
import { ErrorBlock } from './States.jsx';

const STATUS_STYLES = {
  ok: {
    badge: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400',
    dot: 'bg-emerald-400',
    label: 'Operational',
  },
  degraded: {
    badge: 'border-amber-500/30 bg-amber-500/10 text-amber-400',
    dot: 'bg-amber-400',
    label: 'Degraded',
  },
  error: {
    badge: 'border-red-500/30 bg-red-500/10 text-red-400',
    dot: 'bg-red-400',
    label: 'Error',
  },
  disabled: {
    badge: 'border-slate-600 bg-slate-700/40 text-slate-400',
    dot: 'bg-slate-500',
    label: 'Disabled',
  },
  stopped: {
    badge: 'border-slate-600 bg-slate-700/40 text-slate-400',
    dot: 'bg-slate-500',
    label: 'Stopped',
  },
};

function CheckCard({ label, check }) {
  const status = check?.status || 'stopped';
  const style = STATUS_STYLES[status] || STATUS_STYLES.stopped;

  return (
    <div className="rounded-xl border border-slate-700/80 bg-slate-800/40 p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-slate-300">
          {label}
        </span>

        <span className={`rounded-full border px-2 py-1 text-[10px] font-bold ${style.badge}`}>
          {style.label}
        </span>
      </div>

      <div className="mt-3 flex items-center gap-2">
        <span className={`h-2.5 w-2.5 rounded-full ${style.dot}`} />
        <span className="text-sm font-medium capitalize text-slate-200">
          {status}
        </span>
      </div>
    </div>
  );
}

function StatCard({ label, value, description, color, icon }) {
  return (
    <div className="rounded-xl border border-slate-700/80 bg-slate-800/40 p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-slate-400">
          {label}
        </span>
        <span className={`text-lg ${color}`}>
          {icon}
        </span>
      </div>

      <p className={`mt-2 text-2xl font-bold tracking-tight ${color}`}>
        {Number(value ?? 0).toLocaleString()}
      </p>

      <p className="mt-1 text-[11px] text-slate-500">
        {description}
      </p>
    </div>
  );
}

function formatUptime(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remainingSeconds = total % 60;

  if (days > 0) return `${days}d ${hours}h ${minutes}m`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${remainingSeconds}s`;

  return `${remainingSeconds}s`;
}

export default function HealthCard({ health, error, onRetry }) {
  if (error) {
    return (
      <div className="rounded-xl border border-slate-700 bg-[#142136] p-4 shadow-lg">
        <ErrorBlock message={error} onRetry={onRetry} />
      </div>
    );
  }

  if (!health) {
    return (
      <div className="rounded-xl border border-slate-700 bg-[#142136] p-5 shadow-lg">
        <p className="text-sm text-slate-400">
          Loading system health...
        </p>
      </div>
    );
  }

  const pipeline = health.checks?.syslog?.pipeline;
  const overall = STATUS_STYLES[health.status] || STATUS_STYLES.stopped;

  return (
    <section className="rounded-xl border border-slate-700/80 bg-[#142136] p-5 shadow-lg shadow-black/10">

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wider text-slate-200">
            System Health
          </h2>
          <p className="mt-1 text-xs text-slate-400">
            Live status of monitoring infrastructure and syslog ingestion
          </p>
        </div>

        <span className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-bold uppercase ${overall.badge}`}>
          <span className={`h-2 w-2 rounded-full ${overall.dot}`} />
          {health.status || 'Unknown'}
        </span>
      </div>

      {/* Service health */}
      <div className="mt-5">
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
          Infrastructure Services
        </h3>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <CheckCard
            label="Database"
            check={health.checks?.database}
          />

          <CheckCard
            label="Redis"
            check={health.checks?.redis}
          />

          <CheckCard
            label="Syslog"
            check={health.checks?.syslog}
          />
        </div>
      </div>

      {/* Syslog ingestion */}
      {pipeline && (
        <div className="mt-6">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Syslog Ingestion
              </h3>
              <p className="mt-1 text-[11px] text-slate-500">
                Message processing statistics reported by the ingestion pipeline
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <StatCard
              label="Messages Received"
              value={pipeline.submitted}
              description="Messages submitted to pipeline"
              color="text-blue-400"
              icon="↓"
            />

            <StatCard
              label="Messages Stored"
              value={pipeline.stored}
              description="Messages successfully stored"
              color="text-emerald-400"
              icon="✓"
            />

            <StatCard
              label="Messages Dropped"
              value={pipeline.dropped}
              description="Messages not stored"
              color="text-red-400"
              icon="!"
            />
          </div>
        </div>
      )}

      {/* System information */}
      <div className="mt-5 border-t border-slate-700/80 pt-4">
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
          System Information
        </h3>

        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div>
            <p className="text-[11px] text-slate-500">Application Version</p>
            <p className="mt-1 text-sm font-semibold text-slate-200">
              {health.version || 'N/A'}
            </p>
          </div>

          <div>
            <p className="text-[11px] text-slate-500">System Uptime</p>
            <p className="mt-1 text-sm font-semibold text-slate-200">
              {formatUptime(health.uptime_seconds)}
            </p>
          </div>

          <div>
            <p className="text-[11px] text-slate-500">Overall Status</p>
            <p className="mt-1 text-sm font-semibold capitalize text-slate-200">
              {health.status || 'Unknown'}
            </p>
          </div>

          <div>
            <p className="text-[11px] text-slate-500">Monitoring</p>
            <p className="mt-1 text-sm font-semibold text-emerald-400">
              Health checks active
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
