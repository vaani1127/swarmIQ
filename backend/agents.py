import json
import os

from backend.tools import llm, web_search


def orchestrator_agent(query: str) -> dict:
    system = (
        "You are a research orchestrator. Given a research query about a company or topic, "
        "create 4 specific sub-tasks for specialist agents. Each sub-task should be a specific "
        "search instruction. Return ONLY valid JSON with exactly these keys: market_task, "
        "financial_task, risk_task, competitive_task. Each value is a specific research "
        "instruction string."
    )
    response = llm(system, query, json_mode=True)
    try:
        return json.loads(response)
    except (json.JSONDecodeError, TypeError):
        return {
            "market_task": query,
            "financial_task": query,
            "risk_task": query,
            "competitive_task": query,
        }


def market_analyst(task: str, company: str) -> dict:
    search_data = (
        web_search(f"{company} market size growth industry 2024 2025")
        + web_search(f"{company} total addressable market position")
    )
    system = (
        "You are a senior market analyst. Analyze the provided search data and answer the "
        "research task. Focus on: market size, growth rate, industry trends, market position. "
        "Return ONLY valid JSON with keys: findings (detailed string), key_metrics (list of "
        "strings), sources (list of URLs found in data), confidence (High/Medium/Low)"
    )
    user = f"Task: {task}\n\nSearch Data:\n{search_data}"
    response = llm(system, user, json_mode=True)
    try:
        result = json.loads(response)
        result["agent"] = "Market Analyst"
        return result
    except (json.JSONDecodeError, TypeError):
        return {
            "agent": "Market Analyst",
            "findings": "Could not parse analyst response.",
            "key_metrics": [],
            "sources": [],
            "confidence": "Low",
        }


def financial_analyst(task: str, company: str) -> dict:
    search_data = (
        web_search(f"{company} funding revenue valuation investors")
        + web_search(f"{company} financial results 2024 2025")
    )
    system = (
        "You are a senior financial analyst. Extract financial signals. Focus on: funding "
        "rounds, revenue figures, valuation, burn rate, key investors. Return ONLY valid JSON "
        "with keys: findings (string), key_metrics (list), sources (list), confidence "
        "(High/Medium/Low), red_flags (list of strings, empty if none)"
    )
    user = f"Task: {task}\n\nSearch Data:\n{search_data}"
    response = llm(system, user, json_mode=True)
    try:
        result = json.loads(response)
        result["agent"] = "Financial Analyst"
        return result
    except (json.JSONDecodeError, TypeError):
        return {
            "agent": "Financial Analyst",
            "findings": "Could not parse analyst response.",
            "key_metrics": [],
            "sources": [],
            "confidence": "Low",
            "red_flags": [],
        }


def risk_analyst(task: str, company: str) -> dict:
    search_data = (
        web_search(f"{company} lawsuit controversy scandal problem 2024")
        + web_search(f"{company} regulatory issues criticism negative news")
    )
    system = (
        "You are a risk and compliance analyst. Identify risks from the search data. Focus on "
        "legal, regulatory, reputational, operational risks. IMPORTANT: If you find no risks, "
        "explicitly state this and explain why the risk appears low — do not leave this blank. "
        "Return ONLY valid JSON with keys: findings (string), risks (list of dicts each with "
        "keys 'risk' and 'severity' where severity is High/Medium/Low), sources (list), "
        "confidence (High/Medium/Low), overall_risk (High/Medium/Low)"
    )
    user = f"Task: {task}\n\nSearch Data:\n{search_data}"
    response = llm(system, user, json_mode=True)
    try:
        result = json.loads(response)
        result["agent"] = "Risk Analyst"
        return result
    except (json.JSONDecodeError, TypeError):
        return {
            "agent": "Risk Analyst",
            "findings": "Could not parse analyst response.",
            "risks": [],
            "sources": [],
            "confidence": "Low",
            "overall_risk": "Low",
        }


def competitive_analyst(task: str, company: str) -> dict:
    search_data = (
        web_search(f"{company} competitors alternatives comparison 2024")
        + web_search(f"{company} vs competitors market share differentiation")
    )
    system = (
        "You are a competitive intelligence analyst. Map the competitive landscape. Identify "
        "3-5 direct competitors. Return ONLY valid JSON with keys: findings (string), "
        "competitors (list of dicts each with 'name' and 'differentiator' keys), sources "
        "(list), confidence (High/Medium/Low), competitive_position (one of: "
        "Leader/Challenger/Niche/Laggard)"
    )
    user = f"Task: {task}\n\nSearch Data:\n{search_data}"
    response = llm(system, user, json_mode=True)
    try:
        result = json.loads(response)
        result["agent"] = "Competitive Analyst"
        return result
    except (json.JSONDecodeError, TypeError):
        return {
            "agent": "Competitive Analyst",
            "findings": "Could not parse analyst response.",
            "competitors": [],
            "sources": [],
            "confidence": "Low",
            "competitive_position": "Niche",
        }


