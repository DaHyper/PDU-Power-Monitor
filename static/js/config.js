const RACK_COLORS = ["#3dd68c", "#4da6ff", "#f5a623", "#c084fc", "#f472b6"];

let config = null;
let recipients = [];
let pduRows = [];

async function loadConfig() {
  const res = await fetch("/api/config");
  if (!res.ok) throw new Error("Failed to load config");
  config = await res.json();
  recipients = [...(config.smtp.recipients || [])];
  buildPduRows();
  render();
}

function buildPduRows() {
  pduRows = [];
  (config.racks || []).forEach((rack, rackIdx) => {
    (rack.pdus || []).forEach((pdu, pduIdx) => {
      pduRows.push({
        rackIdx,
        pduIdx,
        rackName: rack.name,
        rackDescription: rack.description ?? rack.location ?? "",
        warningKw: rack.warning_kw,
        criticalKw: rack.critical_kw,
        ...pdu,
        testStatus: "pending",
        testError: null,
      });
    });
  });
}

function renderPduTable() {
  const tbody = document.getElementById("pdu-tbody");
  tbody.innerHTML = pduRows
    .map((row, i) => {
      const color = RACK_COLORS[row.rackIdx % RACK_COLORS.length];
      const statusCls = row.testStatus === "ok" ? "ok" : row.testStatus === "fail" ? "fail" : "pending";
      const statusLabel =
        row.testStatus === "ok" ? "✓ OK" : row.testStatus === "fail" ? "✗ Timeout" : "—";
      return `
        <tr data-row="${i}">
          <td><span class="rack-dot" style="background:${color}"></span></td>
          <td><input type="text" class="pdu-name" value="${esc(row.name)}"></td>
          <td>
            <select class="pdu-rack">
              ${(config.racks || []).map((r, ri) =>
                `<option value="${ri}" ${ri === row.rackIdx ? "selected" : ""}>${esc(r.name)}</option>`
              ).join("")}
            </select>
          </td>
          <td><input type="text" class="pdu-host" value="${esc(row.host)}"></td>
          <td><input type="text" class="pdu-community" value="${esc(row.community)}"></td>
          <td><span class="conn-status ${statusCls}">${statusLabel}</span></td>
          <td><button class="btn btn-danger btn-sm remove-pdu" type="button">✕</button></td>
        </tr>`;
    })
    .join("");

  tbody.querySelectorAll(".remove-pdu").forEach((btn) => {
    btn.addEventListener("click", () => {
      const idx = parseInt(btn.closest("tr").dataset.row, 10);
      pduRows.splice(idx, 1);
      syncRowsToConfig();
      buildPduRows();
      renderPduTable();
      renderThresholds();
    });
  });
}

function renderThresholds() {
  const grid = document.getElementById("threshold-grid");
  grid.innerHTML = (config.racks || [])
    .map(
      (rack, i) => `
      <div class="threshold-rack" data-rack="${i}">
        <div class="form-row">
          <label>
            Rack name
            <input type="text" class="rack-name" value="${esc(rack.name)}" placeholder="Rack A">
          </label>
          <label>
            Description
            <input type="text" class="rack-description" value="${esc(rack.description ?? rack.location ?? "")}" placeholder="Row 1 · Slots 1-2">
            <span class="hint">Shown below the rack name on the dashboard</span>
          </label>
        </div>
        <div class="form-row">
          <label>
            Warning threshold (kW)
            <input type="number" class="rack-warning" step="0.01" value="${rack.warning_kw}">
            <span class="hint">Sends first alert, highlights rack amber</span>
          </label>
          <label>
            Critical threshold (kW)
            <input type="number" class="rack-critical" step="0.01" value="${rack.critical_kw}">
            <span class="hint">Sends urgent alert, highlights rack red</span>
          </label>
        </div>
      </div>`
    )
    .join("");
}

function renderRecipients() {
  const wrap = document.getElementById("recipients-wrap");
  wrap.innerHTML = recipients
    .map(
      (email, i) => `
      <span class="recipient-chip">
        ${esc(email)}
        <button type="button" data-idx="${i}" class="remove-recipient">×</button>
      </span>`
    )
    .join("");

  wrap.querySelectorAll(".remove-recipient").forEach((btn) => {
    btn.addEventListener("click", () => {
      recipients.splice(parseInt(btn.dataset.idx, 10), 1);
      renderRecipients();
    });
  });
}

