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

// --- Topology (Phase 4) --------------------------------------------------

export function fetchTopology() {
  return request('/v1/topology');
}

async function deviceMutation(path, method, payload) {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const detail = await response
      .json()
      .catch(() => ({ detail: `status ${response.status}` }));
    throw new Error(detail.detail || `${method} failed`);
  }
  return response.status === 204 ? null : response.json();
}

export function createDevice(payload) {
  return deviceMutation('/v1/devices', 'POST', payload);
}

export function updateDevice(id, payload) {
  return deviceMutation(`/v1/devices/${id}`, 'PATCH', payload);
}

export function deleteDevice(id) {
  return deviceMutation(`/v1/devices/${id}`, 'DELETE', null);
}

export function createLink(payload) {
  return deviceMutation('/v1/links', 'POST', payload);
}

export function updateLink(id, payload) {
  return deviceMutation(`/v1/links/${id}`, 'PATCH', payload);
}

export function deleteLink(id) {
  return deviceMutation(`/v1/links/${id}`, 'DELETE', null);
}

// --- RCA & network health (Phase 5) ---------------------------------------

export function fetchIncidentRca(id) {
  return request(`/v1/incidents/${id}/rca`);
}
// --- Notifications (Phase 7) -----------------------------------------------

export function fetchNotifications(params = {}) {
  const query = new URLSearchParams({ limit: '50' });
  Object.entries(params).forEach(([key, value]) => {
    if (value !== '' && value !== null && value !== undefined) {
      query.set(key, String(value));
    }
  });
  return request(`/v1/notifications?${query.toString()}`);
}

export function fetchUnreadCount() {
  return request('/v1/notifications/unread-count');
}

export async function markNotificationRead(id, actor = 'dashboard-user') {
  const response = await fetch(`${API_BASE}/v1/notifications/${id}/read`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actor }),
  });
  if (!response.ok) {
    throw new Error(`Mark read failed with status ${response.status}`);
  }
  return response.json();
}

export async function markAllNotificationsRead(actor = 'dashboard-user') {
  const response = await fetch(`${API_BASE}/v1/notifications/read-all`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actor }),
  });
  if (!response.ok) {
    throw new Error(`Mark all read failed with status ${response.status}`);
  }
  return response.json();
}

export function fetchNotificationSettings() {
  return request('/v1/notifications/settings');
}

export async function updateNotificationSettings(payload) {
  const response = await fetch(`${API_BASE}/v1/notifications/settings`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`Update settings failed with status ${response.status}`);
  }
  return response.json();
}

export async function triggerEscalation() {
  const response = await fetch(`${API_BASE}/v1/notifications/escalate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!response.ok) {
    throw new Error(`Escalation failed with status ${response.status}`);
  }
  return response.json();
}


export function fetchNetworkHealth(params = {}) {
  const query = new URLSearchParams({ limit: '100' });
  Object.entries(params).forEach(([key, value]) => {
    if (value !== '' && value !== null && value !== undefined) {
      query.set(key, String(value));
    }
  });
  return request(`/v1/network-health?${query.toString()}`);
}
