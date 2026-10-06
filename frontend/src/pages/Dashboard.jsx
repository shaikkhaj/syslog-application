import { useCallback, useEffect, useState } from 'react';
import { fetchEvents, fetchHealth } from '../api/client.js';
import EventsTable from '../components/EventsTable.jsx';
import FilterBar from '../components/FilterBar.jsx';
import HealthCard from '../components/HealthCard.jsx';

const REFRESH_INTERVAL_MS = 5000;

export default function Dashboard() {
  const [health, setHealth] = useState(null);
  const [events, setEvents] = useState([]);
  const [total, setTotal] = useState(0);
  const [filters, setFilters] = useState({
    q: '',
    severity: '',
    device_ip: '',
    event_type: '',
  });
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);

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
    const timer = setInterval(load, REFRESH_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [load]);

  const applyFilters = (nextFilters) => setFilters(nextFilters);

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-800">
            Network Syslog Monitoring
          </h1>
          <p className="text-sm text-slate-500">
            Phase 1 — ingestion &amp; normalized event dashboard
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
        <FilterBar filters={filters} onApply={applyFilters} />
      </div>

      <EventsTable events={events} total={total} />
    </div>
  );
}