function renderWebhooks() {
  if (!config.webhooks) config.webhooks = [];
  const list = document.getElementById("webhook-list");
  if (!config.webhooks.length) {
    list.innerHTML = '<p class="hint">No webhooks configured. Add one for Slack, Discord, or a custom endpoint.</p>';
    return;
  }
  list.innerHTML = config.webhooks
    .map(
      (wh, i) => `
      <div class="webhook-item" data-webhook="${i}">
        <div class="webhook-item-header">
          <label>
            <input type="checkbox" class="webhook-enabled" ${wh.enabled !== false ? "checked" : ""}>
            Enabled
          </label>
          <button class="btn btn-danger btn-sm remove-webhook" type="button">Remove</button>
        </div>
        <div class="form-stack">
          <label>
            Name
            <input type="text" class="webhook-name" value="${esc(wh.name || "")}" placeholder="Ops Slack">
          </label>
          <label>
            Webhook URL
            <input type="url" class="webhook-url" value="${esc(wh.url || "")}" placeholder="https://hooks.slack.com/services/...">
          </label>
          <label>
            Format
            <select class="webhook-format">
              <option value="generic" ${wh.format === "generic" ? "selected" : ""}>Generic JSON</option>
              <option value="slack" ${wh.format === "slack" ? "selected" : ""}>Slack</option>
              <option value="discord" ${wh.format === "discord" ? "selected" : ""}>Discord</option>
            </select>
            <span class="hint">Slack/Discord use incoming webhook URLs from those services</span>
          </label>
        </div>
      </div>`
    )
    .join("");

  list.querySelectorAll(".remove-webhook").forEach((btn) => {
    btn.addEventListener("click", () => {
      const idx = parseInt(btn.closest(".webhook-item").dataset.webhook, 10);
      config.webhooks.splice(idx, 1);
      renderWebhooks();
    });
  });
}

function syncWebhooksFromForm() {
  if (!config.webhooks) config.webhooks = [];
  config.webhooks = [];
  document.querySelectorAll(".webhook-item").forEach((el) => {
    config.webhooks.push({
      name: el.querySelector(".webhook-name").value.trim(),
      url: el.querySelector(".webhook-url").value.trim(),
      format: el.querySelector(".webhook-format").value,
      enabled: el.querySelector(".webhook-enabled").checked,
    });
  });
}

function toggleSnmpV3Panel() {
  const version = document.getElementById("snmp-version").value;
  document.getElementById("snmp-v3-panel").hidden = version !== "3";
}

