"""
SwarmIQ email delivery — sends the intelligence report to a signed-in user.

Uses Python's built-in smtplib over SMTPS (port 465 + SSL). No extra deps.

Required environment variables (set via Key Vault on production):
  MAIL_ID           — sender Gmail address (e.g. swarmiq.reports@gmail.com)
  MAIL_APP_PASSWORD — 16-char Gmail App Password (NOT the account password)

Optional:
  MAIL_FROM_NAME    — display name in the From header (default: "SwarmIQ")
  MAIL_SMTP_HOST    — override SMTP host (default: smtp.gmail.com)
  MAIL_SMTP_PORT    — override SMTP port (default: 465)
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from html import escape

logger = logging.getLogger("swarmiq")

_DEFAULT_HOST = os.getenv("MAIL_SMTP_HOST", "smtp.gmail.com")
_DEFAULT_PORT = int(os.getenv("MAIL_SMTP_PORT", "465"))


def _markdown_to_html(md: str) -> str:
    """Minimal markdown → HTML conversion for the report body.
    Handles only what the Synthesizer emits: ## headings, **bold**, paragraphs,
    blank-line separation. Anything fancier is escaped and rendered literally."""
    if not md:
        return ""
    lines = md.split("\n")
    out: list[str] = []
    para: list[str] = []

    def _flush():
        if not para:
            return
        text = " ".join(p.strip() for p in para if p.strip())
        if text:
            out.append(f"<p style='margin:0 0 12px;line-height:1.6;color:#1e293b;'>{text}</p>")
        para.clear()

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            _flush()
            continue
        if line.startswith("## "):
            _flush()
            heading = escape(line[3:].strip())
            out.append(
                f"<h2 style='font-family:Inter,system-ui,sans-serif;font-size:18px;color:#0f172a;"
                f"margin:24px 0 8px;padding-bottom:6px;border-bottom:2px solid #e2e8f0;font-weight:700;'>"
                f"{heading}</h2>"
            )
        elif line.startswith("# "):
            _flush()
            heading = escape(line[2:].strip())
            out.append(
                f"<h1 style='font-family:Inter,system-ui,sans-serif;font-size:22px;color:#0f172a;"
                f"margin:24px 0 10px;font-weight:800;'>{heading}</h1>"
            )
        else:
            # Inline bold
            escaped = escape(line)
            escaped = escaped.replace("**", "§§B§§")
            parts = escaped.split("§§B§§")
            rebuilt = ""
            for i, part in enumerate(parts):
                if i % 2 == 1:
                    rebuilt += f"<strong style='color:#0f172a;'>{part}</strong>"
                else:
                    rebuilt += part
            para.append(rebuilt)
    _flush()
    return "\n".join(out)


def _debate_html(debate: dict | None) -> str:
    if not debate or not isinstance(debate, dict):
        return ""
    conflict = debate.get("conflict_topic") or ""
    turns = debate.get("debate") or []
    resolution = debate.get("resolution") or ""
    if not (conflict or turns):
        return ""

    agent_color = {
        "Market Analyst":      "#3b82f6",
        "Financial Analyst":   "#22c55e",
        "Risk Analyst":        "#f59e0b",
        "Competitive Analyst": "#a855f7",
        "Critic":              "#ef4444",
        "Synthesizer":         "#5b5ef4",
    }
    parts: list[str] = []
    parts.append(
        "<div style='margin:24px 0;padding:16px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;'>"
        "<div style='font-size:11px;letter-spacing:0.08em;text-transform:uppercase;color:#64748b;font-weight:700;margin-bottom:8px;'>Agent Deliberation</div>"
    )
    if conflict:
        parts.append(
            "<div style='border-left:3px solid #f59e0b;padding:8px 12px;background:#fef3c7;border-radius:4px;margin-bottom:12px;font-size:13px;color:#78350f;'>"
            f"<strong style='font-weight:700;'>Conflict:</strong> {escape(conflict)}</div>"
        )
    for turn in turns[:8]:
        agent = (turn.get("agent") or "Agent").strip()
        text = (turn.get("point") or turn.get("verdict") or "").strip()
        if not text:
            continue
        color = agent_color.get(agent, "#94a3b8")
        parts.append(
            f"<div style='border-left:3px solid {color};padding:8px 12px;margin-bottom:8px;background:#ffffff;border-radius:4px;'>"
            f"<div style='font-size:10px;font-weight:700;text-transform:uppercase;color:{color};letter-spacing:0.06em;margin-bottom:4px;'>{escape(agent)}</div>"
            f"<div style='font-size:13px;color:#1e293b;line-height:1.5;'>{escape(text)}</div>"
            f"</div>"
        )
    if resolution:
        parts.append(
            "<div style='border-left:3px solid #22c55e;padding:8px 12px;background:#dcfce7;border-radius:4px;margin-top:8px;font-size:13px;color:#14532d;'>"
            f"<strong style='font-weight:700;'>Resolution:</strong> {escape(resolution)}</div>"
        )
    parts.append("</div>")
    return "".join(parts)


def _render_html(query: str, report_md: str, critic: dict, debate: dict | None, user_name: str) -> str:
    status = (critic or {}).get("status", "APPROVED")
    confidence = (critic or {}).get("overall_confidence", "—")
    notes = (critic or {}).get("notes") or ""
    is_approved = status == "APPROVED"
    badge_color = "#22c55e" if is_approved else "#ef4444"
    badge_bg = "#dcfce7" if is_approved else "#fee2e2"
    badge_text = "APPROVED" if is_approved else "NEEDS REVISION"

    return f"""<!DOCTYPE html>
