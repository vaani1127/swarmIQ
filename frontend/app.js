// -- Theme (runs before DOM paint to avoid flicker) ----------------------------
(function initTheme() {
  const saved = localStorage.getItem("swarmiq-theme") || "dark";
  if (saved === "light") document.documentElement.setAttribute("data-theme", "light");
})();

function toggleTheme() {
  const isLight = document.documentElement.getAttribute("data-theme") === "light";
  const next = isLight ? "dark" : "light";
  if (next === "light") document.documentElement.setAttribute("data-theme", "light");
  else document.documentElement.removeAttribute("data-theme");
  localStorage.setItem("swarmiq-theme", next);
  const btn = document.getElementById("theme-toggle");
  if (btn) btn.textContent = next === "light" ? "☀️" : "🌙";
}

// -- Example queries ----------------------------------------
const EXAMPLE_QUERIES = [
  "Analyze Zepto as an investment opportunity in India",
  "Research Anthropic's competitive position in AI",
  "Evaluate Stripe as a payments market leader",
  "Assess OpenAI's enterprise strategy and revenue outlook",
  "Analyze Nvidia's dominance in AI accelerators through 2026",
  "Evaluate Tesla's autonomous driving roadmap and risks",
  "Research SpaceX's Starlink as a telecom disruptor",
  "Assess Palantir's commercial expansion beyond government",
  "Analyze Shopify's competitive moat vs Amazon",
  "Evaluate Databricks as a pre-IPO investment",
  "Research Perplexity AI's path to challenging Google search",
  "Assess Reliance Jio's 5G monetisation strategy",
  "Analyze Paytm's recovery after RBI restrictions",
  "Evaluate Nykaa's positioning in Indian beauty e-commerce",
  "Research Swiggy's IPO valuation and growth thesis",
  "Assess Ola Electric's market share trajectory",
  "Analyze Adani Group's debt profile and risk exposure",
  "Evaluate Mahindra's EV pivot vs Tata Motors",
  "Research PhonePe's UPI dominance and fintech ambitions",
  "Assess Byju's collapse — what went wrong",
  "Analyze CRED's monetisation model and unit economics",
  "Evaluate Razorpay's enterprise payments expansion",
  "Research Meesho's social commerce vs Flipkart",
  "Assess Lenskart's vertical integration and global expansion",
  "Analyze Boat as a consumer electronics brand",
  "Evaluate Mamaearth's D2C playbook and margin pressure",
  "Research Zomato's quick commerce push with Blinkit",
  "Assess Dream11's regulatory risk in fantasy sports",
  "Analyze Polygon's positioning in the L2 blockchain race",
  "Evaluate Coinbase's path to profitability after the crypto winter",
  "Research Robinhood's expansion into crypto and futures",
  "Assess Plaid's strategic position in open banking",
  "Analyze Klarna's BNPL model under tightening regulation",
  "Evaluate Wise as a cross-border payments leader",
  "Research Revolut's super-app strategy outside the UK",
  "Assess Nubank's lead in Latin American digital banking",
  "Analyze MercadoLibre as the Amazon of Latin America",
  "Evaluate Sea Group's e-commerce and gaming portfolio",
  "Research Grab's ride-hailing and fintech bundle",
  "Assess Gojek vs Grab in Southeast Asian super-apps",
  "Analyze ByteDance's path to a TikTok spin-off or IPO",
  "Evaluate Pinduoduo's Temu disruption in global e-commerce",
  "Research Alibaba's restructuring and cloud strategy",
  "Assess Xiaomi's EV launch and smartphone moat",
  "Analyze Spotify's profitability turnaround thesis",
  "Evaluate Netflix's ad-tier and password-sharing crackdown",
  "Research Disney's streaming strategy vs Netflix",
  "Assess Roblox as a UGC platform and creator economy",
  "Analyze Unity vs Unreal in the game engine market",
  "Evaluate Figma after the Adobe deal collapsed",
];

function pickRandomQueries(n) {
  const pool = EXAMPLE_QUERIES.slice();
  const out = [];
  while (out.length < n && pool.length) {
    const i = Math.floor(Math.random() * pool.length);
    out.push(pool.splice(i, 1)[0]);
  }
  return out;
}

function renderExampleChips() {
  const container = document.getElementById("example-queries");
  if (!container) return;
  const chips = pickRandomQueries(3);
  container.innerHTML = chips
    .map(q => `<button type="button" class="example-chip" onclick="useExample(this)">${q.replace(/"/g, "&quot;")}</button>`)
    .join("");
}

function useExample(el) {
  const input = document.getElementById("query");
  input.value = el.textContent.trim();
  input.focus();
}

// -- Core state ----------------------------------------
const SESSION_ID = Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
const API_BASE = location.origin;
const WS_BASE = (location.protocol === "https:" ? "wss:" : "ws:") + "//" + location.host;

const AGENT_DISPLAY_NAMES = {
  market: "Market Analyst",
  financial: "Financial Analyst",
  risk: "Risk Analyst",
  competitive: "Competitive Analyst",
};

const AGENT_BADGE_COLORS = {
  "Market Analyst":      { bg: "rgba(59,130,246,0.15)",  color: "#3b82f6" },
  "Financial Analyst":   { bg: "rgba(34,197,94,0.15)",   color: "#22c55e" },
  "Risk Analyst":        { bg: "rgba(245,158,11,0.15)",  color: "#f59e0b" },
  "Competitive Analyst": { bg: "rgba(168,85,247,0.15)",  color: "#a855f7" },
  "Critic":              { bg: "rgba(239,68,68,0.15)",   color: "#ef4444" },
};

let ws = null;
let reportText = "";
let lastQuery = "";
let lastCritic = null;
let lastElapsed = 0;
let timerStart = 0;
let timerInterval = null;
let debateActive = false;

const LAUNCH_READY_LABEL = "Launch Swarm \u2197";
const LAUNCH_BUSY_LABEL = "Launching...";

