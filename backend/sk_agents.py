import asyncio
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from openai import AsyncOpenAI
from semantic_kernel import Kernel
from semantic_kernel.agents import AgentGroupChat, ChatCompletionAgent
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.contents import AuthorRole, ChatMessageContent

load_dotenv()

MAX_REVISIONS = 1

# GitHub Models free tier caps the request body at ~8000 tokens for gpt-4o-mini.
# We compact specialist outputs before passing them to SK chats to stay well under that budget.
# Truncation is char-based (~4 chars/token for English) — not an exact token count.
_FINDINGS_TRUNCATE = 1500  # chars per agent's findings field (~375 tokens at 4 chars/token)
_SOURCES_KEEP = 3

_executor = ThreadPoolExecutor(max_workers=4)


def _compact_output(out: dict) -> dict:
    """Shrink a specialist output dict for inclusion in SK prompts."""
    if not isinstance(out, dict):
        return {"agent": "Unknown", "findings": str(out)[:_FINDINGS_TRUNCATE]}
    return {
        "agent": out.get("agent", "Unknown"),
        "confidence": out.get("confidence", "Medium"),
        "findings": (out.get("findings", "") or "")[:_FINDINGS_TRUNCATE],
        "key_metrics": (out.get("key_metrics", []) or [])[:5],
        "sources": (out.get("sources", []) or [])[:_SOURCES_KEEP],
    }


def _compact_outputs(outs: list) -> list:
    return [_compact_output(o) for o in outs]

# Maps short critic keys → (task dict key, display name for emit)
_AGENT_MAP: dict[str, tuple[str, str]] = {
    "market":      ("market_task",      "Market Analyst"),
    "financial":   ("financial_task",   "Financial Analyst"),
    "risk":        ("risk_task",        "Risk Analyst"),
    "competitive": ("competitive_task", "Competitive Analyst"),
}

_CRITIC_INSTRUCTIONS = (
    "You are an adversarial quality reviewer for a multi-agent research system. Review all "
    "specialist outputs for: 1) Contradictions between agents (e.g. one says revenue "
    "growing, another says declining), 2) Unsupported major claims without source URLs, "
    "3) Suspicious gaps (if a controversial company has zero risks found, that is "
    "suspicious), 4) Confidence mismatches. Return ONLY valid JSON with keys: status "
    "(APPROVED or NEEDS_REVISION), contradictions (list of strings or empty list), issues "
    "(list of strings describing specific problems), flagged_agents (list of agent short "
    "names that produced problematic outputs — choose from: market, financial, risk, "
    "competitive — empty list if status is APPROVED), overall_confidence "
    "(High/Medium/Low), notes (brief summary string)"
)

_SYNTHESIZER_INSTRUCTIONS = (
    "You are a senior research analyst writing an executive intelligence report. Using the "
    "specialist outputs and critic review provided, write a comprehensive markdown report. "
    "Use EXACTLY these section headers: ## Executive Summary, ## Market Position, "
    "## Financial Health, ## Risk Assessment, ## Competitive Landscape, ## Key Insights, "
    "## Recommendation, ## Confidence Score. For each major finding, note in parentheses "
    "which agent found it. Be specific, use real data points from the outputs. At the very "
    "end, add a line: Overall Confidence: [score 0-100]/100. "
    "CRITICAL FORMATTING RULES: "
    "(a) Do NOT emit any code fences, JSON blocks, or raw data structures in the output. "
    "(b) Do NOT echo the literal Critic verdict JSON — translate any critic findings into "
    "prose inside the relevant section. "
    "(c) Do NOT add a top-level '# Executive Intelligence Report' heading; the report starts "
    "directly with '## Executive Summary'. "
    "(d) Output must be valid GitHub-Flavored Markdown with no triple-backtick fences anywhere."
)


async def _run_in_thread(fn, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, fn, *args)


