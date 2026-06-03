import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from backend.agents import (
    orchestrator_agent,
    extract_company,
    market_analyst,
    financial_analyst,
    risk_analyst,
    competitive_analyst,
    critic_agent,
    synthesis_agent,
)
from backend.tools import web_search, llm


def test_full_pipeline():
    print("Testing tools...")
    search_result = web_search("Zepto India startup funding")
    print(search_result[:200])

    print("\nTesting orchestrator...")
    query = "Analyze Zepto as an investment opportunity in Indian quick commerce"
    tasks = orchestrator_agent(query)
    print(tasks)

    company = extract_company(query)
    print(f"\nExtracted company: {company}")

    print("\nTesting all 4 specialists (this takes ~30 seconds)...")

    market_out = market_analyst(tasks["market_task"], company)
    print(f"\n[{market_out['agent']}] {str(market_out.get('findings', ''))[:100]}")

    financial_out = financial_analyst(tasks["financial_task"], company)
    print(f"[{financial_out['agent']}] {str(financial_out.get('findings', ''))[:100]}")

    risk_out = risk_analyst(tasks["risk_task"], company)
    print(f"[{risk_out['agent']}] {str(risk_out.get('findings', ''))[:100]}")

    competitive_out = competitive_analyst(tasks["competitive_task"], company)
    print(f"[{competitive_out['agent']}] {str(competitive_out.get('findings', ''))[:100]}")

    outputs = [market_out, financial_out, risk_out, competitive_out]

    print("\nTesting critic...")
    critic = critic_agent(outputs)
    print(f"Critic status: {critic.get('status')}")

    print("\nTesting synthesizer...")
    report = synthesis_agent(outputs, critic, query)
    print(report[:300])

    print("\nALL TESTS PASSED")


if __name__ == "__main__":
    test_full_pipeline()
