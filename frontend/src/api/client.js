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
