const TIME_RANGES = [
  { key: '15m', label: '15m' },
  { key: '1h', label: '1h' },
  { key: '6h', label: '6h' },
  { key: '24h', label: '24h' },
  { key: '7d', label: '7d' },
  { key: 'all', label: 'All' },
];

const SEVERITIES = ['', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];

const INPUT =
  'rounded border border-slate-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500';

/**
 * Global dashboard controls (Phase 6): time range, device and severity
 * filters plus auto-refresh controls. Presentational — state lives in the
 * Dashboard page.
 */
export default function DashboardToolbar({
  timeRange,
  onTimeRange,
  devices,
  deviceId,
  onDeviceId,
  severity,
  onSeverity,
  incidentStatus,
  onClearIncidentStatus,
  autoRefresh,
  onToggleAutoRefresh,
  onRefreshNow,
  lastUpdated,
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
      <div className="flex flex-wrap items-end gap-x-4 gap-y-3">
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-slate-500">Time range</span>
          <div className="inline-flex overflow-hidden rounded border border-slate-300">
            {TIME_RANGES.map((range) => (
              <button
                key={range.key}
                onClick={() => onTimeRange(range.key)}
                className={`px-2.5 py-1.5 text-xs font-semibold ${
                  timeRange === range.key
                    ? 'bg-blue-600 text-white'
                    : 'bg-white text-slate-600 hover:bg-slate-50'
                }`}
                aria-pressed={timeRange === range.key}
              >
                {range.label}
              </button>
            ))}
          </div>
        </div>

        <label className="flex flex-col gap-1 text-xs font-medium text-slate-500">
          Device
          <select
            value={deviceId}
            onChange={(event) => onDeviceId(event.target.value)}
            className={`${INPUT} w-44`}
          >
            <option value="">All devices</option>
            {devices.map((device) => (
              <option key={device.id} value={String(device.id)}>
                {device.hostname || device.ip_address}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-xs font-medium text-slate-500">
          Severity
          <select
            value={severity}
            onChange={(event) => onSeverity(event.target.value)}
            className={INPUT}
          >
            {SEVERITIES.map((value) => (
              <option key={value} value={value}>
                {value || 'All severities'}
              </option>
            ))}
          </select>
        </label>

        {incidentStatus && (
          <button
            onClick={onClearIncidentStatus}
            className="rounded-full border border-blue-300 bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700 hover:bg-blue-100"
            title="Clear incident status filter"
          >
            status: {incidentStatus} ✕
          </button>
        )}

        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={onToggleAutoRefresh}
            className={`flex items-center gap-1.5 rounded border px-3 py-1.5 text-xs font-semibold ${
              autoRefresh
                ? 'border-emerald-300 bg-emerald-50 text-emerald-700'
                : 'border-slate-300 bg-white text-slate-600 hover:bg-slate-50'
            }`}
            aria-pressed={autoRefresh}
          >
            <span
              className={`inline-block h-2 w-2 rounded-full ${
                autoRefresh ? 'animate-pulse bg-emerald-500' : 'bg-slate-400'
              }`}
            />
            {autoRefresh ? 'Auto-refresh on' : 'Auto-refresh paused'}
          </button>
          <button
            onClick={onRefreshNow}
            className="rounded border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
          >
            Refresh now
          </button>
          {lastUpdated && (
            <span className="hidden text-xs text-slate-400 sm:inline">
              {lastUpdated.toLocaleTimeString()}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
