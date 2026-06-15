const ui = {
  url: document.getElementById("url"),
  statusText: document.getElementById("status-text"),
  statusPill: document.getElementById("status-pill"),
  startBtn: document.getElementById("start-btn"),
  refreshBtn: document.getElementById("refresh-btn"),
  message: document.getElementById("message"),
  queue: document.getElementById("queue"),
  queueCount: document.getElementById("queue-count"),
  downloads: document.getElementById("downloads"),
  downloadCount: document.getElementById("download-count"),
};

let startRequestRunning = false;

function selectedMode() {
  return document.querySelector('input[name="mode"]:checked')?.value || "video";
}

function setMessage(text, kind = "") {
  ui.message.textContent = text || "";
  ui.message.className = `message ${kind}`.trim();
}

function formatBytes(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  if (n >= 1024 * 1024 * 1024) return `${(n / 1024 / 1024 / 1024).toLocaleString("de-DE", { maximumFractionDigits: 2 })} GB`;
  if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toLocaleString("de-DE", { maximumFractionDigits: 1 })} MB`;
  if (n >= 1024) return `${(n / 1024).toLocaleString("de-DE", { maximumFractionDigits: 1 })} KB`;
  return `${n.toLocaleString("de-DE")} B`;
}

function formatDate(epochSeconds) {
  const n = Number(epochSeconds);
  if (!Number.isFinite(n) || n <= 0) return "-";
  return new Date(n * 1000).toLocaleString("de-DE");
}

async function apiGet(url) {
  const res = await fetch(url);
  const text = await res.text();
  const data = text ? JSON.parse(text) : {};
  if (!res.ok) throw new Error(data.error || text || res.statusText);
  return data;
}

async function apiPost(url, payload) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : {};
  if (!res.ok) throw new Error(data.error || text || res.statusText);
  return data;
}

async function pollStatus() {
  try {
    const state = await apiGet("/api/status");
    const status = state.status || "Bereit.";
    ui.statusText.textContent = status;
    ui.statusPill.textContent = status;
    ui.startBtn.disabled = startRequestRunning;
    renderQueue(state);
    if (state.last_error) setMessage(state.last_error, "error");
    if (!state.running && state.files && state.files.length && !startRequestRunning) {
      setMessage(`Fertig: ${state.files.join(", ")}`, "ok");
    }
  } catch (err) {
    ui.statusText.textContent = "Server nicht erreichbar.";
    ui.statusPill.textContent = "Server nicht erreichbar.";
  } finally {
    window.setTimeout(pollStatus, 900);
  }
}

function renderQueue(state) {
  const current = state.current_job;
  const queued = state.queued_jobs || [];
  const recent = state.recent_jobs || [];
  ui.queueCount.textContent = `${queued.length.toLocaleString("de-DE")} wartend`;

  const blocks = [];
  if (current) {
    blocks.push(jobHtml(current, "Laeuft"));
  }
  for (const job of queued) {
    blocks.push(jobHtml(job, "Wartet"));
  }
  for (const job of recent.slice(0, 3)) {
    blocks.push(jobHtml(job, job.state === "error" ? "Fehler" : "Fertig"));
  }

  if (!blocks.length) {
    ui.queue.innerHTML = '<div class="empty">Keine Jobs in der Queue.</div>';
    return;
  }
  ui.queue.innerHTML = `<div class="job-list">${blocks.join("")}</div>`;
}

function jobHtml(job, stateText) {
  const files = job.files && job.files.length ? `<div class="muted">Dateien: ${escapeHtml(job.files.join(", "))}</div>` : "";
  const error = job.error ? `<div class="message error">${escapeHtml(job.error)}</div>` : "";
  return [
    '<div class="job">',
    '<div class="job-top">',
    `<div class="job-title">${escapeHtml(job.label || job.url || job.id)}</div>`,
    `<span class="badge">${escapeHtml(stateText)} / ${escapeHtml(job.mode || "-")}</span>`,
    "</div>",
    `<div class="muted">${escapeHtml(job.status || "")}</div>`,
    files,
    error,
    "</div>",
  ].join("");
}

function renderDownloads(items) {
  const rows = items || [];
  ui.downloadCount.textContent = `${rows.length.toLocaleString("de-DE")} Dateien`;

  if (!rows.length) {
    ui.downloads.innerHTML = '<div class="empty">Noch keine Downloads vorhanden.</div>';
    return;
  }

  const html = [
    "<table>",
    "<thead><tr><th>Datei</th><th>Groesse</th><th>Geaendert</th></tr></thead>",
    "<tbody>",
    ...rows.map((item) => {
      const href = `/downloads/${encodeURIComponent(item.name)}`;
      return `<tr><td><a href="${href}">${escapeHtml(item.name)}</a></td><td>${formatBytes(item.size)}</td><td>${formatDate(item.modified)}</td></tr>`;
    }),
    "</tbody></table>",
  ].join("");
  ui.downloads.innerHTML = html;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function loadDownloads() {
  try {
    const data = await apiGet("/api/downloads");
    renderDownloads(data.items || []);
  } catch (err) {
    ui.downloads.innerHTML = `<div class="empty">${escapeHtml(err.message)}</div>`;
  }
}

async function startDownload() {
  setMessage("");
  const url = ui.url.value.trim();
  if (!url) {
    setMessage("Bitte eine URL eingeben.", "error");
    ui.url.focus();
    return;
  }

  startRequestRunning = true;
  ui.startBtn.disabled = true;
  try {
    const data = await apiPost("/api/download", { url, mode: selectedMode() });
    setMessage(`Job in Queue: ${data.job_id}`, "ok");
    ui.url.value = "";
  } catch (err) {
    setMessage(err.message, "error");
  } finally {
    startRequestRunning = false;
    ui.startBtn.disabled = false;
  }
}

ui.startBtn.addEventListener("click", startDownload);
ui.refreshBtn.addEventListener("click", loadDownloads);

pollStatus();
loadDownloads();
window.setInterval(loadDownloads, 5000);
