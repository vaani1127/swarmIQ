# SwarmIQ

> Six specialized AI agents. One intelligence report. Real-time.

SwarmIQ is a multi-agent research system. Type a query like *"Analyze Zepto as an investment opportunity in India"* and watch six AI agents work in parallel to produce an executive-grade intelligence report — streamed live to your browser as they work.

Built for the Microsoft HackerEarth Hackathon 2026 — Theme 5: Agent Swarms.

## What it does

| Agent | Job |
|---|---|
| **Orchestrator** | Decomposes the query into four specialised sub-tasks |
| **Market Analyst** | TAM, growth, positioning |
| **Financial Analyst** | Funding, revenue, valuation, burn |
| **Risk Analyst** | Lawsuits, regulatory, controversies |
| **Competitive Analyst** | Direct competitors, market position |
| **Critic** | Adversarial review — flags contradictions and unsupported claims |
| **Synthesizer** | Final markdown report with confidence score |

The Critic is the differentiator — most multi-agent demos skip the review step. SwarmIQ won't.

## Architecture

```
Browser  ──WebSocket──▶  FastAPI  ──asyncio.gather──▶  4 specialists (parallel)
   ▲                        │                                │
   │                        │                                ▼
   └──── live updates ──────┘                            Critic ──▶ Synthesizer ──▶ Report
```

- **Backend:** FastAPI + WebSockets + Groq (Llama 3.3 70B) + Tavily web search
- **Frontend:** Vanilla HTML/CSS/JS — zero framework dependencies
- **Streaming:** Each agent's status is pushed live over a per-session WebSocket

## Local development

```bash
# 1. Clone
git clone https://github.com/dhruvgoyal/swarmIQ.git
cd swarmIQ

# 2. Virtual env (Python 3.11+)
python -m venv venv
# Windows:
.\venv\Scripts\Activate.ps1
# macOS / Linux:
source venv/bin/activate

# 3. Install
pip install -r requirements.txt

# 4. Configure secrets
cp .env.example .env
# Edit .env with your real keys:
#   GROQ_API_KEY    — https://console.groq.com/keys (free)
#   TAVILY_API_KEY  — https://app.tavily.com         (free, 1000 searches/mo)

# 5. Run
python -m backend.main
# → open http://localhost:8000
```

Optional sanity check before opening the browser:

```bash
python -m backend.test_agents   # hits real APIs end-to-end, ~30-60s
```

## Docker (optional)

```bash
docker build -t swarmiq .
docker run --env-file .env -p 8000:8000 swarmiq
# → http://localhost:8000
```

Container respects `$PORT` so it drops straight into any platform that injects it (Render, Railway, Fly, Cloud Run).

## Deploy (Render — free tier)

1. Push this repo to GitHub.
2. Sign in to [render.com](https://render.com) with GitHub.
3. **New → Blueprint** → select your `swarmIQ` repo. Render reads `render.yaml`.
4. In the **Environment** tab, set `GROQ_API_KEY` and `TAVILY_API_KEY`.
5. First build takes 2-4 minutes. Your URL: `https://swarmiq.onrender.com`.

**Free-tier caveat:** the service sleeps after 15 minutes of inactivity. First request after sleep takes 30-50 seconds (cold start). Visit your URL a minute before showing the demo.

WebSockets work on Render's free tier out of the box — no extra config.

## Tech stack

| Layer | Choice |
|---|---|
| LLM | Groq Llama 3.3 70B (free, fast) |
| Web search | Tavily (free, 1000/mo) |
| Backend | FastAPI + Uvicorn + WebSockets |
| Frontend | Vanilla HTML/CSS/JS, html2canvas + jsPDF (CDN) |
| Hosting | Render (free) |

## Features

- Live parallel agent execution
- Adversarial Critic review
- Markdown report with agent attribution
- Dark / light theme toggle (persisted)
- Download report as PDF
- Copy report to clipboard
- Pre-filled example queries

## License

MIT — see [LICENSE](LICENSE).
