const detailRoot = document.querySelector("[data-service-detail]");
const serviceId = detailRoot?.dataset.serviceId;
const historyState = document.querySelector("[data-history-state]");
const incidentState = document.querySelector("[data-incident-state]");
let responseChart;

function formatTimestamp(value) {
  return value ? new Date(value).toLocaleString() : "—";
}

function formatDuration(totalSeconds) {
  const seconds = Math.max(0, Number(totalSeconds) || 0);
  const days = Math.floor(seconds / 86_400);
  const hours = Math.floor((seconds % 86_400) / 3_600);
  const minutes = Math.floor((seconds % 3_600) / 60);
  if (days) return `${days}d ${hours}h`;
  if (hours) return `${hours}h ${minutes}m`;
  if (minutes) return `${minutes}m ${Math.floor(seconds % 60)}s`;
  return `${Math.floor(seconds)}s`;
}

function renderChart(points, range) {
  const context = document.querySelector("#response-time-chart");
  responseChart?.destroy();
  responseChart = new Chart(context, {
    type: "line",
    data: {
      labels: points.map((point) => formatTimestamp(point.timestamp)),
      datasets: [
        {
          label: "Response time (ms)",
          data: points.map((point) => point.response_time_ms),
          borderColor: "#4f7cff",
          backgroundColor: "rgba(79, 124, 255, 0.12)",
          pointBackgroundColor: points.map((point) =>
            point.is_up ? "#36a852" : "#d43c4d",
          ),
          pointRadius: points.length > 200 ? 0 : 3,
          tension: 0.15,
          spanGaps: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { intersect: false, mode: "index" },
      scales: {
        y: { beginAtZero: true, title: { display: true, text: "Milliseconds" } },
        x: { ticks: { maxTicksLimit: 8, maxRotation: 0 } },
      },
      plugins: { title: { display: true, text: `${range} history` } },
    },
  });
}

async function loadHistory(range) {
  historyState.textContent = "Loading history…";
  try {
    const response = await fetch(`/api/services/${serviceId}/history?range=${range}`);
    if (!response.ok) throw new Error(`History request failed (${response.status})`);
    const payload = await response.json();
    renderChart(payload.data.points, range);
    historyState.textContent = payload.data.points.length
      ? `${payload.data.points.length} samples shown.`
      : "No samples in this range yet.";
  } catch (error) {
    historyState.textContent = "History could not be loaded.";
  }
}

function renderIncidents(incidents) {
  const rows = document.querySelector("[data-incident-rows]");
  rows.replaceChildren();
  if (!incidents.length) {
    const row = rows.insertRow();
    const cell = row.insertCell();
    cell.colSpan = 4;
    cell.textContent = "No incidents recorded.";
    return;
  }
  for (const incident of incidents) {
    const row = rows.insertRow();
    row.insertCell().textContent = formatTimestamp(incident.started_at);
    row.insertCell().textContent = formatTimestamp(incident.resolved_at);
    row.insertCell().textContent = formatDuration(incident.display_duration_seconds);
    row.insertCell().textContent = incident.resolved ? "Resolved" : "Ongoing";
  }
}

async function loadIncidents() {
  try {
    const response = await fetch(`/api/services/${serviceId}/incidents`);
    if (!response.ok) throw new Error(`Incident request failed (${response.status})`);
    const payload = await response.json();
    renderIncidents(payload.data);
    incidentState.textContent = "";
  } catch (error) {
    incidentState.textContent = "Incident history could not be refreshed.";
  }
}

for (const button of document.querySelectorAll("[data-history-range]")) {
  button.addEventListener("click", () => {
    document.querySelectorAll("[data-history-range]").forEach((item) => {
      const active = item === button;
      item.classList.toggle("active", active);
      item.setAttribute("aria-pressed", String(active));
    });
    loadHistory(button.dataset.historyRange);
  });
}

if (serviceId) {
  loadHistory("24h");
  loadIncidents();
}