// -- Auth state ----------------------------------------
let msalInstance = null;
let currentUser = null;
let authToken = null;
let authConfig = null;

// -- Pipeline DAG controller ----------------------------------------
const DAG = (() => {
  let specDone = new Set();

  function nodeEl(id) { return document.getElementById("dag-" + id); }
  function dotsEl(id) { return document.getElementById("dag-dots-" + id); }

  function setNode(id, ...classes) {
    const el = nodeEl(id);
    if (!el) return;
    el.className = "dag-node";
    classes.forEach(c => { if (c) el.classList.add(c); });
  }

  function setDots(id, on) {
    const el = dotsEl(id);
    if (el) el.classList.toggle("dag-active", on);
  }

  function specKey(agentName) {
    return agentName.split(" ")[0].toLowerCase();
  }

  function checkAllSpecsDone() {
    if (specDone.size >= 4) setDots("merge", true);
  }

  return {
    reset() {
      specDone.clear();
      ["orch", "market", "financial", "risk", "competitive"].forEach(id => setNode(id));
      ["debate", "critic", "synthesizer"].forEach(id => setNode(id, "dag-faint"));
      document.querySelectorAll(".dag-dots").forEach(d => d.classList.remove("dag-active"));
    },

    onEvent(data) {
      const agent  = data.agent  || "";
      const status = data.status || "";
      const type   = data.type   || "";

      if (type === "cache_hit") {
        ["orch","market","financial","risk","competitive","debate","critic","synthesizer"]
          .forEach(id => setNode(id, "dag-done"));
        document.querySelectorAll(".dag-dots").forEach(d => d.classList.remove("dag-active"));
        return;
      }

      if (type === "debate_turn") {
        setNode("debate", "dag-active-amber");
        setDots("deb-crit", true);
        return;
      }

      if (type === "debate_resolved") {
        setNode("debate", "dag-done");
        setDots("merge", false);
        return;
      }

      if (type === "revision_requested") {
        setNode("critic", "dag-critic-revision");
        return;
      }

      if (type === "revision_complete") {
        setNode("critic", data.new_status === "APPROVED" ? "dag-critic-approved" : "dag-done");
        return;
      }

      if (type === "agents_selected") {
        const selected = new Set((data.agents || []).map(a => a.toLowerCase()));
        ["market", "financial", "risk", "competitive"].forEach(k => {
          if (!selected.has(k)) {
            setNode(k, "dag-skipped");
            setDots(k, false);
            specDone.add(k); // count as done for the merge gate
          }
        });
        checkAllSpecsDone();
        return;
      }

      if (type === "agent_skipped" || status === "skipped") {
        const k = specKey(agent);
        setNode(k, "dag-skipped");
        setDots(k, false);
        specDone.add(k);
        checkAllSpecsDone();
        return;
      }

      if (agent === "Orchestrator") {
        if (status === "started") { setNode("orch", "dag-active-purple"); setDots("orch", true); }
        else if (status === "done") {
          setNode("orch", "dag-done"); setDots("orch", false);
          ["market","financial","risk","competitive"].forEach(s => {
            const el = nodeEl(s);
            // Don't reanimate dots on skipped specialists
            if (el && !el.classList.contains("dag-skipped")) setDots(s, true);
          });
        }
        return;
      }

      const SPECIALISTS = ["Market Analyst","Financial Analyst","Risk Analyst","Competitive Analyst"];
      if (SPECIALISTS.includes(agent)) {
        const k = specKey(agent);
        if (status === "working") {
          setNode(k, "dag-active-blue");
        } else if (status === "done" || type === "agent_partial_result") {
          setNode(k, "dag-done"); setDots(k, false);
          specDone.add(k); checkAllSpecsDone();
        } else if (status === "error") {
          setNode(k, "dag-error"); setDots(k, false);
          specDone.add(k); checkAllSpecsDone();
        }
        return;
      }

      if (agent === "Critic") {
        if (status === "thinking") { setNode("critic", "dag-active-red"); setDots("deb-crit", true); }
        else if (status === "done") {
          const el = nodeEl("critic");
          if (el && !el.classList.contains("dag-critic-approved") && !el.classList.contains("dag-critic-revision")) {
            setNode("critic", "dag-done");
          }
          setDots("deb-crit", false);
        }
        return;
      }

      if (agent === "Synthesizer") {
        if (status === "thinking") { setNode("synthesizer", "dag-active-blue"); setDots("crit-synth", true); }
        else if (status === "done") { setNode("synthesizer", "dag-done"); setDots("crit-synth", false); }
      }
    },
  };
})();

// -- Live Thoughts event log ----------------------------------------
let _thoughtsCount = 0;
const _MAX_THOUGHTS = 120;

function _resetThoughts() {
  _thoughtsCount = 0;
  const panel = document.getElementById("thoughts-panel");
  if (panel) panel.innerHTML = `<div class="thoughts-empty">Waiting for the swarm to start…</div>`;
  const count = document.getElementById("thoughts-count");
  if (count) count.textContent = "0";
  const wrap = document.querySelector(".thoughts-wrap");
  if (wrap) wrap.classList.remove("collapsed");
}

function toggleThoughts() {
  const wrap = document.querySelector(".thoughts-wrap");
  if (wrap) wrap.classList.toggle("collapsed");
}

