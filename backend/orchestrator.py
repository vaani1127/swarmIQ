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
    await emit("Orchestrator", "done", "Sub-tasks assigned to 4 specialists")

    await emit("Market Analyst",      "working", "Analyzing market trends and positioning...")
    await emit("Financial Analyst",   "working", "Pulling financials and growth metrics...")
    await emit("Risk Analyst",        "working", "Assessing regulatory and operational risks...")
    await emit("Competitive Analyst", "working", "Mapping competitive landscape...")

    # ── Parallel specialists — stream each result as it finishes ───────────────
    t_spec = time.perf_counter()
    specialist_tasks = [
        asyncio.create_task(_run_specialist_safe(
            "Market Analyst", market_analyst,
            sub_tasks.get("market_task", query), company,
        )),
        asyncio.create_task(_run_specialist_safe(
            "Financial Analyst", financial_analyst,
            sub_tasks.get("financial_task", query), company,
        )),
        asyncio.create_task(_run_specialist_safe(
            "Risk Analyst", risk_analyst,
            sub_tasks.get("risk_task", query), company,
        )),
        asyncio.create_task(_run_specialist_safe(
            "Competitive Analyst", competitive_analyst,
            sub_tasks.get("competitive_task", query), company,
        )),
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
            await emit(
                name, "done", finding[:80] + "...",
                type="agent_partial_result",
                agent_key=_AGENT_SHORT_KEY.get(name, name.split()[0].lower()),
                key_metrics=(key_metrics[:5] if isinstance(key_metrics, list) else []),
                confidence=confidence,
                findings_preview=finding[:200],
            )
            logger.info(f"[{session_id}] [{name}] complete")
            outputs_map[name] = result

    logger.info(
        f"[{session_id}] [Specialists] parallel_complete — "
        f"{int((time.perf_counter() - t_spec) * 1000)}ms"
    )

    # Restore canonical order so downstream agents always see a consistent list
    outputs: list[dict] = [
        outputs_map.get(n, _make_fallback(n, Exception("task missing")))
        for n in _AGENT_ORDER
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