def debate_moderator_agent(specialist_outputs: list) -> dict:
    slim = [
        {
            "agent": o.get("agent", ""),
            "findings": o.get("findings", ""),
            "key_metrics": o.get("key_metrics", []),
        }
        for o in specialist_outputs
        if isinstance(o, dict)
    ]
    system = (
        "You are a debate moderator for an AI research swarm. Given specialist analyst outputs, "
        "identify the single most important CONFLICT or DISAGREEMENT between them. Generate a "
        "structured debate where conflicting agents rebut each other, then the Critic issues a "
        "verdict. Return ONLY valid JSON with keys: conflict_topic (string: one sentence "
        "describing the core disagreement), debate (array of objects each with an 'agent' key "
        "and either a 'point' key for analysts or a 'verdict' key for the Critic, each value "
        "1-2 sentences), resolution (string: one-sentence final verdict the Synthesizer should "
        "treat as authoritative). Only include agents with a genuine stake in the conflict — "
        "2 to 4 agents is ideal. For the Critic entry use 'verdict' not 'point'."
    )
    response = llm(system, json.dumps(slim, indent=2), json_mode=True)
    try:
        return json.loads(response)
    except (json.JSONDecodeError, TypeError):
        return {
            "conflict_topic": "Unable to identify a specific conflict.",
            "debate": [],
            "resolution": "No conflict resolution available.",
        }


def critic_agent(outputs: list) -> dict:
    serialized = json.dumps(outputs, indent=2)
    system = (
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
    response = llm(system, serialized, json_mode=True)
    try:
        result = json.loads(response)
        result["agent"] = "Critic"
        return result
    except (json.JSONDecodeError, TypeError):
        return {
            "agent": "Critic",
            "status": "NEEDS_REVISION",
            "contradictions": [],
            "issues": ["Could not parse critic response."],
            "flagged_agents": [],
            "overall_confidence": "Low",
            "notes": "Critic agent failed to produce a valid review.",
        }


def synthesis_agent(outputs: list, critic: dict, query: str) -> str:
    system = (
        "You are a senior research analyst writing an executive intelligence report. Using the "
        "specialist outputs and critic review provided, write a comprehensive markdown report. "
        "Use EXACTLY these section headers: ## Executive Summary, ## Market Position, "
        "## Financial Health, ## Risk Assessment, ## Competitive Landscape, ## Key Insights, "
        "## Recommendation, ## Confidence Score. For each major finding, note in parentheses "
        "which agent found it. Be specific, use real data points from the outputs. At the very "
        "end, add a line: Overall Confidence: [score 0-100]/100"
    )
    user = (
        f"Research Query: {query}\n\n"
        f"Specialist Outputs:\n{json.dumps(outputs, indent=2)}\n\n"
        f"Critic Review:\n{json.dumps(critic, indent=2)}"
    )
    return llm(system, user)


if __name__ == "__main__":
    mock_outputs = [
        {
            "agent": "Market Analyst",
            "findings": "Zepto operates in India's quick commerce market valued at $5B, growing at 40% YoY.",
            "key_metrics": ["$5B TAM", "40% YoY growth", "10-minute delivery SLA"],
            "sources": ["https://example.com/zepto-market"],
            "confidence": "High",
        },
        {
            "agent": "Financial Analyst",
            "findings": "Zepto raised $1B in 2024 at a $3.6B valuation. Revenue run-rate ~$1B. Still loss-making.",
            "key_metrics": ["$3.6B valuation", "$1B raised 2024", "~$1B revenue run-rate"],
            "sources": ["https://example.com/zepto-funding"],
            "confidence": "High",
            "red_flags": ["High cash burn", "Not yet profitable"],
        },
        {
            "agent": "Risk Analyst",
            "findings": "Zepto faces regulatory scrutiny over FDI compliance and intense price-war pressure.",
            "risks": [
                {"risk": "FDI regulatory non-compliance risk", "severity": "High"},
                {"risk": "Margin compression from price wars", "severity": "Medium"},
            ],
            "sources": ["https://example.com/zepto-risk"],
            "confidence": "Medium",
            "overall_risk": "Medium",
        },
        {
            "agent": "Competitive Analyst",
            "findings": "Zepto competes with Blinkit (Zomato), Swiggy Instamart, and BigBasket Now.",
            "competitors": [
                {"name": "Blinkit", "differentiator": "Backed by Zomato, largest network"},
                {"name": "Swiggy Instamart", "differentiator": "Integrated with food delivery"},
                {"name": "BigBasket Now", "differentiator": "Tata backing, grocery depth"},
            ],
            "sources": ["https://example.com/zepto-competitors"],
            "confidence": "High",
            "competitive_position": "Challenger",
        },
    ]

    critic = critic_agent(mock_outputs)
    print("=== CRITIC OUTPUT ===")
    print(json.dumps(critic, indent=2))

    report = synthesis_agent(mock_outputs, critic, "Analyze Zepto as an investment opportunity")
    print("\n=== SYNTHESIS REPORT ===")
    print(report)
