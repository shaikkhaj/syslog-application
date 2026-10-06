const STATUS_STYLES = {
  ok: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  degraded: 'bg-amber-100 text-amber-700 border-amber-200',
  error: 'bg-red-100 text-red-700 border-red-200',
  disabled: 'bg-slate-200 text-slate-600 border-slate-300',
  stopped: 'bg-slate-200 text-slate-600 border-slate-300',
};

function CheckChip({ label, check }) {
  const status = check?.status || 'stopped';
  return (
    <div className={`rounded border px-2 py-1 text-xs font-medium ${STATUS_STYLES[status] || STATUS_STYLES.stopped}`}>
      {label}: {status}
    </div>
  );
}

export default function HealthCard({ health }) {
  if (!health) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <p className="text-sm text-slate-500">Loading system health…</p>
      </div>
    );
  }

  const pipeline = health.checks?.syslog?.pipeline;
  const overall = STATUS_STYLES[health.status] || STATUS_STYLES.stopped;

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          System Health
        </h2>
        <span className={`rounded-full border px-3 py-1 text-xs font-bold uppercase ${overall}`}>
          {health.status}
        </span>
      </div>

      <div className="flex flex-wrap gap-2">
        <CheckChip label="Database" check={health.checks?.database} />
        <CheckChip label="Redis" check={health.checks?.redis} />
        <CheckChip label="Syslog" check={health.checks?.syslog} />
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-600 sm:grid-cols-4">
        <div>
          <span className="block font-semibold text-slate-400">Version</span>
          {health.version}
        </div>
        <div>
          <span className="block font-semibold text-slate-400">Uptime</span>
          {Math.floor(health.uptime_seconds)}s
        </div>
        {pipeline && (
          <>
            <div>
              <span className="block font-semibold text-slate-400">Received</span>
              {pipeline.submitted}
            </div>
            <div>
              <span className="block font-semibold text-slate-400">Stored</span>
              {pipeline.stored} stored · {pipeline.dropped} dropped
            </div>
          </>
        )}
      </div>
    </div>
  );
}