function isoToLocalInput(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function localInputToIso(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  return d.toISOString();
}

function renderMaintenance() {
  const m = config.maintenance || {};
  document.getElementById("maintenance-enabled").checked = !!m.enabled;
  document.getElementById("maintenance-silence").checked = m.silence_alerts !== false;
  document.getElementById("maintenance-message").value = m.message || "";
  document.getElementById("maintenance-until").value = isoToLocalInput(m.until);
}

function syncMaintenanceFromForm() {
  if (!config.maintenance) config.maintenance = {};
  config.maintenance.enabled = document.getElementById("maintenance-enabled").checked;
  config.maintenance.silence_alerts = document.getElementById("maintenance-silence").checked;
  config.maintenance.message = document.getElementById("maintenance-message").value;
  const until = localInputToIso(document.getElementById("maintenance-until").value);
  config.maintenance.until = until || null;
}

function renderSnmp() {
  const snmp = config.snmp || {};
  const v3 = snmp.v3 || {};
  document.getElementById("snmp-version").value = snmp.version || "2c";
  document.getElementById("energy-oid").value = snmp.energy_oid || "";
  document.getElementById("v3-username").value = v3.username || "";
  document.getElementById("v3-security-level").value = v3.security_level || "authPriv";
  document.getElementById("v3-auth-password").value = "";
  document.getElementById("v3-auth-protocol").value = v3.auth_protocol || "SHA";
  document.getElementById("v3-priv-password").value = "";
  document.getElementById("v3-priv-protocol").value = v3.priv_protocol || "AES";
  toggleSnmpV3Panel();
}

function syncSnmpFromForm() {
  config.snmp.version = document.getElementById("snmp-version").value;
  config.snmp.energy_oid = document.getElementById("energy-oid").value;
  if (!config.snmp.v3) config.snmp.v3 = {};
  config.snmp.v3.username = document.getElementById("v3-username").value;
  config.snmp.v3.security_level = document.getElementById("v3-security-level").value;
  config.snmp.v3.auth_protocol = document.getElementById("v3-auth-protocol").value;
  config.snmp.v3.priv_protocol = document.getElementById("v3-priv-protocol").value;
  const authPw = document.getElementById("v3-auth-password").value;
  const privPw = document.getElementById("v3-priv-password").value;
  if (authPw) config.snmp.v3.auth_password = authPw;
  if (privPw) config.snmp.v3.priv_password = privPw;
}

function render() {
  document.getElementById("poll-interval").value = config.poll_interval_seconds;
  document.getElementById("alert-cooldown").value = config.alert_cooldown_minutes;
  document.getElementById("power-oid").value = config.snmp.power_oid;
  document.getElementById("power-divisor").value = config.snmp.power_divisor;

  renderSnmp();
  renderMaintenance();

  document.getElementById("smtp-host").value = config.smtp.host || "";
  document.getElementById("smtp-port").value = config.smtp.port || 587;
  document.getElementById("smtp-security").value = config.smtp.security || "tls";
  document.getElementById("smtp-username").value = config.smtp.username || "";
  document.getElementById("smtp-password").value = "";
  document.getElementById("smtp-from").value = config.smtp.from_address || "";

  renderPduTable();
  renderThresholds();
  renderWebhooks();
  renderRecipients();
}

function syncRowsToConfig() {
  const racks = (config.racks || []).map((r) => ({
    name: r.name,
    description: r.description ?? r.location ?? "",
    warning_kw: r.warning_kw,
    critical_kw: r.critical_kw,
    pdus: [],
  }));

  pduRows.forEach((row) => {
    if (!racks[row.rackIdx]) return;
    racks[row.rackIdx].pdus.push({
      name: row.name,
      host: row.host,
      community: row.community,
    });
  });

  config.racks = racks;
}

function readFormIntoConfig() {
  syncRowsFromTable();
  syncThresholdsFromForm();
  syncWebhooksFromForm();
  syncMaintenanceFromForm();
  syncSnmpFromForm();

  config.poll_interval_seconds = parseInt(document.getElementById("poll-interval").value, 10);
  config.alert_cooldown_minutes = parseInt(document.getElementById("alert-cooldown").value, 10);
  config.snmp.power_oid = document.getElementById("power-oid").value;
  config.snmp.power_divisor = parseFloat(document.getElementById("power-divisor").value);

  config.smtp.host = document.getElementById("smtp-host").value;
  config.smtp.port = parseInt(document.getElementById("smtp-port").value, 10);
  config.smtp.security = document.getElementById("smtp-security").value;
  config.smtp.username = document.getElementById("smtp-username").value;
  const pw = document.getElementById("smtp-password").value;
  if (pw) config.smtp.password = pw;
  config.smtp.from_address = document.getElementById("smtp-from").value;
  config.smtp.recipients = [...recipients];
}

function syncRowsFromTable() {
  const tbody = document.getElementById("pdu-tbody");
  tbody.querySelectorAll("tr").forEach((tr) => {
    const idx = parseInt(tr.dataset.row, 10);
    const row = pduRows[idx];
    if (!row) return;
    row.name = tr.querySelector(".pdu-name").value;
    row.rackIdx = parseInt(tr.querySelector(".pdu-rack").value, 10);
    row.host = tr.querySelector(".pdu-host").value;
    row.community = tr.querySelector(".pdu-community").value;
  });
  syncRowsToConfig();
}

function syncThresholdsFromForm() {
  document.querySelectorAll(".threshold-rack").forEach((el) => {
    const idx = parseInt(el.dataset.rack, 10);
    config.racks[idx].name = el.querySelector(".rack-name").value.trim() || `Rack ${idx + 1}`;
    config.racks[idx].description = el.querySelector(".rack-description").value;
    config.racks[idx].warning_kw = parseFloat(el.querySelector(".rack-warning").value);
    config.racks[idx].critical_kw = parseFloat(el.querySelector(".rack-critical").value);
  });
}

function showStatus(msg, ok) {
  const el = document.getElementById("save-status");
  el.textContent = msg;
  el.className = `save-status ${ok ? "success" : "error"}`;
  el.hidden = false;
  setTimeout(() => { el.hidden = true; }, 4000);
}

function esc(str) {
  const d = document.createElement("div");
  d.textContent = str;
  return d.innerHTML;
}

document.getElementById("save-btn").addEventListener("click", async () => {
  readFormIntoConfig();
  const res = await fetch("/api/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  const data = await res.json();
  if (res.ok) {
    config = data.config;
    buildPduRows();
    render();
    showStatus("Configuration saved.", true);
  } else {
    showStatus(data.detail || "Save failed.", false);
  }
});

document.getElementById("test-all-btn").addEventListener("click", async () => {
  syncRowsFromTable();
  readFormIntoConfig();
  const btn = document.getElementById("test-all-btn");
  btn.disabled = true;
  pduRows.forEach((r) => { r.testStatus = "pending"; });
  renderPduTable();

  const res = await fetch("/api/test/pdu/all", { method: "POST" });
  const data = await res.json();

  data.results.forEach((result) => {
    const row = pduRows.find((r) => r.host === result.host && r.name === result.name);
    if (row) {
      row.testStatus = result.ok ? "ok" : "fail";
      row.testError = result.error;
    }
  });
  renderPduTable();
  btn.disabled = false;
});

document.getElementById("add-rack-btn").addEventListener("click", () => {
  syncRowsFromTable();
  syncThresholdsFromForm();
  const letter = String.fromCharCode(65 + config.racks.length);
  config.racks.push({
    name: `Rack ${letter}`,
    description: "",
    warning_kw: 2.5,
    critical_kw: 3.0,
    pdus: [],
  });
  buildPduRows();
  renderPduTable();
  renderThresholds();
});

document.getElementById("add-pdu-btn").addEventListener("click", () => {
  syncRowsFromTable();
  syncThresholdsFromForm();
  if (!config.racks.length) {
    config.racks.push({
      name: "Rack A",
      description: "",
      warning_kw: 2.5,
      critical_kw: 3.0,
      pdus: [],
    });
  }
  const rackIdx = 0;
  pduRows.push({
    rackIdx,
    pduIdx: config.racks[rackIdx].pdus.length,
    rackName: config.racks[rackIdx].name,
    name: `PDU ${pduRows.length + 1}`,
    host: "10.0.0.1",
    community: "public",
    testStatus: "pending",
  });
  syncRowsToConfig();
  buildPduRows();
  renderPduTable();
  renderThresholds();
});

document.getElementById("add-recipient-btn").addEventListener("click", () => {
  const input = document.getElementById("recipient-input");
  const email = input.value.trim();
  if (email && !recipients.includes(email)) {
    recipients.push(email);
    renderRecipients();
  }
  input.value = "";
});

document.getElementById("add-webhook-btn").addEventListener("click", () => {
  syncWebhooksFromForm();
  if (!config.webhooks) config.webhooks = [];
  config.webhooks.push({
    name: "",
    url: "",
    format: "slack",
    enabled: true,
  });
  renderWebhooks();
});

document.getElementById("test-webhooks-btn").addEventListener("click", async () => {
  readFormIntoConfig();
  await fetch("/api/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  const res = await fetch("/api/test/webhooks", { method: "POST" });
  const data = await res.json();
  showStatus(res.ok ? "Test webhook sent." : (data.detail || "Webhook test failed."), res.ok);
});

document.getElementById("snmp-version").addEventListener("change", toggleSnmpV3Panel);

document.getElementById("export-config-btn").addEventListener("click", () => {
  window.location.href = "/api/config/export";
});

document.getElementById("import-config-input").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  const res = await fetch("/api/config/import", { method: "POST", body: form });
  const data = await res.json();
  if (res.ok) {
    config = data.config;
    buildPduRows();
    render();
    showStatus("Configuration imported.", true);
  } else {
    showStatus(data.detail || "Import failed.", false);
  }
  e.target.value = "";
});

document.getElementById("test-smtp-btn").addEventListener("click", async () => {
  readFormIntoConfig();
  await fetch("/api/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  const res = await fetch("/api/test/smtp", { method: "POST" });
  const data = await res.json();
  showStatus(res.ok ? "Test email sent." : (data.detail || "SMTP test failed."), res.ok);
});

loadConfig().catch((err) => showStatus(err.message, false));
