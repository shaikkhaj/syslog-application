import { useCallback, useEffect, useRef, useState } from 'react';
import {
  fetchAlerts,
  fetchDevices,
  fetchEvents,
  fetchHealth,
  fetchIncidents,
  fetchNetworkHealth,
} from '../api/client.js';
import AlertsPanel from '../components/AlertsPanel.jsx';
import ChartsPanel from '../components/ChartsPanel.jsx';
import DashboardToolbar from '../components/DashboardToolbar.jsx';
import EventsTable from '../components/EventsTable.jsx';
import FilterBar from '../components/FilterBar.jsx';
import HealthCard from '../components/HealthCard.jsx';
import IncidentsPanel from '../components/IncidentsPanel.jsx';
import NetworkHealthPanel from '../components/NetworkHealthPanel.jsx';

const REFRESH_INTERVAL_MS = 5000;
const TREND_EVENT_LIMIT = 500; // /events max page size — bucketing cap
const TREND_BUCKETS = 12;

const RANGE_MINUTES = { '15m': 15, '1h': 60, '6h': 360, '24h': 1440, '7d': 10080, all: null };
const RANGE_LABELS = {
  '15m': 'last 15 min',
  '1h': 'last hour',
  '6h': 'last 6 h',
  '24h': 'last 24 h',
  '7d': 'last 7 days',
  all: 'all time',
};

const ALERT_SEVERITIES = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];
const INCIDENT_STATUSES = ['OPEN', 'INVESTIGATING', 'ACKNOWLEDGED', 'RESOLVED', 'CLOSED'];
// Incidents use LOW..CRITICAL only — INFO would fail the API pattern (422).
const INCIDENT_SEVERITIES = new Set(['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']);

const SECTION_LINKS = [
  ['charts', 'Analytics'],
  ['network-health', 'Health'],
  ['incidents', 'Incidents'],
  ['alerts', 'Alerts'],
  ['events', 'Events'],
];

function alertsWsUrl() {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${scheme}://${window.location.host}/api/v1/ws/alerts`;
}

/** ISO `since` for the selected range (undefined = all time). */
function rangeSince(timeRange) {
  const minutes = RANGE_MINUTES[timeRange];
  if (!minutes) return undefined;
  return new Date(Date.now() - minutes * 60_000).toISOString();
}