def _build_kernel() -> Kernel:
    """
    Build a Semantic Kernel wired to an OpenAI-compatible inference endpoint.
    Defaults to GitHub Models (free, Microsoft-hosted). Override via env vars to
    swap to Azure OpenAI, OpenAI direct, or any other compatible endpoint.
    """
    base_url = os.getenv("LLM_BASE_URL", "https://models.github.ai/inference")
    api_key = os.getenv("LLM_API_KEY") or os.getenv("GITHUB_TOKEN")
    model_id = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")

    async_client = AsyncOpenAI(base_url=base_url, api_key=api_key)

    kernel = Kernel()
    kernel.add_service(
        OpenAIChatCompletion(
            ai_model_id=model_id,
            async_client=async_client,
        )
    )
    return kernel


def _parse_critic(raw: str) -> dict:
    try:
        result = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        result = {
            "status": "NEEDS_REVISION",
            "contradictions": [],
            "issues": ["Could not parse critic response."],
            "flagged_agents": [],
            "overall_confidence": "Low",
            "notes": raw,
        }
    result.setdefault("agent", "Critic")
    result.setdefault("flagged_agents", [])
    return result


async def run_sk_validation_synthesis(
    specialist_outputs: list,
    query: str,
    emit,
    tasks: dict,
    company: str,
    debate_resolution: str = "",
) -> dict:
    from backend.agents import (
        competitive_analyst,
        financial_analyst,
        market_analyst,
        risk_analyst,
    )

    _agent_fns = {
        "market":      market_analyst,
        "financial":   financial_analyst,
        "risk":        risk_analyst,
        "competitive": competitive_analyst,
    }

    kernel = _build_kernel()
    critic_sk = ChatCompletionAgent(
        kernel=kernel,
        name="Critic",
        instructions=_CRITIC_INSTRUCTIONS,
    )
    synthesizer_sk = ChatCompletionAgent(
        kernel=kernel,
        name="Synthesizer",
        instructions=_SYNTHESIZER_INSTRUCTIONS,
    )
    group_chat = AgentGroupChat(agents=[critic_sk, synthesizer_sk])

    current_outputs = list(specialist_outputs)
    original_outputs = list(specialist_outputs)
    revision_happened = False

    # ── First Critic pass ──────────────────────────────────────────────────────
    await emit("Critic", "thinking", "Running adversarial review via Semantic Kernel...")

    _critic_prompt = f"Review these specialist research outputs:\n{json.dumps(_compact_outputs(current_outputs), indent=2)}"
    if debate_resolution:
        _critic_prompt += (
            f"\n\nDebate Resolution Context: The specialist agents previously debated and "
            f"reached this consensus: \"{debate_resolution}\". Factor this into your review."
        )
    await group_chat.add_chat_message(
        ChatMessageContent(role=AuthorRole.USER, content=_critic_prompt)
    )

    critic_result: dict = {}
    _it = group_chat.invoke_agent(critic_sk)
    try:
        async for message in _it:
            critic_result = _parse_critic(message.content or "")
            break
    finally:
        try:
            await _it.aclose()
        except Exception:
            pass

    # ── Revision loop (MAX_REVISIONS = 1) ──────────────────────────────────────
    if critic_result.get("status") == "NEEDS_REVISION":
        flagged: list[str] = critic_result.get("flagged_agents") or list(_AGENT_MAP.keys())

        await emit(
            "Critic", "revision_requested", "",
            type="revision_requested",
            issues=critic_result.get("issues", []),
            flagged_agents=flagged,
        )

        issue_str = str(critic_result.get("issues", []))
        rerun_plan = [
            (key, _agent_fns[key], tasks.get(task_key, query) + f" REVISION REQUIRED — address these issues: {issue_str}", display)
            for key in flagged
            if key in _AGENT_MAP
            for task_key, display in [_AGENT_MAP[key]]
        ]

        # Signal each flagged card working (blue pulse, removes needs-revision)
        for _, _, _, display in rerun_plan:
            await emit(display, "working", "Revising analysis based on critic feedback...")

        revised_results = await asyncio.gather(
            *[_run_in_thread(fn, revised_task, company) for _, fn, revised_task, _ in rerun_plan]
        )

        display_to_result: dict = {}
        for (_, _, _, display), result in zip(rerun_plan, revised_results):
            finding = result.get("findings", "") if isinstance(result, dict) else str(result)
            await emit(display, "done", finding[:80] + "...")
            display_to_result[display] = result

        # Merge revised outputs back (overwrite flagged agents, keep others)
        current_outputs = [
            display_to_result.get(o.get("agent"), o) for o in current_outputs
        ]
        revision_happened = True

        await group_chat.add_chat_message(
            ChatMessageContent(
                role=AuthorRole.USER,
                content=(
                    "The flagged agents have revised their outputs. "
                    f"Re-review all outputs:\n{json.dumps(_compact_outputs(current_outputs), indent=2)}"
                ),
            )
        )

        new_critic: dict = {}
        _it2 = group_chat.invoke_agent(critic_sk)
        try:
            async for message in _it2:
                new_critic = _parse_critic(message.content or "")
                break
        finally:
            try:
                await _it2.aclose()
            except Exception:
                pass

        critic_result = new_critic
        critic_result["revision_exhausted"] = True

        await emit(
            "Critic", "revision_complete", "",
            type="revision_complete",
            new_status=critic_result.get("status", "APPROVED"),
            critic_result=critic_result,
        )

    await emit("Critic", "done", f"Review complete: {critic_result.get('status', 'APPROVED')}")

    # ── Synthesis ──────────────────────────────────────────────────────────────
    await emit("Synthesizer", "thinking", "Writing final intelligence report via Semantic Kernel...")

    # Summarize the critic as prose so the Synthesizer doesn't echo raw JSON in the report.
    _critic_status = critic_result.get("status", "APPROVED")
    _critic_conf = critic_result.get("overall_confidence", "Medium")
    _critic_notes = critic_result.get("notes", "")
    _critic_issues = critic_result.get("issues") or []
    _issues_text = "; ".join(str(i) for i in _critic_issues[:3]) if _critic_issues else "None"
    critic_summary = (
        f"Critic verdict: {_critic_status} (confidence: {_critic_conf}). "
        f"Issues flagged: {_issues_text}. Notes: {_critic_notes}"
    )

    if revision_happened:
        synth_content = (
            f"Research Query: {query}\n\n"
            f"Specialist Outputs (post-revision):\n{json.dumps(_compact_outputs(current_outputs), indent=2)}\n\n"
            f"{critic_summary}\n\n"
            f"Write the markdown report now. Begin with '## Executive Summary'."
        )
    else:
        synth_content = (
            f"Research Query: {query}\n\n"
            f"Specialist Outputs:\n{json.dumps(_compact_outputs(current_outputs), indent=2)}\n\n"
            f"{critic_summary}\n\n"
            f"Write the markdown report now. Begin with '## Executive Summary'."
        )

    await group_chat.add_chat_message(
        ChatMessageContent(role=AuthorRole.USER, content=synth_content)
    )

    final_report = ""
    _it3 = group_chat.invoke_agent(synthesizer_sk)
    try:
        async for message in _it3:
            final_report = message.content or ""
            break
    finally:
        try:
            await _it3.aclose()
        except Exception:
            pass

    # Belt-and-braces: strip any ```...``` code fences and any leading "# Executive
    # Intelligence Report" heading that the LLM might emit despite instructions.
    if final_report:
        final_report = re.sub(r"```[a-zA-Z]*\s*", "", final_report)
        final_report = final_report.replace("```", "")
        final_report = re.sub(r"^#\s+Executive Intelligence Report\s*\n+", "", final_report.strip())
        final_report = final_report.strip()

    await emit("Synthesizer", "done", "Report ready")

    return {"critic_result": critic_result, "final_report": final_report}
