import { useState } from 'react';
import { EmptyBlock, ErrorBlock, LoadingBlock } from './States.jsx';

const SEVERITY_COLORS = {
  CRITICAL: '#dc2626',
  HIGH: '#ea580c',
  MEDIUM: '#f59e0b',
  LOW: '#eab308',
  INFO: '#38bdf8',
};

const STATUS_COLORS = {
  OPEN: '#dc2626',
  INVESTIGATING: '#f59e0b',
  ACKNOWLEDGED: '#2563eb',
  RESOLVED: '#059669',
  CLOSED: '#64748b',
};

const BAND_COLORS = {
  critical: '#dc2626',
  degraded: '#d97706',
  healthy: '#059669',
};

function ChartCard({ title, subtitle, description, children, className = '' }) {
  return (
    <div
      className={`flex flex-col rounded-xl border border-slate-700/80 bg-[#142136] shadow-lg shadow-black/10 ${className}`}
    >
      <div className="border-b border-slate-700/80 px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-bold uppercase tracking-wider text-slate-200">
            {title}
          </h2>
          {subtitle && (
            <span className="rounded-full border border-slate-600 bg-slate-800/70 px-2.5 py-1 text-xs font-semibold text-blue-300">
              {subtitle}
            </span>
          )}
        </div>

        {description && (
          <p className="mt-1.5 text-xs leading-5 text-slate-400">
            {description}
          </p>
        )}
      </div>

      <div className="flex-1 p-4">{children}</div>
    </div>
  );
}

/**
 * Event-trend line/area chart with hover tooltips.
 * points: [{ label, fullLabel, count }] — bucketed by the parent (Phase 6).
 */
function TrendChart({ points }) {
  const [hover, setHover] = useState(null);
  const width = 720;
  const height = 210;
  const pad = { l: 40, r: 10, t: 12, b: 26 };
  const max = Math.max(1, ...points.map((point) => point.count));
  const innerW = width - pad.l - pad.r;
  const innerH = height - pad.t - pad.b;
  const xAt = (index) =>
    pad.l + (index * innerW) / Math.max(points.length - 1, 1);
  const yAt = (value) => pad.t + innerH - (value / max) * innerH;
  const baseline = pad.t + innerH;

  const linePath = points
    .map(
      (point, index) =>
        `${index === 0 ? 'M' : 'L'} ${xAt(index).toFixed(1)} ${yAt(point.count).toFixed(1)}`
    )
    .join(' ');
  const areaPath = points.length
    ? `${linePath} L ${xAt(points.length - 1).toFixed(1)} ${baseline} L ${xAt(0).toFixed(1)} ${baseline} Z`
    : '';

  const hoverPoint = hover !== null ? points[hover] : null;
  const labelIndexes = points.length
    ? [...new Set([0, Math.floor((points.length - 1) / 2), points.length - 1])]
    : [];

  return (
    <div className="relative">
      <svg
  viewBox={`0 0 ${width} ${height}`}
  className="h-auto w-full"
  onMouseLeave={() => setHover(null)}
  role="img"
  aria-label="Event trend chart"
>
  <defs>
    <linearGradient
      id="event-area-gradient"
      x1="0"
      y1="0"
      x2="0"
      y2="1"
    >
      <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.35" />
      <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.01" />
    </linearGradient>

    <linearGradient
      id="event-line-gradient"
      x1="0"
      y1="0"
      x2="1"
      y2="0"
    >
      <stop offset="0%" stopColor="#38bdf8" />
      <stop offset="100%" stopColor="#6366f1" />
    </linearGradient>

    <filter
      id="event-line-glow"
      x="-20%"
      y="-50%"
      width="140%"
      height="200%"
    >
      <feGaussianBlur stdDeviation="3" result="blur" />
      <feMerge>
        <feMergeNode in="blur" />
        <feMergeNode in="SourceGraphic" />
      </feMerge>
    </filter>
  </defs>

  {/* Keep your existing grid lines, paths, hover points and labels here */}
        viewBox={`0 0 ${width} ${height}`}
        className="h-auto w-full"
        onMouseLeave={() => setHover(null)}
        role="img"
        aria-label="Event trend chart"
      
        {[0, 0.5, 1].map((fraction) => (
          <g key={fraction}>
            <line
              x1={pad.l}
              x2={width - pad.r}
              y1={pad.t + fraction * innerH}
              y2={pad.t + fraction * innerH}
              stroke="#293b53"
              strokeWidth="1"
            />
            <text
              x={pad.l - 6}
              y={pad.t + fraction * innerH + 4}
              textAnchor="end"
              fontSize="10"
              fill="#94a3b8"
            >
              {Math.round(max * (1 - fraction))}
            </text>
          </g>
        ))}

        <path d={areaPath} fill="url(#event-area-gradient)" />
        <path
  d={linePath}
  fill="none"
  stroke="url(#event-line-gradient)"
  strokeWidth="3"
  strokeLinecap="round"
  strokeLinejoin="round"
  filter="url(#event-line-glow)"
/>

        {points.map((point, index) => (
          <g key={index}>
            <rect
              x={xAt(index) - innerW / Math.max(points.length, 1) / 2}
              y={pad.t}
              width={innerW / Math.max(points.length, 1)}
              height={innerH}
              fill="transparent"
              onMouseEnter={() => setHover(index)}
            />
            {hover === index && (
              <circle cx={xAt(index)} cy={yAt(point.count)} r="4" fill="#2563eb" />
            )}
          </g>
        ))}

        {labelIndexes.map((index) => (
          <text
            key={index}
            x={xAt(index)}
            y={height - 8}
            textAnchor={index === 0 ? 'start' : index === points.length - 1 ? 'end' : 'middle'}
            fontSize="10"
            fill="#94a3b8"
          >
            {points[index]?.label}
          </text>
        ))}
      </svg>

      {hoverPoint && (
        <div
          className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded bg-slate-900 px-2 py-1 text-xs font-medium text-white shadow"
          style={{
            left: `${(xAt(hover) / width) * 100}%`,
            top: `${(yAt(hoverPoint.count) / height) * 100}%`,
          }}
        >
          {hoverPoint.fullLabel} · {hoverPoint.count} event
          {hoverPoint.count === 1 ? '' : 's'}
        </div>
      )}
    </div>
  );
}