function _formatTime(d) {
  const pad = n => String(n).padStart(2, "0");
  const ms = String(d.getMilliseconds()).padStart(3, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${ms.slice(0, 2)}`;
}

function _thoughtIconAndClass(data) {
  const status = data.status || "";
  const type = data.type || "";
  if (status === "error" || type === "agent_error") return ["✗", "thought-error"];
  if (status === "done")                              return ["✓", "thought-done"];
  if (status === "working" || status === "started")   return ["▶", "thought-working"];
  if (status === "thinking")                          return ["◉", "thought-thinking"];
  if (type === "debate_turn")                         return ["⚡", "thought-debate"];
  if (type === "debate_resolved")                     return ["✓", "thought-done"];
  if (type === "revision_requested")                  return ["↻", "thought-thinking"];
  if (type === "revision_complete")                   return ["✓", "thought-done"];
  if (type === "cache_hit")                           return ["♥", "thought-done"];
  if (type === "agent_partial_result")                return ["•", "thought-done"];
  if (type === "agents_selected")                     return ["⊕", "thought-system"];
  if (data.agent === "SYSTEM")                        return ["◇", "thought-system"];
  return ["·", ""];
}

function _logThought(data) {
  const panel = document.getElementById("thoughts-panel");
  if (!panel) return;

  if (_thoughtsCount === 0) panel.innerHTML = "";

  const [icon, cssClass] = _thoughtIconAndClass(data);
  const agent = data.agent || "—";
  const status = data.status || data.type || "";
  let msg = data.message || "";
  if (!msg && data.type === "debate_turn") msg = `${data.agent || ""}: ${(data.point || data.verdict || "").slice(0, 80)}`;
  if (!msg && data.type === "agents_selected") msg = `selected: ${(data.agents || []).join(", ")}`;
  if (!msg && data.type === "cache_hit") msg = "loaded from cache (24h)";
  if (!msg && data.type === "revision_requested") msg = `revising: ${(data.flagged_agents || []).join(", ")}`;
  msg = String(msg).slice(0, 140);

  const row = document.createElement("div");
  row.className = `thought-entry ${cssClass}`.trim();
  row.innerHTML =
    `<span class="thought-time">${_formatTime(new Date())}</span>` +
    `<span class="thought-icon">${icon}</span>` +
    `<span class="thought-agent">${agent}</span>` +
    `<span class="thought-msg">${status}${msg ? " — " + msg.replace(/</g, "&lt;") : ""}</span>`;
  panel.appendChild(row);

  // Cap entries so the DOM doesn't grow unbounded on long sessions
  while (panel.children.length > _MAX_THOUGHTS) panel.removeChild(panel.firstChild);

  _thoughtsCount += 1;
  const count = document.getElementById("thoughts-count");
  if (count) count.textContent = String(_thoughtsCount);

  // Auto-scroll to newest (only if user hasn't scrolled up)
  const nearBottom = panel.scrollHeight - panel.scrollTop - panel.clientHeight < 50;
  if (nearBottom) panel.scrollTop = panel.scrollHeight;
}

// -- Timer ----------------------------------------
function startTimer() {
  timerStart = performance.now();
  const el = document.getElementById("timer-value");
  if (timerInterval) clearInterval(timerInterval);
  timerInterval = setInterval(() => {
    const secs = (performance.now() - timerStart) / 1000;
    if (el) el.textContent = secs.toFixed(1) + "s";
  }, 100);
}

function stopTimer() {
  if (timerInterval) {
    clearInterval(timerInterval);
    timerInterval = null;
  }
  const secs = (performance.now() - timerStart) / 1000;
  const el = document.getElementById("timer-value");
  if (el) el.textContent = secs.toFixed(1) + "s";
}

// -- Agent card rendering ----------------------------------------
function clearErrors() {
  ["input-error", "swarm-error"].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = "";
    el.classList.add("hidden");
  });
}

function showError(message, target = "swarm") {
  const id = target === "input" ? "input-error" : "swarm-error";
  const el = document.getElementById(id);
  if (!el) return;

  el.textContent = message || "Something went wrong. Please try again.";
  el.classList.remove("hidden");

  if (target !== "input") {
    const section = document.getElementById("swarm-section");
    if (section) {
      section.classList.remove("hidden");
      section.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }
}

function resetLaunchButton() {
  const btn = document.getElementById("launch-btn");
  if (!btn) return;
  btn.disabled = false;
  btn.textContent = LAUNCH_READY_LABEL;
}

function handleFatalLaunchError(message) {
  stopTimer();
  showError(message, "swarm");
  if (ws && ws.readyState === WebSocket.OPEN) ws.close();
  resetLaunchButton();
}

async function submitAnalysisRequest(query, headers) {
  const formData = new FormData();
  formData.append("query", query);
  formData.append("session_id", SESSION_ID);

  try {
    const response = await fetch(API_BASE + "/analyze", {
      method: "POST",
      headers,
      body: formData,
    });

    let payload = {};
    try {
      payload = await response.json();
    } catch (e) {
      payload = {};
    }

    if (!response.ok || payload.status === "error") {
      handleFatalLaunchError(payload.message || "The swarm could not start. Please try again.");
    }
  } catch (err) {
    console.error("Analyze request failed", err);
    handleFatalLaunchError("Could not reach the backend service. Please try again in a moment.");
  }
}

async function waitForServerHealth() {
  const overlay = document.getElementById("warmup-overlay");
  if (!overlay) return;

  const showTimer = setTimeout(() => overlay.classList.remove("hidden"), 500);

  while (true) {
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 2500);
      const response = await fetch(API_BASE + "/health", {
        cache: "no-store",
        signal: controller.signal,
      });
      clearTimeout(timeout);

      if (response.ok) {
        clearTimeout(showTimer);
        overlay.classList.add("hidden");
        return;
      }
    } catch (e) {
      // Keep the overlay visible while the hosted container wakes up.
    }

    clearTimeout(showTimer);
    overlay.classList.remove("hidden");
    await new Promise(resolve => setTimeout(resolve, 1500));
  }
}

function populateAgentCard(agentName, data) {
  const card = document.querySelector('[data-agent="' + agentName + '"]');
  if (!card) return;
  const existing = card.querySelector(".agent-details");
  if (existing) existing.remove();

  const details = document.createElement("div");
  details.className = "agent-details";

  const conf = data.confidence || "Medium";
  const confColor =
    conf === "High"   ? "var(--success)" :
    conf === "Low"    ? "var(--danger)"  : "var(--accent)";
  const badge = document.createElement("span");
  badge.className = "conf-badge";
  badge.textContent = conf + " confidence";
  badge.style.cssText =
    `background:${confColor}1a;color:${confColor};border:1px solid ${confColor}33;`;
  details.appendChild(badge);

  const metrics = Array.isArray(data.key_metrics) ? data.key_metrics : [];
  if (metrics.length > 0) {
    const list = document.createElement("ul");
    list.className = "metrics-list";
    metrics.slice(0, 4).forEach(m => {
      const li = document.createElement("li");
      li.textContent = typeof m === "string" ? m : JSON.stringify(m);
      li.title = li.textContent;
      list.appendChild(li);
    });
    details.appendChild(list);
  } else if (data.findings_preview) {
    const preview = document.createElement("p");
    preview.className = "findings-preview";
    preview.textContent = data.findings_preview;
    details.appendChild(preview);
  }

  const sources = Array.isArray(data.sources) ? data.sources : [];
  if (sources.length > 0) {
    const sourcesWrap = document.createElement("div");
    sourcesWrap.className = "sources-list";
    const label = document.createElement("span");
    label.className = "sources-label";
    label.textContent = "Sources:";
    sourcesWrap.appendChild(label);
    sources.slice(0, 3).forEach(url => {
      if (typeof url !== "string" || !url) return;
      let host = url;
      try { host = new URL(url).hostname.replace(/^www\./, ""); } catch {}
      const a = document.createElement("a");
      a.className = "source-link";
      a.href = url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.textContent = host;
      a.title = url;
      sourcesWrap.appendChild(a);
    });
    details.appendChild(sourcesWrap);
  }

  card.appendChild(details);
}

function handleCacheHit() {
  const names = ["Orchestrator","Market Analyst","Financial Analyst","Risk Analyst","Competitive Analyst","Critic"];
  names.forEach(n => updateAgentCard(n, "done", "Loaded from cache"));
  const el = document.getElementById("timer-value");
  if (el) el.textContent = "⚡ cached";
}

function updateAgentCard(agentName, status, message) {
  const card = document.querySelector('[data-agent="' + agentName + '"]');
  if (!card) return;

  const statusEl = card.querySelector(".agent-status");

  card.classList.remove("working", "done", "idle", "needs-revision", "skipped");

  if (status === "done") {
    card.classList.add("done");
    statusEl.textContent = "✓ Complete";
  } else if (status === "working" || status === "started" || status === "thinking") {
    card.classList.add("working");
    statusEl.textContent = message || status;
  } else if (status === "skipped") {
    card.classList.add("skipped");
    statusEl.textContent = "— Not relevant";
  } else {
    statusEl.textContent = message || status;
  }
}

// -- Critic result ----------------------------------------
function showCriticResult(critic) {
  document.getElementById("critic-section").classList.remove("hidden");

  const isApproved = critic.status === "APPROVED";
  const badgeClass = isApproved ? "status-approved" : "status-revision";
  const badgeLabel = isApproved ? "Approved" : "Needs Revision";

  let contradictionsHTML = "";
  if (critic.contradictions && critic.contradictions.length > 0) {
    const items = critic.contradictions
      .map(c => `<li style="font-size:13px;color:var(--muted);margin-bottom:4px;">${c}</li>`)
      .join("");
    contradictionsHTML = `<ul style="margin:0.5rem 0 0.5rem 1rem;padding:0;">${items}</ul>`;
  }

  document.getElementById("critic-box").innerHTML = `
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:0.75rem;">
      <span class="critic-status ${badgeClass}">${badgeLabel}</span>
      <span style="font-size:13px;color:var(--muted);">Confidence: ${critic.overall_confidence || "—"}</span>
    </div>
    ${contradictionsHTML}
    <p style="font-size:13px;color:var(--muted);margin:0;">${critic.notes || ""}</p>
  `;
}

// -- Revision flow ----------------------------------------
function handleRevisionRequested(data) {
  const flagged = (data.flagged_agents || []).map(k => AGENT_DISPLAY_NAMES[k] || k);
  const issues = data.issues || [];

  flagged.forEach(name => {
    const card = document.querySelector('[data-agent="' + name + '"]');
    if (!card) return;
    card.classList.remove("working", "done", "idle");
    card.classList.add("needs-revision");
    const statusEl = card.querySelector(".agent-status");
    if (statusEl) statusEl.textContent = "Revision requested";
  });

  const label = flagged.length
    ? "Critic requested revision from: " + flagged.join(" + ")
    : "Critic requested revision from all specialists";

  const entry = document.createElement("div");
  entry.className = "revision-entry";
  entry.id = "revision-entry-pending";
  entry.innerHTML = `<span style="color:var(--danger);margin-right:6px;">⟳</span>${label}`;
  if (issues.length) {
    const detail = document.createElement("div");
    detail.style.cssText = "font-size:11px;opacity:0.7;margin-top:3px;";
    detail.textContent = issues.slice(0, 2).join("; ");
    entry.appendChild(detail);
  }

  const log = document.getElementById("revision-log");
  if (log) log.appendChild(entry);
}

function handleRevisionComplete(data) {
  const newStatus = data.new_status || "APPROVED";
  const isApproved = newStatus === "APPROVED";
  const icon = isApproved ? "✓" : "✗";
  const color = isApproved ? "var(--success)" : "var(--danger)";
  const note = isApproved ? "" : " (proceeding to synthesis)";

  const pending = document.getElementById("revision-entry-pending");
  if (pending) {
    pending.removeAttribute("id");
    if (isApproved) pending.classList.add("complete");
    pending.innerHTML =
      `<span style="color:${color};margin-right:6px;">${icon}</span>` +
      `Revision complete — Critic verdict: <strong>${newStatus}</strong>${note}`;
  }

  // Refresh the Critic badge with the post-revision verdict so the UI doesn't
  // show stale "Needs Revision / Low" after the second pass approves.
  if (data.critic_result) {
    lastCritic = data.critic_result;
    showCriticResult(lastCritic);
    const banner = document.getElementById("revision-banner");
    if (banner) {
      if (isApproved) banner.classList.add("hidden");
      else banner.classList.remove("hidden");
    }
  }
}

// -- Typewriter ----------------------------------------
async function _typewriter(el, text, duration) {
  const chars = [...text];
  const delay = chars.length > 0 ? Math.max(8, Math.floor(duration / chars.length)) : 0;
  for (const ch of chars) {
    el.textContent += ch;
    await new Promise(r => setTimeout(r, delay));
  }
}

// -- Debate panel ----------------------------------------
function handleDebateTurn(data) {
  const section = document.getElementById("debate-section");
  const topicEl = document.getElementById("debate-topic");
  const turnsEl = document.getElementById("debate-turns");
  const panelEl = document.getElementById("debate-panel");

  if (!debateActive) {
    debateActive = true;
    if (section) section.classList.remove("hidden");
    if (panelEl) panelEl.classList.add("debating");
    if (topicEl) topicEl.textContent = "⚡ Conflict Detected: " + (data.conflict_topic || "");
    if (section) section.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  const agentName = data.agent || "";
  const point = data.point || "";
  const theme = AGENT_BADGE_COLORS[agentName] || { bg: "rgba(148,163,184,0.12)", color: "#94a3b8" };

  const bubble = document.createElement("div");
  bubble.className = "debate-bubble";

  const badge = document.createElement("span");
  badge.className = "debate-badge";
  badge.textContent = agentName;
  badge.style.cssText = `background:${theme.bg};color:${theme.color};`;

  const textEl = document.createElement("div");
  textEl.className = "debate-text";

  bubble.appendChild(badge);
  bubble.appendChild(textEl);
  if (turnsEl) turnsEl.appendChild(bubble);

  _typewriter(textEl, point, 300);
}

function handleDebateResolved(data) {
  debateActive = false;
  const panelEl = document.getElementById("debate-panel");
  if (panelEl) panelEl.classList.remove("debating");

  const resEl = document.getElementById("debate-resolution");
  if (resEl) {
    resEl.classList.remove("hidden");
    resEl.innerHTML =
      `<span style="color:var(--success);margin-right:8px;">✓</span>` +
      (data.resolution || "");
  }
}

// -- Report rendering ----------------------------------------
function renderReport(markdown) {
  reportText = markdown;
  document.getElementById("report-section").classList.remove("hidden");

  let html = markdown
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\n{3,}/g, "\n\n")
    .replace(/\n/g, "<br>")
    .replace(/<\/h2><br>/g, "</h2>");

  document.getElementById("report-content").innerHTML = `<div>${html}</div>`;

  document.getElementById("report-section").scrollIntoView({ behavior: "smooth" });
}

// -- Launch swarm ----------------------------------------
async function launchSwarm() {
  const query = document.getElementById("query").value.trim();
  clearErrors();
  if (!query) {
    showError("Enter a research query to launch the swarm.", "input");
    return;
  }
  lastQuery = query;
  lastCritic = null;

  const btn = document.getElementById("launch-btn");
  btn.disabled = true;
  btn.textContent = LAUNCH_BUSY_LABEL;

  document.getElementById("swarm-section").classList.remove("hidden");

  document.querySelectorAll(".agent-card").forEach(card => {
    card.classList.remove("working", "done", "idle");
    card.querySelector(".agent-status").textContent = "Waiting...";
    const details = card.querySelector(".agent-details");
    if (details) details.remove();
  });
  DAG.reset();
  _resetThoughts();

  document.getElementById("critic-section").classList.add("hidden");
  document.getElementById("report-section").classList.add("hidden");
  document.getElementById("revision-banner").classList.add("hidden");

  const revLog = document.getElementById("revision-log");
  if (revLog) revLog.innerHTML = "";
  document.querySelectorAll(".agent-card").forEach(c => c.classList.remove("needs-revision"));

  debateActive = false;
  document.getElementById("debate-section").classList.add("hidden");
  document.getElementById("debate-topic").textContent = "";
  document.getElementById("debate-turns").innerHTML = "";
  const debResEl = document.getElementById("debate-resolution");
  if (debResEl) { debResEl.classList.add("hidden"); debResEl.innerHTML = ""; }
  const debPanelEl = document.getElementById("debate-panel");
  if (debPanelEl) debPanelEl.classList.remove("debating");

  // Refresh auth token silently before making the request
  await _refreshTokenIfNeeded();

  startTimer();
  ws = new WebSocket(WS_BASE + "/ws/" + SESSION_ID);

  ws.onopen = () => {
    setTimeout(() => {
      const headers = {};
      if (authToken) headers["Authorization"] = "Bearer " + authToken;

      submitAnalysisRequest(query, headers);
    }, 400);
  };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    _logThought(data);

    if (data.agent === "SYSTEM" && data.status === "error") {
      handleFatalLaunchError(data.message || "The analysis failed before the swarm could finish.");
      return;
    }

    // Any progress event proves the swarm is alive — clear any stale "already running" banner
    // (covers the case where a previous session was already active server-side, but the
    // existing run is still streaming back to us)
    if (data.status === "working" || data.status === "started" || data.status === "done" || data.status === "thinking" ||
        data.type === "agent_partial_result" || data.type === "debate_turn") {
      clearErrors();
    }

    if (data.status === "error" || data.type === "agent_error") {
      showError(data.message || "One agent failed, so the swarm is continuing with a fallback.", "swarm");
    }

    DAG.onEvent(data);

    if (data.agent === "SYSTEM" && data.status === "complete") {
      lastElapsed = (performance.now() - timerStart) / 1000;
      stopTimer();
      lastCritic = data.critic || null;
      showCriticResult(data.critic);
      if (data.critic && data.critic.status !== "APPROVED") {
        document.getElementById("revision-banner").classList.remove("hidden");
      }
      renderReport(data.report);
      resetLaunchButton();

      // Phase 5: persist result for anonymous users in localStorage
      _saveToLocalStorage(data.report, data.critic, query);
    } else if (data.type === "cache_hit") {
      handleCacheHit();
    } else if (data.type === "agent_skipped" || data.status === "skipped") {
      updateAgentCard(data.agent, "skipped", data.message || "Not relevant to this query");
    } else if (data.type === "agent_partial_result") {
      updateAgentCard(data.agent, data.status, data.message);
      populateAgentCard(data.agent, data);
    } else if (data.type === "debate_turn") {
      handleDebateTurn(data);
    } else if (data.type === "debate_resolved") {
      handleDebateResolved(data);
    } else if (data.type === "revision_requested") {
      handleRevisionRequested(data);
    } else if (data.type === "revision_complete") {
      handleRevisionComplete(data);
    } else {
      updateAgentCard(data.agent, data.status, data.message);
    }
  };

  ws.onerror = () => {
    stopTimer();
    showError("Connection error. Is the backend running on port 8000?", "swarm");
    resetLaunchButton();
  };
}

// -- Copy / PDF ----------------------------------------
function copyReport() {
  navigator.clipboard.writeText(reportText);
  const btn = document.querySelector(".report-actions .download-btn");
  btn.textContent = "Copied! ✓";
  setTimeout(() => {
    btn.textContent = "Copy Report ↗";
  }, 2000);
}

async function downloadPDF() {
  const fallbackText = document.getElementById("report-content")?.innerText || "";
  const content = (reportText || fallbackText).trim();
  if (!content) return;

  const btn = document.getElementById("pdf-btn");
  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Generating...";

  try {
    const { jsPDF } = window.jspdf;
    const pdf = new jsPDF("p", "mm", "a4");
    const pageW = pdf.internal.pageSize.getWidth();
    const pageH = pdf.internal.pageSize.getHeight();
    const margin = 16;
    const contentW = pageW - margin * 2;
    const bottom = 18;
    let pageNumber = 1;
    let y = 18;

    const colors = {
      bg: [15, 15, 23],
      panel: [19, 19, 26],
      border: [30, 30, 46],
      text: [226, 232, 240],
      strong: [255, 255, 255],
      muted: [148, 163, 184],
      accent: [91, 94, 244],
      success: [34, 197, 94],
      danger: [239, 68, 68],
    };

    function paintPage() {
      pdf.setFillColor(...colors.bg);
      pdf.rect(0, 0, pageW, pageH, "F");
    }

    function drawFooter() {
      pdf.setFont("helvetica", "normal");
      pdf.setFontSize(8);
      pdf.setTextColor(...colors.muted);
      pdf.text(`SwarmIQ | Page ${pageNumber}`, pageW / 2, pageH - 8, { align: "center" });
    }

    function addPage() {
      drawFooter();
      pdf.addPage();
      pageNumber += 1;
      paintPage();
      y = 18;
    }

    function ensureSpace(height) {
      if (y + height > pageH - bottom) addPage();
    }

    function cleanInline(text) {
      return String(text == null ? "" : text)
        .replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1 ($2)")
        .replace(/\*\*(.*?)\*\*/g, "$1")
        .replace(/__(.*?)__/g, "$1")
        .replace(/`([^`]+)`/g, "$1")
        .replace(/\*(.*?)\*/g, "$1")
        .trim();
    }

    function writeText(text, opts = {}) {
      const size = opts.size || 10;
      const lineHeight = opts.lineHeight || size * 0.42;
      const x = opts.x || margin;
      const maxWidth = opts.maxWidth || contentW;
      pdf.setFont("helvetica", opts.style || "normal");
      pdf.setFontSize(size);
      pdf.setTextColor(...(opts.color || colors.text));

      const lines = pdf.splitTextToSize(cleanInline(text), maxWidth);
      lines.forEach(line => {
        ensureSpace(lineHeight);
        pdf.text(line, x, y);
        y += lineHeight;
      });
      y += opts.after || 0;
    }

    function writeLabel(text) {
      writeText(text.toUpperCase(), {
        size: 8,
        lineHeight: 4,
        color: colors.muted,
        style: "bold",
        after: 1,
      });
    }

    function markdownBlocks(markdown) {
      const blocks = [];
      let paragraph = [];

      function flushParagraph() {
        if (paragraph.length) {
          blocks.push({ type: "paragraph", text: paragraph.join(" ") });
          paragraph = [];
        }
      }

      markdown.split(/\r?\n/).forEach(rawLine => {
        const line = rawLine.trim();
        if (!line) {
          flushParagraph();
          return;
        }

        const heading = line.match(/^#{1,3}\s+(.+)$/);
        if (heading) {
          flushParagraph();
          blocks.push({ type: "heading", text: heading[1] });
          return;
        }

        const bullet = line.match(/^[-*]\s+(.+)$/);
        if (bullet) {
          flushParagraph();
          blocks.push({ type: "bullet", text: bullet[1] });
          return;
        }

        const ordered = line.match(/^\d+[.)]\s+(.+)$/);
        if (ordered) {
          flushParagraph();
          blocks.push({ type: "bullet", text: ordered[1] });
          return;
        }

        paragraph.push(line);
      });

      flushParagraph();
      return blocks;
    }

    paintPage();

    pdf.setFont("helvetica", "bold");
    pdf.setFontSize(20);
    pdf.setTextColor(...colors.strong);
    pdf.text("Swarm", margin, y);
    const swarmW = pdf.getTextWidth("Swarm");
    pdf.setTextColor(...colors.accent);
    pdf.text("IQ", margin + swarmW, y);
    const titleX = margin + swarmW + pdf.getTextWidth("IQ") + 2;
    pdf.setTextColor(...colors.strong);
    pdf.text("Intelligence Report", titleX, y);
    y += 9;

    const isApproved = lastCritic && lastCritic.status === "APPROVED";
    const verdictLabel = lastCritic ? (isApproved ? "APPROVED" : "NEEDS REVISION") : "UNREVIEWED";
    const confidence = (lastCritic && lastCritic.overall_confidence) || "-";
    const elapsedStr = lastElapsed > 0 ? lastElapsed.toFixed(1) + "s" : "-";
    const verdictColor = isApproved ? colors.success : colors.danger;

    pdf.setFillColor(...colors.panel);
    pdf.setDrawColor(...colors.border);
    pdf.roundedRect(margin, y, contentW, 29, 3, 3, "FD");
    y += 7;
    writeText(`Generated: ${new Date().toLocaleString()}`, {
      x: margin + 5,
      maxWidth: contentW - 10,
      size: 9,
      lineHeight: 4.2,
      color: colors.muted,
      after: 1,
    });
    writeText(`Critic verdict: ${verdictLabel} | Confidence: ${confidence} | Elapsed: ${elapsedStr}`, {
      x: margin + 5,
      maxWidth: contentW - 10,
      size: 9,
      lineHeight: 4.2,
      color: verdictColor,
      style: "bold",
    });
    y += 9;

    writeLabel("Research Query");
    writeText(lastQuery || "-", {
      size: 11,
      lineHeight: 5.2,
      color: colors.strong,
      style: "bold",
      after: 5,
    });

    if (!isApproved && lastCritic) {
      writeText("Critic flagged this report for revision. Review the Quality Review section before relying on these findings.", {
        size: 9,
        lineHeight: 4.3,
        color: colors.danger,
        style: "bold",
        after: 5,
      });
    }

    if (lastCritic && lastCritic.notes) {
      writeLabel("Quality Review");
      writeText(lastCritic.notes, {
        size: 9,
        lineHeight: 4.3,
        color: colors.muted,
        after: 5,
      });
    }

    writeLabel("Report");

    markdownBlocks(content).forEach(block => {
      if (block.type === "heading") {
        ensureSpace(12);
        y += 2;
        writeText(block.text, {
          size: 13,
          lineHeight: 6,
          color: colors.strong,
          style: "bold",
          after: 1,
        });
        pdf.setDrawColor(...colors.border);
        pdf.line(margin, y, pageW - margin, y);
        y += 4;
      } else if (block.type === "bullet") {
        writeText("- " + block.text, {
          x: margin + 4,
          maxWidth: contentW - 4,
          size: 10,
          lineHeight: 4.7,
          color: colors.text,
          after: 1,
        });
      } else {
        writeText(block.text, {
          size: 10,
          lineHeight: 4.8,
          color: colors.text,
          after: 3,
        });
      }
    });

    drawFooter();
    pdf.save("swarmiq-report.pdf");
  } catch (err) {
    console.error("PDF generation failed", err);
    showError("PDF generation failed. Please try again.", "swarm");
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

// PHASE 4: Microsoft Entra auth via MSAL.js
// ----------------------------------------

async function initAuth() {
  try {
    const resp = await fetch(API_BASE + "/config");
    if (!resp.ok) return;
    authConfig = await resp.json();

    if (!authConfig.authEnabled) return;
    if (typeof msal === "undefined") {
      console.warn("[Auth] MSAL.js not loaded — auth disabled");
      return;
    }

    msalInstance = new msal.PublicClientApplication({
      auth: {
        clientId: authConfig.clientId,
        authority: authConfig.authority,
        redirectUri: location.origin,
      },
      cache: { cacheLocation: "sessionStorage" },
    });
    await msalInstance.initialize();

    // Restore session if account already signed in
    const accounts = msalInstance.getAllAccounts();
    if (accounts.length > 0) {
      await _refreshTokenForAccount(accounts[0]);
    } else {
      // Show sign-in option now that auth is confirmed available
      _showSignInOption();
    }
  } catch (e) {
    console.warn("[Auth] init failed:", e);
  }
}

async function _refreshTokenForAccount(account) {
  try {
    const result = await msalInstance.acquireTokenSilent({
      scopes: ["openid", "profile", "email"],
      account,
    });
    authToken = result.idToken;
    currentUser = {
      name: account.name || account.username || "User",
      oid: account.localAccountId,
    };
    _updateAuthUI();
  } catch (e) {
    authToken = null;
    currentUser = null;
    _showSignInOption();
  }
}

async function _refreshTokenIfNeeded() {
  if (!msalInstance || !currentUser) return;
  const accounts = msalInstance.getAllAccounts();
  if (accounts.length === 0) return;
  try {
    const result = await msalInstance.acquireTokenSilent({
      scopes: ["openid", "profile", "email"],
      account: accounts[0],
    });
    authToken = result.idToken;
  } catch (e) {
    console.warn("[Auth] token refresh failed:", e);
  }
}

async function signIn() {
  if (!msalInstance) return;
  try {
    const result = await msalInstance.loginPopup({
      scopes: ["openid", "profile", "email"],
    });
    authToken = result.idToken;
    currentUser = {
      name: result.account.name || result.account.username || "User",
      oid: result.account.localAccountId,
    };
    _updateAuthUI();
    loadHistory();
  } catch (e) {
    if (e.errorCode !== "user_cancelled") {
      console.warn("[Auth] sign-in failed:", e);
    }
  }
}

async function signOut() {
  if (!msalInstance) return;
  try {
    const accounts = msalInstance.getAllAccounts();
    if (accounts.length > 0) {
      await msalInstance.logoutPopup({ account: accounts[0] });
    }
  } catch (e) {
    console.warn("[Auth] sign-out error:", e);
  }
  authToken = null;
  currentUser = null;
  _updateAuthUI();
}

function _showSignInOption() {
  const signinBtn = document.getElementById("signin-btn");
  const signinBanner = document.getElementById("signin-banner");
  if (signinBtn) signinBtn.classList.remove("hidden");
  if (signinBanner) signinBanner.classList.remove("hidden");
}

function _updateAuthUI() {
  const signinBtn = document.getElementById("signin-btn");
  const userInfo = document.getElementById("user-info");
  const userName = document.getElementById("user-name");
  const historyBtn = document.getElementById("history-btn");
  const signinBanner = document.getElementById("signin-banner");

  if (currentUser) {
    if (signinBtn) signinBtn.classList.add("hidden");
    if (userInfo) userInfo.classList.remove("hidden");
    if (userName) userName.textContent = currentUser.name;
    if (historyBtn) historyBtn.classList.remove("hidden");
    if (signinBanner) signinBanner.classList.add("hidden");
  } else {
    if (authConfig && authConfig.authEnabled) {
      if (signinBtn) signinBtn.classList.remove("hidden");
      if (signinBanner) signinBanner.classList.remove("hidden");
    }
    if (userInfo) userInfo.classList.add("hidden");
    if (historyBtn) historyBtn.classList.add("hidden");
  }
}

// ----------------------------------------
// PHASE 4: History panel
// ----------------------------------------

function toggleHistory() {
  const panel = document.getElementById("history-panel");
  if (!panel) return;
  if (panel.classList.contains("hidden")) {
    panel.classList.remove("hidden");
    document.getElementById("history-overlay").classList.remove("hidden");
    loadHistory();
  } else {
    closeHistory();
  }
}

function closeHistory() {
  const panel = document.getElementById("history-panel");
  const overlay = document.getElementById("history-overlay");
  if (panel) panel.classList.add("hidden");
  if (overlay) overlay.classList.add("hidden");
}

async function loadHistory() {
  if (!authToken) return;
  const list = document.getElementById("history-list");
  if (list) list.innerHTML = '<p class="history-empty">Loading…</p>';
  try {
    const resp = await fetch(API_BASE + "/history", {
      headers: { Authorization: "Bearer " + authToken },
    });
    if (!resp.ok) {
      if (list) list.innerHTML = '<p class="history-empty">Could not load history.</p>';
      return;
    }
    const data = await resp.json();
    _renderHistoryList(data.analyses || []);
  } catch (e) {
    console.warn("[History] load failed:", e);
    if (list) list.innerHTML = '<p class="history-empty">Could not load history.</p>';
  }
}

function _renderHistoryList(analyses) {
  const list = document.getElementById("history-list");
  if (!list) return;
  if (analyses.length === 0) {
    list.innerHTML = '<p class="history-empty">No analyses yet. Run a query to get started.</p>';
    return;
  }
  list.innerHTML = analyses.map(a => `
    <div class="history-card">
      <div class="history-card-company">${_esc(a.company || "Unknown")}</div>
      <div class="history-card-query">${_esc(a.query || "")}</div>
      <div class="history-card-meta">${_fmtDate(a.created_at)}</div>
      <button class="history-load-btn" onclick="loadAnalysis('${_esc(a._id)}')">Load</button>
    </div>
  `).join("");
}

async function loadAnalysis(analysisId) {
  if (!authToken) return;
  try {
    const resp = await fetch(API_BASE + "/analysis/" + encodeURIComponent(analysisId), {
      headers: { Authorization: "Bearer " + authToken },
    });
    if (!resp.ok) return;
    const data = await resp.json();
    const analysis = data.analysis;

    // Populate state
    lastQuery = analysis.query || "";
    lastCritic = analysis.critic_result || null;
    lastElapsed = analysis.duration_seconds || 0;

    // Show relevant sections
    document.getElementById("swarm-section").classList.remove("hidden");
    document.getElementById("revision-banner").classList.add("hidden");
    document.getElementById("debate-section").classList.add("hidden");

    if (lastCritic) {
      showCriticResult(lastCritic);
      if (lastCritic.status !== "APPROVED") {
        document.getElementById("revision-banner").classList.remove("hidden");
      }
    }
    if (analysis.final_report) renderReport(analysis.final_report);

    closeHistory();
  } catch (e) {
    console.warn("[History] loadAnalysis failed:", e);
  }
}

// ----------------------------------------
// PHASE 5: localStorage fallback for anonymous users
// ----------------------------------------

const _LS_KEY = "swarmiq:last_analysis";

function _saveToLocalStorage(report, critic, query) {
  try {
    localStorage.setItem(_LS_KEY, JSON.stringify({
      query,
      report,
      critic,
      savedAt: new Date().toISOString(),
    }));
  } catch (e) { /* quota exceeded or private browsing */ }
}

function _loadFromLocalStorage() {
  try {
    const raw = localStorage.getItem(_LS_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (e) { return null; }
}

function _checkResumeButton() {
  const saved = _loadFromLocalStorage();
  if (!saved || !saved.report) return;
  const btn = document.getElementById("resume-btn");
  if (!btn) return;
  const label = saved.query ? `Resume: "${saved.query.slice(0, 50)}${saved.query.length > 50 ? "…" : ""}"` : "Resume last analysis";
  btn.textContent = label;
  btn.classList.remove("hidden");
}

function resumeLastAnalysis() {
  const saved = _loadFromLocalStorage();
  if (!saved || !saved.report) return;

  lastQuery = saved.query || "";
  lastCritic = saved.critic || null;
  lastElapsed = 0;

  document.getElementById("swarm-section").classList.remove("hidden");
  document.getElementById("revision-banner").classList.add("hidden");

  if (lastCritic) {
    showCriticResult(lastCritic);
    if (lastCritic.status !== "APPROVED") {
      document.getElementById("revision-banner").classList.remove("hidden");
    }
  }
  renderReport(saved.report);

  const btn = document.getElementById("resume-btn");
  if (btn) btn.classList.add("hidden");
}

// -- Helpers ----------------------------------------
function _esc(str) {
  return String(str == null ? "" : str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function _fmtDate(isoStr) {
  if (!isoStr) return "";
  try { return new Date(isoStr).toLocaleString(); } catch { return isoStr; }
}

// -- DOMContentLoaded ----------------------------------------
document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("query").addEventListener("keydown", e => {
    if (e.key === "Enter") launchSwarm();
  });

  const isLight = document.documentElement.getAttribute("data-theme") === "light";
  const tbtn = document.getElementById("theme-toggle");
  if (tbtn) tbtn.textContent = isLight ? "☀️" : "🌙";

  renderExampleChips();
  _checkResumeButton();
  waitForServerHealth();
  initAuth();
  _resetThoughts();

  const yearEl = document.getElementById("footer-year");
  if (yearEl) yearEl.textContent = new Date().getFullYear();
});