<html><body style="margin:0;padding:24px;background:#f1f5f9;font-family:Inter,Segoe UI,system-ui,Arial,sans-serif;color:#1e293b;">
  <div style="max-width:680px;margin:0 auto;background:#ffffff;border:1px solid #e2e8f0;border-radius:14px;overflow:hidden;box-shadow:0 4px 24px rgba(15,23,42,0.06);">

    <div style="background:linear-gradient(135deg,#0a0a0f 0%,#1a1235 100%);color:#ffffff;padding:24px 28px;">
      <div style="display:flex;align-items:baseline;justify-content:space-between;gap:12px;">
        <div style="font-size:22px;font-weight:800;letter-spacing:-0.01em;">Swarm<span style="color:#7c7ffa;">IQ</span> &middot; Intelligence Report</div>
        <span style="display:inline-block;background:{badge_bg};color:{badge_color};padding:4px 10px;border-radius:999px;font-size:11px;font-weight:700;letter-spacing:0.04em;">{badge_text}</span>
      </div>
      <div style="font-size:12px;opacity:0.7;margin-top:6px;letter-spacing:0.04em;">Six AI specialists. One adversarial Critic. One report.</div>
    </div>

    <div style="padding:24px 28px;border-bottom:1px solid #e2e8f0;">
      <div style="font-size:10px;color:#64748b;letter-spacing:0.08em;text-transform:uppercase;font-weight:700;margin-bottom:4px;">Research Query</div>
      <div style="font-size:15px;color:#0f172a;font-weight:600;line-height:1.5;">{escape(query or "—")}</div>
      <div style="display:flex;gap:24px;margin-top:14px;font-size:12px;color:#475569;">
        <div><strong style="color:#0f172a;">Confidence</strong> · {escape(str(confidence))}</div>
        <div><strong style="color:#0f172a;">Delivered to</strong> · {escape(user_name)}</div>
      </div>
    </div>

    <div style="padding:24px 28px;">
      {_debate_html(debate)}
      <div>{_markdown_to_html(report_md)}</div>
      {"<div style='margin-top:24px;padding:14px 16px;background:#f1f5f9;border-radius:8px;font-size:13px;color:#475569;line-height:1.55;'><strong style='color:#0f172a;'>Critic notes:</strong> " + escape(notes) + "</div>" if notes else ""}
    </div>

    <div style="padding:18px 28px;background:#f8fafc;border-top:1px solid #e2e8f0;text-align:center;font-size:11px;color:#64748b;letter-spacing:0.03em;">
      Generated by <strong style="color:#0f172a;">SwarmIQ</strong> · Microsoft Build AI 2026 · <a href="https://swarmiq.vaaniprashar.tech" style="color:#5b5ef4;text-decoration:none;">swarmiq.vaaniprashar.tech</a>
    </div>

  </div>
</body></html>"""


def send_report_email(
    *,
    to_email: str,
    user_name: str,
    query: str,
    report_md: str,
    critic: dict,
    debate: dict | None = None,
) -> None:
    """Send a styled HTML email with the SwarmIQ report. Raises on failure."""
    sender = os.getenv("MAIL_ID")
    password = os.getenv("MAIL_APP_PASSWORD")
    if not sender or not password:
        raise RuntimeError("Email delivery not configured: MAIL_ID / MAIL_APP_PASSWORD missing.")
    if not to_email or "@" not in to_email:
        raise ValueError(f"Invalid recipient address: {to_email!r}")

    from_name = os.getenv("MAIL_FROM_NAME", "SwarmIQ")
    subject = f"SwarmIQ report — {(query or 'analysis')[:60]}"

    msg = EmailMessage()
    msg["From"] = formataddr((from_name, sender))
    msg["To"] = to_email
    msg["Subject"] = subject

    # Plain-text fallback for clients that don't render HTML
    msg.set_content(
        f"SwarmIQ Intelligence Report\n"
        f"Query: {query}\n\n"
        f"{report_md}\n\n"
        "Generated by SwarmIQ · https://swarmiq.vaaniprashar.tech"
    )
    msg.add_alternative(_render_html(query, report_md, critic, debate, user_name), subtype="html")

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(_DEFAULT_HOST, _DEFAULT_PORT, context=ctx, timeout=20) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg)
    logger.info(f"[Email] sent to={to_email} subject={subject!r}")