/**
 * Horizontal bar list used for alert severity, incident status and
 * device health charts. Rows are buttons so bars can act as filters.
 * items: [{ key, label, value }]
 */
function BarList({
  items,
  colorOf,
  selected,
  onSelect,
  emptyTitle,
  emptyHint,
}) {
  const total = items.reduce((sum, item) => sum + item.value, 0);

  if (total === 0) {
    return <EmptyBlock title={emptyTitle} hint={emptyHint} />;
  }

  const max = Math.max(1, ...items.map((item) => item.value));

  const descriptions = {
    CRITICAL: 'Immediate action required',
    HIGH: 'Urgent investigation',
    MEDIUM: 'Needs attention',
    LOW: 'Minor issue',
    INFO: 'Informational event',
    OPEN: 'Awaiting investigation',
    INVESTIGATING: 'Currently being investigated',
    ACKNOWLEDGED: 'Accepted by an operator',
    RESOLVED: 'Problem has been fixed',
    CLOSED: 'Formally closed',
  };

  return (
    <div className="space-y-2">
      {items.map((item) => {
        const isSelected = selected === item.key;
        const dimmed = selected && !isSelected;
        const color = colorOf(item.key);
        const description =
          descriptions[item.key] ||
          (onSelect ? 'Click to view matching records' : 'Current device health score');

        return (
          <button
            key={item.key}
            onClick={() => onSelect && onSelect(item.key)}
            className={`group w-full rounded-lg border px-3 py-2.5 text-left transition-all duration-200 ${
              isSelected
                ? 'border-blue-500 bg-blue-500/10 ring-1 ring-blue-500/40'
                : 'border-transparent bg-slate-800/40 hover:border-slate-600 hover:bg-slate-800/80'
            } ${dimmed ? 'opacity-40' : ''} ${
              onSelect ? 'cursor-pointer' : 'cursor-default'
            }`}
            title={onSelect ? `Filter by ${item.label}` : item.label}
            aria-pressed={onSelect ? isSelected : undefined}
          >
            <div className="flex items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-2.5">
                <span
                  className="h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{
                    backgroundColor: color,
                    boxShadow: `0 0 9px ${color}70`,
                  }}
                />

                <div className="min-w-0">
                  <p className="truncate text-xs font-bold tracking-wide text-slate-200">
                    {item.label}
                  </p>
                  <p className="mt-0.5 text-[11px] text-slate-400">
                    {description}
                  </p>
                </div>
              </div>

              <span className="shrink-0 rounded-md bg-slate-900/80 px-2.5 py-1 font-mono text-sm font-bold text-white">
                {item.value}
              </span>
            </div>

            <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-slate-700/80">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${Math.max(
                    (item.value / max) * 100,
                    item.value > 0 ? 3 : 0
                  )}%`,
                  backgroundColor: color,
                  boxShadow: `0 0 8px ${color}55`,
                }}
              />
            </div>
          </button>
        );
      })}
    </div>
  );
}

/**
 * Dashboard analytics (Phase 6): event trend, alert severity,
 * incident status and device health charts. Data is fetched by the
 * parent from existing APIs — this component only renders it.
 */
export default function ChartsPanel({
  loading,
  error,
  onRetry,
  trend,
  trendNote,
  alertSeverity,
  incidentStatus,
  health,
  selectedSeverity,
  onSelectSeverity,
  selectedStatus,
  onSelectStatus,
  onSelectDevice,
  rangeLabel,
}) {
  if (loading) {
    return (
      <section id="charts" className="mb-6">
        <ChartCard title="Analytics" subtitle={rangeLabel}>
          <LoadingBlock label="Loading charts…" rows={4} />
        </ChartCard>
      </section>
    );
  }

  const severityItems = alertSeverity || [];
const statusItems = incidentStatus || [];
const worstDevices = (health?.items || []).slice(0, 10);

const totalAlerts = severityItems.reduce(
  (sum, item) => sum + item.value,
  0
);

const totalIncidents = statusItems.reduce(
  (sum, item) => sum + item.value,
  0
);

  return (
    <section id="charts" className="mb-6">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartCard
  title="Event Trend"
  subtitle={rangeLabel}
  description="Number of syslog events received over time. Spikes can indicate increased network activity or potential issues."
  className="lg:col-span-2"
>
          {error ? (
            <ErrorBlock message={error} onRetry={onRetry} />
          ) : trend.length === 0 ? (
            <EmptyBlock
              title="No events in the selected range"
              hint="Widen the time range or send test syslog messages."
            />
          ) : (
            <>
              <TrendChart points={trend} />
              {trendNote && (
                <p className="mt-1 text-right text-[11px] text-slate-400">{trendNote}</p>
              )}
            </>
          )}
        </ChartCard>

        <ChartCard
  title="Alert Distribution"
  subtitle={`${totalAlerts} total alerts`}
  description="Breakdown of detected network issues by severity. Higher severity means greater operational impact. Select a category to filter alerts."
>
          {!error && (
            <BarList
              items={severityItems}
              colorOf={(key) => SEVERITY_COLORS[key] || '#64748b'}
              selected={selectedSeverity}
              onSelect={onSelectSeverity}
              emptyTitle="No alerts in the selected range"
              emptyHint="The detection engine raises alerts from interface, routing, auth and performance events."
            />
          )}
        </ChartCard>

        <ChartCard
  title="Incident Lifecycle"
  subtitle={`${totalIncidents} total incidents`}
  description="Tracks correlated network incidents through investigation and resolution. Select a status to filter incidents."
>
          {!error && (
            <BarList
              items={statusItems}
              colorOf={(key) => STATUS_COLORS[key] || '#64748b'}
              selected={selectedStatus}
              onSelect={onSelectStatus}
              emptyTitle="No incidents in the selected range"
              emptyHint="Incidents appear when related alerts correlate."
            />
          )}
        </ChartCard>

        <ChartCard
  title="Device Health"
  subtitle={
    health
      ? `Overall ${Math.round(health.overall_score)}/100 · ${health.band}`
      : undefined
  }
  description="Network device health scores. Select a device to open its topology view."
  className="lg:col-span-2"
>
          {!health ? (
            <LoadingBlock label="Loading health scores…" rows={2} />
          ) : worstDevices.length === 0 ? (
            <EmptyBlock
              title="No devices registered"
              hint="Devices appear after syslog traffic is ingested."
            />
          ) : (
            <BarList
              items={worstDevices.map((device) => ({
                key: String(device.device_id),
                label: device.hostname || device.ip_address,
                value: Math.round(device.score),
              }))}
              colorOf={(key) => {
                const device = worstDevices.find((item) => String(item.device_id) === key);
                return BAND_COLORS[device?.band] || '#64748b';
              }}
              selected={null}
              onSelect={(key) => onSelectDevice && onSelectDevice(Number(key))}
              emptyTitle="No devices"
            />
          )}
        </ChartCard>
      </div>
    </section>
  );
}
