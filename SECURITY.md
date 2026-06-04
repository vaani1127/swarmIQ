# Security Policy

We take the security of SwarmIQ seriously. This document explains what versions are supported, how to report a vulnerability, and what our threat model looks like.

---

## Supported versions

| Version | Status | Notes |
|---|---|---|
| `main` | ✅ Supported | All security fixes land here first |
| Anything tagged before `v1.0` | ⚠️ Best effort | This is a hackathon-era prototype; please upgrade |

Once we cut release tags, only the latest two minor versions will receive security patches.

---

## Reporting a vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Instead, use one of these private channels — in this order of preference:

1. **GitHub Security Advisories** (preferred):
   Open a private security advisory at
   [github.com/vaani1127/swarmIQ/security/advisories/new](https://github.com/vaani1127/swarmIQ/security/advisories/new).
   GitHub will keep your report private until we publish a coordinated fix.

2. **Email**:
   Send the details to **dhruv621999goyal@gmail.com**.
   Use the subject line `[SwarmIQ Security]` and we will reply within 72 hours acknowledging receipt.

### What to include

- A clear description of the issue and the impact
- Steps to reproduce (a minimal proof-of-concept is ideal)
- The component or file path you believe is affected
- Whether the issue is publicly known or already exploited
- Your name / handle if you would like attribution in the fix advisory

### What to expect from us

- An acknowledgement within **72 hours**
- A reasonable triage assessment within **7 days**
- A coordinated fix and disclosure timeline that respects both severity and the time you need to verify the patch
- Public credit in the release notes, unless you prefer to remain anonymous

### Out of scope

The following are **not** considered security vulnerabilities:

- Rate-limit thresholds being lower than you would like
- The `/test`, `/health`, or `/config` endpoints being publicly readable (they intentionally are — they expose no secrets)
- CORS being permissive (`allow_origins=["*"]`) — the API is a public demo
- The Critic returning `NEEDS_REVISION` on edge-case queries (this is the gate working, not a bug)
- Behavior of dependencies we do not maintain (e.g. Tavily, Azure OpenAI, GitHub Models) — please report those upstream

---

## Threat model

SwarmIQ is a public demo app for a hackathon. The threat model is:

- **Trust boundary 1** — anonymous browser user vs. the SwarmIQ backend.
  Anonymous users can run analyses and download reports. They cannot list or access other users' history.

- **Trust boundary 2** — signed-in user vs. another signed-in user.
  Microsoft Entra ID tokens are validated server-side via JWKS (`backend/auth.py`). The Cosmos DB queries scope by the `oid` claim (`backend/db.py`). One user cannot read another user's history.

- **Trust boundary 3** — the deployed app vs. its hosting infrastructure.
  Secrets are stored in Azure Key Vault and accessed via the Container App's system-assigned managed identity. They never appear in env files, git history, or container logs. The GitHub Actions service principal is scoped only to the `swarmiq-rg` resource group.

### What we do to keep this safe

- All inputs that get rendered into the DOM go through an `_esc()` HTML escaper (`frontend/app.js`)
- All LLM calls use OpenAI's `response_format={"type": "json_object"}` mode and `json.loads()` with fallback dicts — we never `eval()` LLM output
- WebSocket sessions are scoped to a per-page `session_id`; messages never cross sessions
- The Container App runs as **non-root user 1000** with a multi-stage Dockerfile
- The custom domain is on the **gray cloud** in Cloudflare (DNS only — not proxied) so the TLS endpoint is Microsoft-issued and WebSockets are not interfered with
- Rate limiting is applied to the analysis endpoint (5 requests/minute per IP)
- Per-session concurrency is gated server-side via Redis to prevent abuse loops

### What we know we have not done

- No formal penetration test
- CSP headers are not yet set
- Subresource integrity hashes are not yet set on the CDN scripts (`html2canvas`, `jsPDF`, `MSAL.js`)
- No automated dependency vulnerability scanning yet (consider adding `pip-audit` to CI)

PRs to address any of the above are very welcome.

---

## Disclosure

We follow coordinated disclosure. After a fix is merged we publish a release note describing:

- The class of vulnerability
- The affected versions
- The fix
- Credit to the reporter (unless they preferred anonymity)

Thank you for helping keep SwarmIQ users safe.

— Team Paradise
