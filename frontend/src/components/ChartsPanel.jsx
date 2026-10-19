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

function ChartCard({ title, subtitle, children, className = '' }) {
  return (
    <div className={`flex flex-col rounded-lg border border-slate-200 bg-white shadow-sm ${className}`}>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          {title}
        </h2>
        {subtitle && <span className="text-xs text-slate-400">{subtitle}</span>}
      </div>
      <div className="flex-1 p-3">{children}</div>
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
        {[0, 0.5, 1].map((fraction) => (
          <g key={fraction}>
            <line
              x1={pad.l}
              x2={width - pad.r}
              y1={pad.t + fraction * innerH}
              y2={pad.t + fraction * innerH}
              stroke="#e2e8f0"
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

        <path d={areaPath} fill="#3b82f6" fillOpacity="0.12" />
        <path d={linePath} fill="none" stroke="#3b82f6" strokeWidth="2" />

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
function BarList({ items, colorOf, selected, onSelect, emptyTitle, emptyHint }) {
  const total = items.reduce((sum, item) => sum + item.value, 0);
  if (total === 0) {
    return <EmptyBlock title={emptyTitle} hint={emptyHint} />;
  }
  const max = Math.max(1, ...items.map((item) => item.value));

  return (
    <div className="space-y-1.5">
      {items.map((item) => {
        const isSelected = selected === item.key;
        const dimmed = selected && !isSelected;
        return (
          <button
            key={item.key}
            onClick={() => onSelect && onSelect(item.key)}
            className={`flex w-full items-center gap-2 rounded px-1 py-0.5 text-left transition ${
              onSelect ? 'hover:bg-slate-50' : 'cursor-default'
            } ${dimmed ? 'opacity-40' : ''} ${isSelected ? 'ring-2 ring-blue-500' : ''}`}
            title={onSelect ? `Filter by ${item.label}` : undefined}
          >
            <span className="w-24 shrink-0 truncate text-xs font-medium text-slate-600">
              {item.label}
            </span>
            <span className="h-4 flex-1 rounded bg-slate-100">
              <span
                className="block h-4 rounded"
                style={{
                  width: `${Math.max((item.value / max) * 100, item.value > 0 ? 4 : 0)}%`,
                  backgroundColor: colorOf(item.key),
                }}
              />
            </span>
            <span className="w-10 shrink-0 text-right font-mono text-xs font-semibold text-slate-700">
              {item.value}
            </span>
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

  return (
    <section id="charts" className="mb-6">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartCard title="Event trend" subtitle={rangeLabel} className="lg:col-span-2">
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

        <ChartCard title="Alerts by severity" subtitle="click to filter">
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

        <ChartCard title="Incidents by status" subtitle="click to filter">
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
          title="Device health"
          subtitle={
            health
              ? `overall ${Math.round(health.overall_score)}/100 · ${health.band}`
              : undefined
          }
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
