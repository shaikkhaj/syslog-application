const API_BASE = import.meta.env.VITE_API_BASE || '/api';

async function request(path) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    throw new Error(`API request ${path} failed with status ${response.status}`);
  }
  return response.json();
}

export function fetchHealth() {
  return request('/v1/health');
}

export function fetchEvents(params = {}) {
  const query = new URLSearchParams({ limit: '50' });
  Object.entries(params).forEach(([key, value]) => {
    if (value !== '' && value !== null && value !== undefined) {
      query.set(key, String(value));
    }
  });
  return request(`/v1/events?${query.toString()}`);
}

export function fetchDevices() {
  return request('/v1/devices');
}

// --- Alerts (Phase 2) -----------------------------------------------------

export function fetchAlerts(params = {}) {
  const query = new URLSearchParams({ limit: '50' });
  Object.entries(params).forEach(([key, value]) => {
    if (value !== '' && value !== null && value !== undefined) {
      query.set(key, String(value));
    }
  });
  return request(`/v1/alerts?${query.toString()}`);
}

export async function acknowledgeAlert(id, actor = 'dashboard-user') {
  const response = await fetch(`${API_BASE}/v1/alerts/${id}/acknowledge`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actor }),
  });
  if (!response.ok) {
    throw new Error(`Acknowledge failed with status ${response.status}`);
  }
  return response.json();
}

export async function resolveAlert(id, actor = 'dashboard-user') {
  const response = await fetch(`${API_BASE}/v1/alerts/${id}/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actor }),
  });
  if (!response.ok) {
    throw new Error(`Resolve failed with status ${response.status}`);
  }
  return response.json();
}

// --- Incidents (Phase 3) -------------------------------------------------

export function fetchIncidents(params = {}) {
  const query = new URLSearchParams({ limit: '30' });
  Object.entries(params).forEach(([key, value]) => {
    if (value !== '' && value !== null && value !== undefined) {
      query.set(key, String(value));
    }
  });
  return request(`/v1/incidents?${query.toString()}`);
}

export function fetchIncidentTimeline(id) {
  return request(`/v1/incidents/${id}/timeline`);
}

async function incidentAction(id, action, actor = 'dashboard-user') {
  const response = await fetch(`${API_BASE}/v1/incidents/${id}/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actor }),
  });
  if (!response.ok) {
    const detail = await response
      .json()
      .catch(() => ({ detail: `status ${response.status}` }));
    throw new Error(detail.detail || `Incident ${action} failed`);
  }
  return response.json();
}

export function acknowledgeIncident(id, actor) {
  return incidentAction(id, 'acknowledge', actor);
}

export function resolveIncident(id, actor) {
  return incidentAction(id, 'resolve', actor);
}

export function closeIncident(id, actor) {
  return incidentAction(id, 'close', actor);
}
