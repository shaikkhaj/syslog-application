import { useCallback, useEffect, useRef, useState } from 'react';
import {
  fetchAlerts,
  fetchEvents,
  fetchHealth,
  fetchIncidents,
} from '../api/client.js';
import AlertsPanel from '../components/AlertsPanel.jsx';
import EventsTable from '../components/EventsTable.jsx';
import FilterBar from '../components/FilterBar.jsx';
import HealthCard from '../components/HealthCard.jsx';
import IncidentsPanel from '../components/IncidentsPanel.jsx';

const REFRESH_INTERVAL_MS = 5000;

function alertsWsUrl() {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${scheme}://${window.location.host}/api/v1/ws/alerts`;
}

export default function Dashboard() {
  const [health, setHealth] = useState(null);
  const [events, setEvents] = useState([]);
  const [total, setTotal] = useState(0);
  const [alerts, setAlerts] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [wsLive, setWsLive] = useState(false);
  const [filters, setFilters] = useState({
    q: '',
    severity: '',
    device_ip: '',
    event_type: '',
  });
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const reconnectTimer = useRef(null);

  const loadAlerts = useCallback(async () => {
    try {
      const data = await fetchAlerts({ limit: 30 });
      setAlerts(data.items);
    } catch (err) {
      setError(err.message);
    }
  }, []);

  const loadIncidents = useCallback(async () => {
    try {
      const data = await fetchIncidents({ limit: 30 });
      setIncidents(data.items);
    } catch (err) {
      setError(err.message);
    }
  }, []);

  const load = useCallback(async () => {
    try {
      const [healthData, eventData] = await Promise.all([
        fetchHealth(),
        fetchEvents(filters),
      ]);
      setHealth(healthData);
      setEvents(eventData.items);
      setTotal(eventData.total);
      setLastUpdated(new Date());
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }, [filters]);

  useEffect(() => {
    load();
    loadAlerts();
    loadIncidents();
    const timer = setInterval(() => {
      load();
      loadAlerts();
      loadIncidents();
    }, REFRESH_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [load, loadAlerts, loadIncidents]);

  // Real-time alert stream (falls back to the polling above when offline).
  useEffect(() => {
    let socket;
    let closed = false;

    const connect = () => {
      try {
        socket = new WebSocket(alertsWsUrl());
      } catch (err) {
        return;
      }
      socket.onopen = () => setWsLive(true);
      socket.onmessage = (message) => {
        try {
          const payload = JSON.parse(message.data);
          if (payload.type === 'alert') {
            loadAlerts();
          } else if (payload.type === 'incident') {
            loadIncidents();
          }
        } catch (err) {
          /* ignore malformed frames */
        }
      };
      socket.onclose = () => {
        setWsLive(false);
        if (!closed) {
          reconnectTimer.current = setTimeout(connect, 5000);
        }
      };
      socket.onerror = () => socket.close();
    };

    connect();
    return () => {
      closed = true;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (socket) socket.close();
    };
  }, [loadAlerts, loadIncidents]);

  const applyFilters = (nextFilters) => setFilters(nextFilters);

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-800">
            Network Syslog Monitoring
          </h1>
          <p className="text-sm text-slate-500">
            Phase 2 — ingestion, detection engine &amp; real-time alerts
          </p>
        </div>
        <div className="text-right text-xs text-slate-500">
          <span className="mr-2 inline-block h-2 w-2 animate-pulse rounded-full bg-emerald-500 align-middle" />
          auto-refresh {REFRESH_INTERVAL_MS / 1000}s
          {lastUpdated && (
            <div>updated {lastUpdated.toLocaleTimeString()}</div>
          )}
        </div>
      </header>

      {error && (
        <div className="mb-4 rounded border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error} — is the backend running?
        </div>
      )}

      <div className="mb-6">
        <HealthCard health={health} />
      </div>

      <div className="mb-4">
        <IncidentsPanel
          incidents={incidents}
          live={wsLive}
          onChanged={loadIncidents}
          onError={setError}
        />
      </div>

      <div className="mb-4">
        <AlertsPanel
          alerts={alerts}
          live={wsLive}
          onChanged={loadAlerts}
          onError={setError}
        />
      </div>

      <div className="mb-4">
        <FilterBar filters={filters} onApply={applyFilters} />
      </div>

      <EventsTable events={events} total={total} />
    </div>
  );
}
