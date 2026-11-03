import { ErrorBlock } from './States.jsx';

const BAND_STYLES = {
  healthy: 'bg-emerald-100 text-emerald-700',
  degraded: 'bg-amber-100 text-amber-700',
  critical: 'bg-red-100 text-red-700',
};

const BAND_DOT = {
  healthy: 'bg-emerald-500',
  degraded: 'bg-amber-500',
  critical: 'bg-red-500',
};

function scoreColor(band) {
  if (band === 'critical') return 'text-red-600';
  if (band === 'degraded') return 'text-amber-600';
  return 'text-emerald-600';
}

/**
 * Network health (Phase 5): overall score + worst-first device table.
 * Data comes from GET /api/v1/network-health (alerts, incidents, event
 * frequency and device status — nothing stored).
 */
export default function NetworkHealthPanel({ health, error, onRetry }) {
  if (error) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <ErrorBlock message={error} onRetry={onRetry} />
      </div>
    );
  }

  if (!health) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-400 shadow-sm">
        Loading network health…
      </div>
    );
  }

  const counts = health.counts || { healthy: 0, degraded: 0, critical: 0 };

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Network Health
        </h2>
        <div className="flex items-center gap-3 text-xs text-slate-500">
          <span>{health.device_count} devices</span>
          <span>
            last {health.window_minutes} min
          </span>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-6 border-b border-slate-100 px-4 py-3">
        <div className="flex items-baseline gap-2">
          <span className={`text-3xl font-bold ${scoreColor(health.band)}`}>
            {Math.round(health.overall_score)}
          </span>
          <span className="text-sm text-slate-400">/ 100</span>
          <span
            className={`ml-1 rounded px-2 py-0.5 text-xs font-bold uppercase ${
              BAND_STYLES[health.band] || 'bg-slate-100 text-slate-600'
            }`}
          >
            {health.band}
          </span>
        </div>
        <div className="flex gap-4 text-xs text-slate-600">
          {['healthy', 'degraded', 'critical'].map((band) => (
            <span key={band} className="flex items-center gap-1.5">
              <span
                className={`inline-block h-2 w-2 rounded-full ${BAND_DOT[band]}`}
              />
              {counts[band]} {band}
            </span>
          ))}
        </div>
      </div>

      {health.items.length === 0 ? (
        <p className="p-6 text-center text-sm text-slate-500">
          No devices registered yet — send syslog traffic or add devices in
          the topology view.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-2">Device</th>
                <th className="px-4 py-2">Band</th>
                <th className="px-4 py-2">Score</th>
                <th className="px-4 py-2">Open alerts</th>
                <th className="px-4 py-2">Incidents</th>
                <th className="px-4 py-2">Recent events</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {health.items.map((device) => (
                <tr key={device.device_id} className="hover:bg-slate-50">
                  <td className="px-4 py-2">
                    <span className="font-medium text-slate-700">
                      {device.hostname || device.ip_address}
                    </span>
                    <span className="ml-2 text-xs text-slate-400">
                      {device.ip_address} · {device.device_type}
                    </span>
                  </td>
                  <td className="px-4 py-2">
                    <span
                      className={`rounded px-2 py-0.5 text-xs font-bold uppercase ${
                        BAND_STYLES[device.band] || 'bg-slate-100'
                      }`}
                    >
                      {device.band}
                    </span>
                  </td>
                  <td
                    className={`px-4 py-2 font-mono font-semibold ${scoreColor(
                      device.band
                    )}`}
                  >
                    {Math.round(device.score)}
                  </td>
                  <td className="px-4 py-2">
                    {device.open_alerts || 0}
                    {device.max_alert_severity && (
                      <span className="ml-1 text-xs text-slate-400">
                        ({device.max_alert_severity})
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2">{device.active_incidents || 0}</td>
                  <td className="px-4 py-2">{device.recent_events || 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
