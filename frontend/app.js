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
      stopTimer();
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

  const wrapper = document.createElement("div");
  wrapper.style.cssText =
    "position:fixed;left:-10000px;top:0;width:760px;padding:40px;" +
    "background:#13131a;color:#e2e8f0;" +
    "font-family:system-ui,sans-serif;font-size:14px;line-height:1.8;";

  const heading = document.createElement("h1");
  heading.textContent = "SwarmIQ Intelligence Report";
  heading.style.cssText =
    "color:#ffffff;font-size:24px;margin:0 0 8px;font-weight:700;";
  const sub = document.createElement("div");
  sub.textContent = new Date().toLocaleString();
  sub.style.cssText = "color:var(--muted);font-size:12px;margin-bottom:24px;";
  wrapper.appendChild(heading);
  wrapper.appendChild(sub);

  const clone = source.cloneNode(true);
  clone.querySelectorAll("h2").forEach(h => {
    h.style.cssText =
      "color:#ffffff;font-size:18px;margin:24px 0 10px;padding-bottom:6px;" +
      "border-bottom:1px solid #1e1e2e;font-weight:600;";
  });
  clone.querySelectorAll("strong").forEach(s => {
    s.style.color = "#ffffff";
  });
  wrapper.appendChild(clone);
  document.body.appendChild(wrapper);

  try {
    const canvas = await html2canvas(wrapper, {
      backgroundColor: "#13131a",
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
    pdf.setFillColor(19, 19, 26);
    pdf.rect(0, 0, pageW, pageH, "F");
    pdf.addImage(imgData, "PNG", 0, position, imgW, imgH);
    heightLeft -= pageH;

    while (heightLeft > 0) {
      position -= pageH;
      pdf.addPage();
      pdf.setFillColor(19, 19, 26);
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
});
