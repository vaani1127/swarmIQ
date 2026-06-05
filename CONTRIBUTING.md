# Contributing to SwarmIQ

Thanks for your interest in SwarmIQ. This document is the short version of how to set up the project locally, what we expect from contributions, and how to ship a change.

SwarmIQ was built for the Microsoft Build AI 2026 hackathon (Theme 05 — Agent Swarms) and is now an open project under MIT. PRs are welcome.

---

## Table of contents

- [Getting set up](#getting-set-up)
- [Architecture at a glance](#architecture-at-a-glance)
- [What to work on](#what-to-work-on)
- [Branch + PR workflow](#branch--pr-workflow)
- [Commit message style](#commit-message-style)
- [Code style](#code-style)
- [Testing your change](#testing-your-change)
- [Reporting bugs](#reporting-bugs)
- [Code of conduct](#code-of-conduct)

---

## Getting set up

You need:

- Python 3.11 or newer
- Docker Desktop (recommended — runs Redis alongside the app)
- A free Tavily API key from [app.tavily.com](https://app.tavily.com)
- A GitHub Personal Access Token with the `Models: Read-only` scope from [github.com/settings/tokens?type=beta](https://github.com/settings/tokens?type=beta) (this is your LLM credential — SwarmIQ uses GitHub Models by default)

Then:

```bash
git clone https://github.com/vaani1127/swarmIQ.git
cd swarmIQ
cp .env.example .env
# Edit .env — at minimum fill LLM_API_KEY (your GitHub PAT) and TAVILY_API_KEY
docker compose up --build
# Open http://localhost:8000
```

If you don't have Docker, see the Python venv path in [README.md](README.md#option-b--python-venv).

The `.env` is gitignored — never commit secrets. Everything sensitive flows through env vars; in production they're resolved from Azure Key Vault via the Container App's managed identity.

---

## Architecture at a glance

```
Browser  ──WebSocket──▶  FastAPI (backend/main.py)
                            │
                            ▼
                    Orchestrator (agents.py)
                            │
                            ▼
              4 parallel specialists (asyncio.gather)
                            │
                            ▼
              Debate Moderator (agents.py)
                            │
                            ▼
        Semantic Kernel Critic ⇄ Synthesizer
              (sk_agents.py — group chat)
                            │
                            ▼
                    Final markdown report
```

- **`backend/agents.py`** — Orchestrator, four specialist agents, Debate Moderator
- **`backend/sk_agents.py`** — Semantic Kernel `AgentGroupChat` with Critic + Synthesizer + revision loop
- **`backend/orchestrator.py`** — async parallel runner, dynamic agent selection, Redis cache, cosmos persistence
- **`backend/main.py`** — FastAPI app, WebSocket endpoint, rate limiting, auth, email endpoint
- **`backend/tools.py`** — OpenAI-compatible LLM client + Tavily web search
- **`backend/auth.py`** — Entra ID token validation via JWKS
- **`backend/db.py`** — Cosmos DB MongoDB-API access via Motor
- **`backend/mailer.py`** — SMTP email delivery (Gmail App Password)
- **`frontend/`** — vanilla HTML/CSS/JS, no framework. SVG-based DAG, MSAL.js for auth, jsPDF for export
- **`azure-resources.sh`** — idempotent infra provisioning (Resource Group → ACR → Key Vault → Container Apps env → Container App + RBAC)
- **`.github/workflows/azure-deploy.yml`** — CI/CD on every push to `main`

A more detailed architecture diagram lives in [ARCHITECTURE.md](ARCHITECTURE.md).

---

## What to work on

Good first issues:

- Add more specialists (`Technical Analyst`, `Macro Analyst`) — fit the existing pattern in [backend/agents.py](backend/agents.py)
- Improve the DAG SVG layout for the new specialists
- Add a "compare two companies" mode
- Write proper end-to-end tests with pytest + httpx
- Improve mobile responsiveness past 380px breakpoint
- Internationalisation — the report could be requested in a target language
- A real Cosmos-backed "share this analysis" link

Bigger ideas:

- Replace the always-4 specialist pipeline with a fully dynamic graph that the Orchestrator generates per query
- Stream the LLM tokens (instead of waiting for completion) into the Live Event Stream panel
- Build a Chrome extension that surfaces SwarmIQ analysis on company pages

---

## Branch + PR workflow

1. Fork the repo or create a feature branch off `main`. Branch names should be short and descriptive: `feature/competitor-charts`, `fix/cosmos-timeout`, `docs/readme-typo`.
2. Make your change. Keep PRs focused — one concept per PR. If you find yourself adding "and also..." commits, split into multiple PRs.
3. Open a PR against `main`. Use the title format described in [Commit message style](#commit-message-style).
4. Fill in the PR description:
   - **What** the change does in plain English
   - **Why** it's needed (link the issue if there is one)
   - **How** you tested it locally — at minimum, `docker compose up --build` and one end-to-end query
   - Screenshots / screen recordings for any UI change
5. GitHub Actions runs build + the deploy pipeline on `main`. PR builds should pass image build (the deploy step is gated to `main`).

We squash-merge PRs to keep `main` history linear.

---

## Commit message style

Loosely Conventional Commits:

```
<type>: <short, present tense, no period>

[optional body — wrap at 72 chars]
```

Types we use: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`, `perf`, `style`.

Examples:

```
feat: dynamic agent selection in Orchestrator
fix: stale Critic badge after revision pass
docs: README live demo URL
refactor: extract SK kernel builder
ci: add Azure deploy workflow
```

---

## Code style

**Python (backend)**:
- Format with `ruff format` (configured in `pyproject.toml` if added later)
- Type hints encouraged but not required for hackathon-era code
- Async-first — never block the event loop in a handler
- Logs go through `logger = logging.getLogger("swarmiq")` with `[session_id]` and `[agent_name]` prefixes — see existing examples
- Secrets only via `os.getenv()`, never hardcoded

**Frontend**:
- Vanilla JS — no framework, no build step
- All UI text on a button → wire through an event handler, not inline `onclick` strings that reference globals (some legacy `onclick` exists; new code uses `addEventListener`)
- All user-content rendered into DOM must go through `_esc()` (XSS escaper in app.js)
- Use CSS custom properties via `var(--bg)`, `var(--accent)` etc. so theme toggle keeps working
- No hardcoded URLs — use `location.origin` / `location.host`

**Docker / infra**:
- Multi-stage builds, non-root user
- Health-check every container
- Key Vault references for every secret; never `--set-env-vars` with a literal in CI

---

## Testing your change

There is no formal test suite yet (PRs welcome). Minimum bar:

1. `docker compose up --build` from a fresh clone with your `.env`
2. Open `http://localhost:8000`
3. Run **one APPROVED** query end-to-end (the canonical demo: `Analyze Zepto as an investment opportunity in India`)
4. Run **one NEEDS_REVISION** query so the revision loop fires (`Research Grab's ride-hailing and fintech bundle` usually does it)
5. Click **Download PDF** — verify the PDF renders the Agent Deliberation section
6. Sign in with a Microsoft account → click **Email me the report** → check inbox
7. Sign out → confirm History button hides
8. Open the app in a second tab → confirm cross-tab session sync

If your change touches the LLM prompts, additionally run one query in light theme and one on a phone-sized viewport.

---

## Reporting bugs

Open a [GitHub issue](https://github.com/vaani1127/swarmIQ/issues/new) with:

- A clear, single-sentence title
- Steps to reproduce
- Expected vs. actual behavior
- Browser + OS for frontend issues
- The relevant chunk of `docker compose logs` for backend issues — but please **redact any tokens or env values** before pasting

For security issues, **do not** open a public issue. See [SECURITY.md](SECURITY.md).

---

## Code of conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating you agree to abide by it.

---

Thank you for contributing to SwarmIQ.

— Team Paradise (Dhruv Goyal · Vaani Prashar · Madhav Kapila)
