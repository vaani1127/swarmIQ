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

const SESSION_ID = Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
const API_BASE = location.origin;
const WS_BASE = (location.protocol === "https:" ? "wss:" : "ws:") + "//" + location.host;

let ws = null;
let reportText = "";
let lastQuery = "";
let lastCritic = null;
let lastElapsed = 0;
let timerStart = 0;
let timerInterval = null;

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

function updateAgentCard(agentName, status, message) {
  const card = document.querySelector('[data-agent="' + agentName + '"]');
  if (!card) return;

  const statusEl = card.querySelector(".agent-status");

  card.classList.remove("working", "done", "idle");

  if (status === "done") {
    card.classList.add("done");
    statusEl.textContent = "✓ Complete";
  } else if (status === "working" || status === "started") {
    card.classList.add("working");
    statusEl.textContent = message || status;
  } else {
    statusEl.textContent = message || status;
  }
}

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

function launchSwarm() {
  const query = document.getElementById("query").value.trim();
  if (!query) {
    alert("Please enter a research query");
    return;
  }
  lastQuery = query;
  lastCritic = null;

  const btn = document.getElementById("launch-btn");
  btn.disabled = true;
  btn.textContent = "Launching...";

  document.getElementById("swarm-section").classList.remove("hidden");

  document.querySelectorAll(".agent-card").forEach(card => {
    card.classList.remove("working", "done", "idle");
    card.querySelector(".agent-status").textContent = "Waiting...";
  });

  document.getElementById("critic-section").classList.add("hidden");
  document.getElementById("report-section").classList.add("hidden");
  document.getElementById("revision-banner").classList.add("hidden");

  startTimer();
  ws = new WebSocket(WS_BASE + "/ws/" + SESSION_ID);

  ws.onopen = () => {
    setTimeout(() => {
      const formData = new FormData();
      formData.append("query", query);
      formData.append("session_id", SESSION_ID);

      fetch(API_BASE + "/analyze", {
        method: "POST",
        body: formData,
      });
    }, 400);
  };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    if (data.agent === "SYSTEM" && data.status === "complete") {
      lastElapsed = (performance.now() - timerStart) / 1000;
      stopTimer();
      lastCritic = data.critic || null;
      showCriticResult(data.critic);
      if (data.critic && data.critic.status !== "APPROVED") {
        document.getElementById("revision-banner").classList.remove("hidden");
      }
      renderReport(data.report);
      btn.disabled = false;
      btn.textContent = "Launch Swarm ↗";
    } else {
      updateAgentCard(data.agent, data.status, data.message);
    }
  };

  ws.onerror = () => {
    stopTimer();
    alert("Connection error. Is the backend running on port 8000?");
    btn.disabled = false;
    btn.textContent = "Launch Swarm ↗";
  };
}

function copyReport() {
  navigator.clipboard.writeText(reportText);
  const btn = document.querySelector(".report-actions .download-btn");
  btn.textContent = "Copied! ✓";
  setTimeout(() => {
    btn.textContent = "Copy Report ↗";
  }, 2000);
}

