import asyncio
import hashlib
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor

from backend.sk_agents import run_sk_validation_synthesis

logger = logging.getLogger("swarmiq")

_executor = ThreadPoolExecutor(max_workers=6)

_AGENT_SHORT_KEY = {
    "Market Analyst":      "market",
    "Financial Analyst":   "financial",
    "Risk Analyst":        "risk",
    "Competitive Analyst": "competitive",
}

_AGENT_ORDER = ["Market Analyst", "Financial Analyst", "Risk Analyst", "Competitive Analyst"]

_SHORT_TO_DISPLAY = {v: k for k, v in _AGENT_SHORT_KEY.items()}

_WORKING_LABEL = {
    "Market Analyst":      "Analyzing market trends and positioning...",
    "Financial Analyst":   "Pulling financials and growth metrics...",
    "Risk Analyst":        "Assessing regulatory and operational risks...",
    "Competitive Analyst": "Mapping competitive landscape...",
}


async def run_in_thread(fn, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, fn, *args)


async def _run_specialist_safe(name: str, fn, task_arg: str, company: str):
    try:
        result = await run_in_thread(fn, task_arg, company)
        return name, result, None
    except Exception as exc:
        return name, None, exc


async def extract_company(query: str) -> str:
    """LLM-based extraction — handles lowercase, multi-word, and non-English names."""
    from backend.tools import llm
    prompt = (
        "Extract the company or organization name from this query. Return ONLY the name, "
        "nothing else. If multiple companies, return the primary one. "
        "If no company found, return 'Unknown'."
    )
    result = await run_in_thread(llm, prompt, query, False)
    return result.strip()


_FALLBACK_EXTRAS: dict[str, dict] = {
    "Market Analyst":      {"key_metrics": [], "sources": [], "confidence": "Low"},
    "Financial Analyst":   {"key_metrics": [], "sources": [], "confidence": "Low", "red_flags": []},
    "Risk Analyst":        {"risks": [], "sources": [], "confidence": "Low", "overall_risk": "Low"},
    "Competitive Analyst": {"competitors": [], "sources": [], "confidence": "Low", "competitive_position": "Niche"},
}


def _make_fallback(agent_name: str, error: Exception) -> dict:
    return {
        "agent": agent_name,
        "findings": f"Analysis failed: {error}",
        "error": True,
        **_FALLBACK_EXTRAS.get(agent_name, {}),
    }


