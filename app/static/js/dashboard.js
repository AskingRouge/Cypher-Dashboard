const refreshState = document.querySelector("[data-refresh-state]");
let activeRequest;
let refreshTimer;

function formatUptime(value) {
  return value === null || value === undefined ? "N/A" : `${value.toFixed(2)}%`;
}

function formatTime(value) {
  return value ? new Date(value).toLocaleString() : "Never";
}

function updateCard(service) {
  const card = document.querySelector(`[data-service-id="${service.id}"]`);
  if (!card) return;

  const status = card.querySelector('[data-field="status"]');
  status.textContent = service.status[0].toUpperCase() + service.status.slice(1);
  status.className = `status status-${service.status}`;

  const response = card.querySelector('[data-field="response-time"]');
  response.textContent =
    service.response_time_ms === null
      ? "—"
      : `${service.response_time_ms.toFixed(1)} ms`;

  card.querySelector('[data-field="last-checked"]').textContent = formatTime(
    service.last_checked_at,
  );
  for (const range of ["24h", "7d", "30d"]) {
    card.querySelector(`[data-uptime-range="${range}"]`).textContent = formatUptime(
      service.uptime[range],
    );
  }
}

async function refreshServices() {
  activeRequest?.abort();
  activeRequest = new AbortController();
  try {
    const response = await fetch("/api/services", {
      headers: { Accept: "application/json" },
      signal: activeRequest.signal,
    });
    if (!response.ok) throw new Error(`Refresh failed (${response.status})`);
    const payload = await response.json();
    payload.data.forEach(updateCard);
    refreshState.textContent = `Updated ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    if (error.name !== "AbortError") {
      refreshState.textContent = "Live refresh failed; showing the last known status.";
    }
  }
}

function scheduleRefresh() {
  window.clearInterval(refreshTimer);
  if (!document.hidden) {
    refreshServices();
    refreshTimer = window.setInterval(refreshServices, 15_000);
  }
}

document.addEventListener("visibilitychange", scheduleRefresh);
scheduleRefresh();