async function downloadPDF() {
  const source = document.getElementById("report-content");
  if (!source || !source.innerHTML.trim()) return;

  const btn = document.getElementById("pdf-btn");
  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Generating...";

  const esc = (s) => String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  const wrapper = document.createElement("div");
  wrapper.style.cssText =
    "position:fixed;left:-10000px;top:0;width:780px;padding:48px 56px;" +
    "background:#0f0f17;color:#e2e8f0;" +
    "font-family:'Segoe UI',system-ui,-apple-system,sans-serif;font-size:14px;line-height:1.75;";

  const isApproved = lastCritic && lastCritic.status === "APPROVED";
  const verdictColor = isApproved ? "#22c55e" : "#ef4444";
  const verdictLabel = isApproved ? "APPROVED" : "NEEDS REVISION";
  const verdictBg = isApproved ? "rgba(34,197,94,0.12)" : "rgba(239,68,68,0.12)";
  const confidence = (lastCritic && lastCritic.overall_confidence) || "—";
  const elapsedStr = lastElapsed > 0 ? lastElapsed.toFixed(1) + "s" : "—";

  const banner = !isApproved && lastCritic
    ? `<div style="background:${verdictBg};border-left:3px solid ${verdictColor};
         padding:10px 14px;margin:0 0 20px;border-radius:6px;font-size:12px;color:#fca5a5;">
         <strong style="color:${verdictColor};">⚠ Critic flagged this report for revision.</strong>
         Read the Quality Review section before relying on these findings.
       </div>`
    : "";

  const criticNotes = lastCritic && lastCritic.notes
    ? `<div style="margin-top:10px;font-size:12px;color:#94a3b8;line-height:1.6;">
         <em>${esc(lastCritic.notes)}</em>
       </div>` : "";

  wrapper.innerHTML = `
    <div style="border-bottom:2px solid #1e1e2e;padding-bottom:20px;margin-bottom:24px;">
      <div style="display:flex;align-items:baseline;justify-content:space-between;gap:16px;">
        <h1 style="color:#ffffff;font-size:26px;margin:0;font-weight:700;letter-spacing:-0.02em;">
          Swarm<span style="color:#5b5ef4;">IQ</span> Intelligence Report
        </h1>
        <span style="background:${verdictBg};color:${verdictColor};
          padding:4px 10px;border-radius:999px;font-size:11px;font-weight:600;
          letter-spacing:0.04em;white-space:nowrap;">${verdictLabel}</span>
      </div>
      <div style="margin-top:16px;display:grid;grid-template-columns:repeat(3,1fr);gap:14px;
        font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.06em;">
        <div><div style="opacity:0.7;">Generated</div>
          <div style="color:#e2e8f0;text-transform:none;letter-spacing:0;margin-top:2px;font-size:12px;">
            ${esc(new Date().toLocaleString())}
          </div>
        </div>
        <div><div style="opacity:0.7;">Confidence</div>
          <div style="color:#e2e8f0;text-transform:none;letter-spacing:0;margin-top:2px;font-size:12px;">
            ${esc(confidence)}
          </div>
        </div>
        <div><div style="opacity:0.7;">Elapsed</div>
          <div style="color:#e2e8f0;text-transform:none;letter-spacing:0;margin-top:2px;font-size:12px;">
            ${esc(elapsedStr)}
          </div>
        </div>
      </div>
    </div>

    <div style="background:#13131a;border:1px solid #1e1e2e;border-radius:10px;padding:16px 18px;margin-bottom:24px;">
      <div style="font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;">
        Research Query
      </div>
      <div style="color:#ffffff;font-size:15px;font-weight:500;line-height:1.5;">
        ${esc(lastQuery || "—")}
      </div>
    </div>

    ${banner}
  `;

  const clone = source.cloneNode(true);
  clone.querySelectorAll("h2").forEach(h => {
    h.style.cssText =
      "color:#ffffff;font-size:17px;margin:28px 0 10px;padding-bottom:8px;" +
      "border-bottom:1px solid #1e1e2e;font-weight:600;letter-spacing:-0.01em;";
  });
  clone.querySelectorAll("strong").forEach(s => {
    s.style.color = "#ffffff";
  });
  clone.querySelectorAll("br + br").forEach(br => br.remove());
  wrapper.appendChild(clone);

  if (lastCritic && lastCritic.notes) {
    const criticBlock = document.createElement("div");
    criticBlock.style.cssText =
      "margin-top:32px;padding:16px 18px;background:#13131a;" +
      "border:1px solid #1e1e2e;border-radius:10px;";
    criticBlock.innerHTML = `
      <div style="font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;">
        Critic Notes
      </div>
      <div style="color:#e2e8f0;font-size:13px;line-height:1.6;">${esc(lastCritic.notes)}</div>
    `;
    wrapper.appendChild(criticBlock);
  }

  const footer = document.createElement("div");
  footer.style.cssText =
    "margin-top:40px;padding-top:16px;border-top:1px solid #1e1e2e;" +
    "font-size:10px;color:#64748b;text-align:center;letter-spacing:0.05em;";
  footer.textContent = "Generated by SwarmIQ — six AI agents, one intelligence report";
  wrapper.appendChild(footer);

  document.body.appendChild(wrapper);

  try {
    const canvas = await html2canvas(wrapper, {
      backgroundColor: "#0f0f17",
      scale: 2,
      useCORS: true,
    });
    document.body.removeChild(wrapper);

    const { jsPDF } = window.jspdf;
    const pdf = new jsPDF("p", "mm", "a4");
    const pageW = pdf.internal.pageSize.getWidth();
    const pageH = pdf.internal.pageSize.getHeight();
    const imgW = pageW;
    const imgH = (canvas.height * imgW) / canvas.width;
    const imgData = canvas.toDataURL("image/png");

    let heightLeft = imgH;
    let position = 0;
    pdf.setFillColor(15, 15, 23);
    pdf.rect(0, 0, pageW, pageH, "F");
    pdf.addImage(imgData, "PNG", 0, position, imgW, imgH);
    heightLeft -= pageH;

    while (heightLeft > 0) {
      position -= pageH;
      pdf.addPage();
      pdf.setFillColor(15, 15, 23);
      pdf.rect(0, 0, pageW, pageH, "F");
      pdf.addImage(imgData, "PNG", 0, position, imgW, imgH);
      heightLeft -= pageH;
    }

    pdf.save("swarmiq-report.pdf");
  } catch (err) {
    console.error("PDF generation failed", err);
    alert("PDF generation failed. Check console.");
    if (wrapper.parentNode) wrapper.parentNode.removeChild(wrapper);
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("query").addEventListener("keydown", e => {
    if (e.key === "Enter") launchSwarm();
  });
  const isLight = document.documentElement.getAttribute("data-theme") === "light";
  const tbtn = document.getElementById("theme-toggle");
  if (tbtn) tbtn.textContent = isLight ? "☀️" : "🌙";
  renderExampleChips();
});