async def run_swarm(query: str, emit, session_id: str = "", redis_client=None) -> dict:
    # ── Cache check ────────────────────────────────────────────────────────────
    cache_key = f"swarm:result:{hashlib.sha256(query.lower().strip().encode()).hexdigest()}"
    if redis_client:
        try:
            cached = await redis_client.get(cache_key)
            if cached:
                logger.info(f"[{session_id}] [Cache] hit — {cache_key}")
                await emit("SYSTEM", "cache_hit", "Results loaded from cache", type="cache_hit")
                return json.loads(cached)
        except Exception as exc:
            logger.warning(f"[{session_id}] [Cache] read_failed — {exc}")

    from backend.agents import (
        competitive_analyst,
        debate_moderator_agent,
        financial_analyst,
        market_analyst,
        orchestrator_agent,
        risk_analyst,
    )

    logger.info(f"[{session_id}] [Orchestrator] analysis_start")
    t_swarm = time.perf_counter()

    company = await extract_company(query)
    logger.info(f"[{session_id}] [Orchestrator] company_extracted — {company!r}")

    await emit("Orchestrator", "started", "Decomposing research query...")
    sub_tasks = await run_in_thread(orchestrator_agent, query)

    # Dynamic specialist selection — Orchestrator picks 2-4 relevant specialists
    agents_needed = sub_tasks.get("agents_needed") or ["market", "financial", "risk", "competitive"]
    selected_display_names = [
        _SHORT_TO_DISPLAY[k] for k in agents_needed if k in _SHORT_TO_DISPLAY
    ]
    if not selected_display_names:
        selected_display_names = list(_AGENT_ORDER)
    logger.info(f"[{session_id}] [Orchestrator] agents_selected — {agents_needed}")

    await emit(
        "Orchestrator", "done",
        f"Selected {len(selected_display_names)}/4 specialists for this query",
        type="agents_selected",
        agents=agents_needed,
    )

    # Mark unselected specialists as skipped so the UI dims them out
    for name in _AGENT_ORDER:
        if name not in selected_display_names:
            await emit(name, "skipped", "Not relevant to this query", type="agent_skipped")

    for name in selected_display_names:
        await emit(name, "working", _WORKING_LABEL[name])

    # ── Parallel specialists — only the selected ones run ─────────────────────
    t_spec = time.perf_counter()
    _specialist_fn = {
        "Market Analyst":      (market_analyst,      "market_task"),
        "Financial Analyst":   (financial_analyst,   "financial_task"),
        "Risk Analyst":        (risk_analyst,        "risk_task"),
        "Competitive Analyst": (competitive_analyst, "competitive_task"),
    }
    specialist_tasks = [
        asyncio.create_task(_run_specialist_safe(
            display_name,
            _specialist_fn[display_name][0],
            sub_tasks.get(_specialist_fn[display_name][1], query),
            company,
        ))
        for display_name in selected_display_names
    ]

    outputs_map: dict[str, dict] = {}
    for fut in asyncio.as_completed(specialist_tasks):
        name, result, error = await fut
        if error:
            logger.error(f"[{session_id}] [{name}] agent_failed — {error}")
            await emit(name, "error", f"Analysis failed: {error}",
                       type="agent_error", error=str(error))
            outputs_map[name] = _make_fallback(name, error)
        else:
            finding = result.get("findings", "") if isinstance(result, dict) else str(result)
            key_metrics = result.get("key_metrics", []) if isinstance(result, dict) else []
            confidence = result.get("confidence", "Medium") if isinstance(result, dict) else "Medium"
            sources = result.get("sources", []) if isinstance(result, dict) else []
            await emit(
                name, "done", finding[:80] + "...",
                type="agent_partial_result",
                agent_key=_AGENT_SHORT_KEY.get(name, name.split()[0].lower()),
                key_metrics=(key_metrics[:5] if isinstance(key_metrics, list) else []),
                confidence=confidence,
                findings_preview=finding[:200],
                sources=(sources[:3] if isinstance(sources, list) else []),
            )
            logger.info(f"[{session_id}] [{name}] complete")
            outputs_map[name] = result

    logger.info(
        f"[{session_id}] [Specialists] parallel_complete — "
        f"{int((time.perf_counter() - t_spec) * 1000)}ms"
    )

    # Downstream agents (Debate, Critic, Synthesis) only see specialists that actually ran.
    # Skipped specialists are intentionally omitted so they don't pollute the prompts or
    # cause the Critic to flag "missing analysis" as a contradiction.
    outputs: list[dict] = [
        outputs_map[n] for n in selected_display_names if n in outputs_map
    ]

    # ── Debate step ────────────────────────────────────────────────────────────
    t_debate = time.perf_counter()
    debate_result = await run_in_thread(debate_moderator_agent, outputs)
    logger.info(
        f"[{session_id}] [Debate] complete — "
        f"{int((time.perf_counter() - t_debate) * 1000)}ms"
    )

    for turn in debate_result.get("debate", []):
        await emit(
            turn.get("agent", ""),
            "debate_turn", "",
            type="debate_turn",
            point=turn.get("point") or turn.get("verdict", ""),
            conflict_topic=debate_result.get("conflict_topic", ""),
        )
        await asyncio.sleep(0.7)

    if debate_result.get("resolution"):
        await emit(
            "Critic", "debate_resolved", "",
            type="debate_resolved",
            resolution=debate_result["resolution"],
        )

    # ── Critic + revision loop + Synthesis ────────────────────────────────────
    t_sk = time.perf_counter()
    sk_result = await run_sk_validation_synthesis(
        outputs, query, emit, sub_tasks, company,
        debate_resolution=debate_result.get("resolution", ""),
    )
    logger.info(
        f"[{session_id}] [SK] critic_synthesis_complete — "
        f"{int((time.perf_counter() - t_sk) * 1000)}ms"
    )

    total_ms = int((time.perf_counter() - t_swarm) * 1000)
    logger.info(f"[{session_id}] [Orchestrator] analysis_complete — {total_ms}ms")

    final = {
        "outputs": outputs,
        "critic": sk_result["critic_result"],
        "report": sk_result["final_report"],
        "company": company,
        "debate": debate_result,
    }

    # ── Cache store ────────────────────────────────────────────────────────────
    if redis_client:
        try:
            await redis_client.setex(cache_key, 86400, json.dumps(final))
            logger.info(f"[{session_id}] [Cache] stored — TTL=86400s")
        except Exception as exc:
            logger.warning(f"[{session_id}] [Cache] write_failed — {exc}")

    return final
