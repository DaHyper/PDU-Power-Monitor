const STATUS_LABELS = {
  ok: "Normal",
  warning: "Warning",
  critical: "Danger",
  unknown: "Unknown",
};

let pollTimer = null;

async function fetchStatus() {
  const res = await fetch("/api/status");
  if (!res.ok) throw new Error("Failed to fetch status");
  return res.json();
}

function formatKw(value) {
  if (value == null) return "—";
  return value.toFixed(2);
}

function renderRackCard(rack) {
  const status = rack.status || "unknown";
  const pct = rack.percent_of_limit ?? 0;
  const barWidth = Math.min(pct, 100);

  const pduHtml = rack.pdus
    .map((pdu) => {
      const cls = pdu.status === "unreachable" ? "unreachable" : pdu.status === "stale" ? "stale" : "";
      const power = pdu.power_kw != null ? `${formatKw(pdu.power_kw)} kW` : "—";
      const err = pdu.error ? `<div class="pdu-error">${pdu.error}</div>` : "";
      return `
        <div class="pdu-item ${cls}">
          <div class="pdu-item-header">
            <span>🔗</span> ${pdu.name}
          </div>
          <div class="pdu-power">${power}</div>
          <div class="pdu-host">${pdu.host}</div>
          ${err}
        </div>`;
    })
    .join("");

  return `
    <div class="rack-card status-${status}">
      <div class="rack-header">
        <div>
          <div class="rack-name">${rack.name}</div>
          <div class="rack-description">${rack.description || rack.location || ""}</div>
        </div>
        <span class="status-badge ${status}">${STATUS_LABELS[status] || status}</span>
      </div>
      <div class="rack-power">
        <span class="power-value ${status}">${formatKw(rack.power_kw)}</span>
        <span class="power-limit"> kW / ${formatKw(rack.critical_kw)} kW limit</span>
      </div>
      <div class="progress-bar">
        <div class="progress-fill ${status}" style="width: ${barWidth}%"></div>
      </div>
      <div class="rack-meta">
        <span>${pct}% of limit</span>
        <span class="headroom ${status}">${formatKw(rack.headroom_kw)} kW headroom</span>
      </div>
      <div class="pdu-list">${pduHtml}</div>
    </div>`;
}

function renderCombinedView(racks) {
  const section = document.getElementById("combined-view");
  if (!racks.length) {
    section.hidden = true;
    return;
  }
  section.hidden = false;

  const maxCritical = Math.max(...racks.map((r) => r.critical_kw));
  const maxWarning = Math.max(...racks.map((r) => r.warning_kw));
  const totalKw = racks.reduce((sum, r) => sum + (r.power_kw || 0), 0);

  const rackParts = racks
    .map((r) => `${r.name} <strong>${formatKw(r.power_kw)} kW</strong>`)
    .join(" · ");

  document.getElementById("combined-summary").innerHTML =
    `${rackParts} · Warn at <strong>${formatKw(maxWarning)} kW</strong> · Limit <span class="limit">${formatKw(maxCritical)} kW</span>`;

  const scaleMax = maxCritical * 1.2;
  const warnPct = (maxWarning / scaleMax) * 100;
  const critPct = ((maxCritical - maxWarning) / scaleMax) * 100;
  const okPct = 100 - warnPct - critPct;

  const track = document.getElementById("gauge-track");
  track.querySelector(".gauge-zone-ok").style.width = `${okPct}%`;
  track.querySelector(".gauge-zone-warn").style.width = `${warnPct}%`;
  track.querySelector(".gauge-zone-critical").style.width = `${critPct}%`;

  const markerPct = (maxCritical / scaleMax) * 100;
  const marker = document.getElementById("gauge-marker");
  marker.style.left = `${markerPct}%`;
  document.getElementById("gauge-limit-label").style.left = `${markerPct}%`;
  document.getElementById("gauge-limit-label").textContent = `${formatKw(maxCritical)} kW`;

  const arrowPct = Math.min((totalKw / scaleMax) * 100, 100);
  document.getElementById("gauge-arrow").style.left = `${arrowPct}%`;
}

function updateHeader(racks, interval) {
  const pduCount = racks.reduce((n, r) => n + r.pdus.length, 0);
  document.getElementById("header-subtitle").textContent =
    `APC AP8841 · ${racks.length} rack${racks.length !== 1 ? "s" : ""} · ${pduCount} PDU${pduCount !== 1 ? "s" : ""}`;
  document.getElementById("poll-interval").textContent = interval;
}

function updateLastPoll(iso) {
  const el = document.getElementById("last-poll");
  if (!iso) {
    el.textContent = "Last poll: —";
    return;
  }
  const d = new Date(iso);
  el.textContent = `Last poll: ${d.toLocaleString()}`;
}

function render(data) {
  const grid = document.getElementById("rack-grid");
  if (!data.racks || !data.racks.length) {
    grid.innerHTML = '<p class="loading">No racks configured. <a href="/config" style="color:var(--blue)">Add PDUs</a>.</p>';
    return;
  }
  grid.innerHTML = data.racks.map(renderRackCard).join("");
  renderCombinedView(data.racks);
  updateHeader(data.racks, data.poll_interval_seconds);
  updateLastPoll(data.last_poll);
  schedulePoll(data.poll_interval_seconds);
}

function schedulePoll(intervalSeconds) {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      const data = await fetchStatus();
      render(data);
    } catch (_) { /* silent retry next interval */ }
  }, intervalSeconds * 1000);
}

async function init() {
  try {
    const data = await fetchStatus();
    render(data);
  } catch (err) {
    document.getElementById("rack-grid").innerHTML =
      `<p class="loading">Error loading data: ${err.message}</p>`;
  }
}

document.getElementById("refresh-btn").addEventListener("click", async () => {
  const btn = document.getElementById("refresh-btn");
  btn.disabled = true;
  try {
    const res = await fetch("/api/refresh", { method: "POST" });
    const data = await res.json();
    render(data);
  } finally {
    btn.disabled = false;
  }
});

init();