function bucketLabel(timestampMs, timeRange) {
  const date = new Date(timestampMs);
  if (timeRange === '7d' || timeRange === 'all') {
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  }
  return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

/**
 * Bucket fetched events into evenly spaced trend points (client-side,
 * so no new backend endpoint is needed). items are already filtered
 * with the same criteria as the events table.
 */
function buildTrend(items, timeRange) {
  if (!items.length) return [];
  const now = Date.now();
  const minutes = RANGE_MINUTES[timeRange];
  const startMs = minutes
    ? now - minutes * 60_000
    : Math.min(...items.map((item) => Date.parse(item.received_at)));
  const span = Math.max(now - startMs, 60_000);
  const bucketMs = span / TREND_BUCKETS;
  const counts = new Array(TREND_BUCKETS).fill(0);

  items.forEach((item) => {
    const receivedMs = Date.parse(item.received_at);
    const index = Math.min(
      TREND_BUCKETS - 1,
      Math.max(0, Math.floor((receivedMs - startMs) / bucketMs))
    );
    counts[index] += 1;
  });

  return counts.map((count, index) => {
    const bucketStart = startMs + index * bucketMs;
    return {
      count,
      label: bucketLabel(bucketStart, timeRange),
      fullLabel: `${bucketLabel(bucketStart, timeRange)} – ${bucketLabel(
        bucketStart + bucketMs,
        timeRange
      )}`,
    };
  });
}

export default function Dashboard() {
  const [health, setHealth] = useState(null);
  const [events, setEvents] = useState([]);
  const [total, setTotal] = useState(0);
  const [alerts, setAlerts] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [networkHealth, setNetworkHealth] = useState(null);
  const [devices, setDevices] = useState([]);
  const [wsLive, setWsLive] = useState(false);
  const [filters, setFilters] = useState({
    q: '',
    severity: '',
    event_type: '',
  });
  const [timeRange, setTimeRange] = useState('1h');
  const [deviceId, setDeviceId] = useState('');
  const [alertSeverity, setAlertSeverity] = useState('');
  const [incidentStatus, setIncidentStatus] = useState('');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [error, setError] = useState(null); // action/mutation errors (banner)
  const [sectionErrors, setSectionErrors] = useState({}); // per-section fetch errors
  const [loaded, setLoaded] = useState({}); // first successful fetch per section
  const [chartsData, setChartsData] = useState({
    trend: [],
    trendNote: '',
    alertSeverity: [],
    incidentStatus: [],
  });
  const [lastUpdated, setLastUpdated] = useState(null);
  const reconnectTimer = useRef(null);
  const autoRefreshRef = useRef(true);

  const selectedDevice = devices.find((device) => String(device.id) === deviceId);
  const deviceIdNum = deviceId ? Number(deviceId) : undefined;
  const deviceIp = selectedDevice ? selectedDevice.ip_address : '';
  const incidentSev =
    alertSeverity && INCIDENT_SEVERITIES.has(alertSeverity) ? alertSeverity : undefined;

  /** Run a fetch, tracking per-section error + loaded state. Returns data or null. */
  const run = useCallback(async (key, fn) => {
    try {
      const result = await fn();
      setSectionErrors((previous) => {
        if (!previous[key]) return previous;
        const next = { ...previous };
        delete next[key];
        return next;
      });
      setLoaded((previous) => (previous[key] ? previous : { ...previous, [key]: true }));
      return result;
    } catch (err) {
      setSectionErrors((previous) => ({ ...previous, [key]: err.message }));
      return null;
    }
  }, []);

  const eventQuery = useCallback(() => {
    const query = { ...filters, since: rangeSince(timeRange) };
    if (deviceIp) query.device_ip = deviceIp;
    return query;
  }, [filters, timeRange, deviceIp]);

  const loadAlerts = useCallback(async () => {
    const data = await run('alerts', () =>
      fetchAlerts({
        limit: 30,
        since: rangeSince(timeRange),
        device_id: deviceIdNum,
        severity: alertSeverity || undefined,
      })
    );
    if (data) setAlerts(data.items);
  }, [run, timeRange, deviceIdNum, alertSeverity]);

  const loadIncidents = useCallback(async () => {
    const data = await run('incidents', () =>
      fetchIncidents({
        limit: 30,
        since: rangeSince(timeRange),
        device_id: deviceIdNum,
        severity: incidentSev,
        status: incidentStatus || undefined,
      })
    );
    if (data) setIncidents(data.items);
  }, [run, timeRange, deviceIdNum, incidentSev, incidentStatus]);

  const load = useCallback(async () => {
    const [healthData, eventData, networkHealthData, devicesData] = await Promise.all([
      run('health', () => fetchHealth()),
      run('events', () => fetchEvents(eventQuery())),
      run('networkHealth', () => fetchNetworkHealth({ limit: 50 })),
      run('devices', () => fetchDevices()),
    ]);
    if (healthData) setHealth(healthData);
    if (eventData) {
      setEvents(eventData.items);
      setTotal(eventData.total);
    }
    if (networkHealthData) setNetworkHealth(networkHealthData);
    if (devicesData) setDevices(devicesData.items || []);
    setLastUpdated(new Date());
  }, [run, eventQuery]);

  const loadCharts = useCallback(async () => {
    const since = rangeSince(timeRange);
    const query = eventQuery();
    query.limit = TREND_EVENT_LIMIT;
    const result = await run('charts', async () => {
      const [eventData, ...totals] = await Promise.all([
        fetchEvents(query),
        ...ALERT_SEVERITIES.map((severity) =>
          fetchAlerts({ severity, since, device_id: deviceIdNum, limit: 1 })
        ),
        ...INCIDENT_STATUSES.map((status) =>
          fetchIncidents({ status, since, device_id: deviceIdNum, severity: incidentSev, limit: 1 })
        ),
      ]);
      return {
        trend: buildTrend(eventData.items, timeRange),
        trendNote:
          eventData.items.length >= TREND_EVENT_LIMIT
            ? 'bucketed from the latest 500 matching events'
            : '',
        alertSeverity: ALERT_SEVERITIES.map((severity, index) => ({
          key: severity,
          value: totals[index].total,
        })),
        incidentStatus: INCIDENT_STATUSES.map((status, index) => ({
          key: status,
          value: totals[ALERT_SEVERITIES.length + index].total,
        })),
      };
    });
    if (result) setChartsData(result);
  }, [run, eventQuery, timeRange, deviceIdNum, incidentSev]);

  const refreshAll = useCallback(() => {
    load();
    loadAlerts();
    loadIncidents();
    loadCharts();
  }, [load, loadAlerts, loadIncidents, loadCharts]);

  useEffect(() => {
    refreshAll();
    if (!autoRefresh) return undefined;
    const timer = setInterval(refreshAll, REFRESH_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [refreshAll, autoRefresh]);

  useEffect(() => {
    autoRefreshRef.current = autoRefresh;
  }, [autoRefresh]);

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
          if (!autoRefreshRef.current) return; // paused — keep the view frozen
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

  /** Deep link: open the topology page with a device preselected (Phase 6). */
  const openInTopology = (deviceIdToOpen) => {
    window.location.hash = `#/topology?device=${deviceIdToOpen}`;
  };

  const scrollToSection = (id) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const eventsFiltered = Boolean(
    filters.q || filters.severity || filters.event_type || deviceIp || timeRange !== 'all'
  );

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <header className="mb-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold text-slate-800">
              Network Syslog Monitoring
            </h1>
            <p className="text-sm text-slate-500">
              Phases 1–6 — ingestion, detection, correlation, RCA, network
              health &amp; live analytics
            </p>
          </div>
        </div>
        <nav className="mt-3 flex flex-wrap gap-2" aria-label="Dashboard sections">
          {SECTION_LINKS.map(([id, label]) => (
            <button
              key={id}
              onClick={() => scrollToSection(id)}
              className="rounded-full border border-slate-300 bg-white px-3 py-1 text-xs font-medium text-slate-600 hover:border-blue-400 hover:text-blue-600"
            >
              {label}
            </button>
          ))}
        </nav>
      </header>

      {error && (
        <div className="mb-4 flex items-center justify-between rounded border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700">
          <span>{error}</span>
          <button
            onClick={() => setError(null)}
            className="ml-3 font-bold"
            aria-label="Dismiss error"
          >
            ✕
          </button>
        </div>
      )}

      <div className="mb-4">
        <DashboardToolbar
          timeRange={timeRange}
          onTimeRange={setTimeRange}
          devices={devices}
          deviceId={deviceId}
          onDeviceId={setDeviceId}
          severity={alertSeverity}
          onSeverity={setAlertSeverity}
          incidentStatus={incidentStatus}
          onClearIncidentStatus={() => setIncidentStatus('')}
          autoRefresh={autoRefresh}
          onToggleAutoRefresh={() => setAutoRefresh((value) => !value)}
          onRefreshNow={refreshAll}
          lastUpdated={lastUpdated}
        />
      </div>

      <div className="mb-4">
        <HealthCard health={health} error={sectionErrors.health} />
      </div>

      <ChartsPanel
        loading={!loaded.charts && !sectionErrors.charts}
        error={sectionErrors.charts}
        onRetry={loadCharts}
        trend={chartsData.trend}
        trendNote={chartsData.trendNote}
        alertSeverity={chartsData.alertSeverity}
        incidentStatus={chartsData.incidentStatus}
        health={networkHealth}
        selectedSeverity={alertSeverity}
        onSelectSeverity={(key) =>
          setAlertSeverity((current) => (current === key ? '' : key))
        }
        selectedStatus={incidentStatus}
        onSelectStatus={(key) =>
          setIncidentStatus((current) => (current === key ? '' : key))
        }
        onSelectDevice={openInTopology}
        rangeLabel={RANGE_LABELS[timeRange]}
      />

      <div id="network-health" className="mb-4 scroll-mt-4">
        <NetworkHealthPanel
          health={networkHealth}
          error={sectionErrors.networkHealth}
          onRetry={refreshAll}
          onSelectDevice={openInTopology}
        />
      </div>

      <div id="incidents" className="mb-4 scroll-mt-4">
        <IncidentsPanel
          incidents={incidents}
          loading={!loaded.incidents}
          error={sectionErrors.incidents}
          onRetry={refreshAll}
          live={wsLive}
          onChanged={loadIncidents}
          onError={setError}
        />
      </div>

      <div id="alerts" className="mb-4 scroll-mt-4">
        <AlertsPanel
          alerts={alerts}
          loading={!loaded.alerts}
          error={sectionErrors.alerts}
          onRetry={refreshAll}
          live={wsLive}
          onChanged={loadAlerts}
          onError={setError}
        />
      </div>

      <div className="mb-4">
        <FilterBar filters={filters} onApply={applyFilters} />
      </div>

      <div id="events" className="scroll-mt-4">
        <EventsTable
          events={events}
          total={total}
          loading={!loaded.events}
          error={sectionErrors.events}
          onRetry={refreshAll}
          filtered={eventsFiltered}
        />
      </div>
    </div>
  );
}
