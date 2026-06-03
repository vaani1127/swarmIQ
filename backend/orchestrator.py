import asyncio
import json
from concurrent.futures import ThreadPoolExecutor

_executor = ThreadPoolExecutor(max_workers=6)


async def run_in_thread(fn, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, fn, *args)


async def run_swarm(query: str, emit) -> dict:
    from backend.agents import (
        orchestrator_agent,
        market_analyst,
        financial_analyst,
        risk_analyst,
        competitive_analyst,
        critic_agent,
        synthesis_agent,
        extract_company,
    )

    company = extract_company(query)

    await emit("Orchestrator", "started", "Decomposing research query...")
    tasks = await run_in_thread(orchestrator_agent, query)
    await emit("Orchestrator", "done", "Sub-tasks assigned to 4 specialists")

    await emit("Market Analyst", "working", "Analyzing market trends and positioning...")
    await emit("Financial Analyst", "working", "Pulling financials and growth metrics...")
    await emit("Risk Analyst", "working", "Assessing regulatory and operational risks...")
    await emit("Competitive Analyst", "working", "Mapping competitive landscape...")

    mkt, fin, risk, comp = await asyncio.gather(
        run_in_thread(market_analyst, tasks.get("market_task", query), company),
        run_in_thread(financial_analyst, tasks.get("financial_task", query), company),
        run_in_thread(risk_analyst, tasks.get("risk_task", query), company),
        run_in_thread(competitive_analyst, tasks.get("competitive_task", query), company),
    )

    for agent_name, result in [
        ("Market Analyst", mkt),
        ("Financial Analyst", fin),
        ("Risk Analyst", risk),
        ("Competitive Analyst", comp),
    ]:
        finding = result.get("findings", "") if isinstance(result, dict) else str(result)
        await emit(agent_name, "done", finding[:80] + "...")

    await emit("Critic", "working", "Reviewing all outputs for contradictions...")
    critic_result = await run_in_thread(critic_agent, [mkt, fin, risk, comp])
    await emit("Critic", "done", f"Review complete: {critic_result.get('status', 'APPROVED')}")

    await emit("Synthesizer", "working", "Writing final intelligence report...")
    final_report = await run_in_thread(synthesis_agent, [mkt, fin, risk, comp], critic_result, query)
    await emit("Synthesizer", "done", "Report ready")

    return {"outputs": [mkt, fin, risk, comp], "critic": critic_result, "report": final_report}
