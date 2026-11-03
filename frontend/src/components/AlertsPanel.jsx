import { useState } from 'react';
import { acknowledgeAlert, resolveAlert } from '../api/client.js';
import { ErrorBlock, LoadingBlock } from './States.jsx';

const SEVERITY_STYLES = {
  CRITICAL: 'border-red-500/30 bg-red-500/15 text-red-400',
  HIGH: 'border-orange-500/30 bg-orange-500/15 text-orange-400',
  MEDIUM: 'border-amber-500/30 bg-amber-500/15 text-amber-400',
  LOW: 'border-yellow-500/30 bg-yellow-500/15 text-yellow-400',
  INFO: 'border-sky-500/30 bg-sky-500/15 text-sky-400',
};

const STATUS_STYLES = {
  new: 'border-red-500/30 bg-red-500/10 text-red-400',
  acknowledged: 'border-amber-500/30 bg-amber-500/10 text-amber-400',
  resolved: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400',
};

function formatTime(value) {
  if (!value) return '—';
  return new Date(value).toLocaleString();
}

function Badge({ children, className }) {
  return (
    <span className={`inline-flex whitespace-nowrap rounded-md border px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide ${className}`}>
      {children}
    </span>
  );
}

export default function AlertsPanel({
  alerts,
  live,
  onChanged,
  onError,
  loading,
  error,
  onRetry,
}) {
  const [busyId, setBusyId] = useState(null);

  const act = async (id, action) => {
    setBusyId(id);
    try {
      if (action === 'acknowledge') await acknowledgeAlert(id);
      else await resolveAlert(id);
      onChanged();
      onError(null);
    } catch (err) {
      onError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section className="overflow-hidden rounded-xl border border-slate-700/80 bg-[#142136] shadow-lg shadow-black/10">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-700/80 px-5 py-4">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wider text-slate-200">
            Alerts
          </h2>
          <p className="mt-1 text-xs text-slate-400">
            Detected network conditions requiring attention and action.
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-full border border-slate-700 bg-slate-800/70 px-3 py-1.5 text-xs text-slate-300">
          <span className={`h-2 w-2 rounded-full ${live ? 'animate-pulse bg-emerald-400' : 'bg-slate-500'}`} />
          {live ? 'Live monitoring' : 'Polling'}
        </div>
      </div>

      {error ? (
        <ErrorBlock message={error} onRetry={onRetry} />
      ) : loading ? (
        <LoadingBlock label="Loading alerts…" />
      ) : alerts.length === 0 ? (
        <p className="p-8 text-center text-sm text-slate-400">
          No alerts yet. The detection engine is monitoring network events.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-800/70 text-left text-[10px] font-bold uppercase tracking-wider text-slate-400">
              <tr>
                <th className="px-4 py-3">Severity</th>
                <th className="px-4 py-3">Alert description</th>
                <th className="px-4 py-3">Event type</th>
                <th className="px-4 py-3 text-center">Count</th>
                <th className="px-4 py-3">Last detected</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/70">
              {alerts.map((alert) => (
                <tr key={alert.id} className="transition-colors hover:bg-blue-500/5">
                  <td className="whitespace-nowrap px-4 py-3">
                    <Badge className={SEVERITY_STYLES[alert.severity] || 'border-slate-600 bg-slate-700 text-slate-300'}>
                      {alert.severity}
                    </Badge>
                  </td>
                  <td className="max-w-md px-4 py-3 font-medium text-slate-200">
                    {alert.title}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-slate-400">
                    {alert.event_type}
                  </td>
                  <td className="px-4 py-3 text-center font-mono font-semibold text-slate-200">
                    {alert.event_count}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-400">
                    {formatTime(alert.last_seen_at)}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3">
                    <Badge className={STATUS_STYLES[alert.status] || 'border-slate-600 bg-slate-700 text-slate-300'}>
                      {alert.status}
                    </Badge>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3">
                    {alert.status === 'new' && (
                      <button
                        onClick={() => act(alert.id, 'acknowledge')}
                        disabled={busyId === alert.id}
                        className="mr-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-1.5 text-xs font-semibold text-amber-300 hover:bg-amber-500/20 disabled:opacity-50"
                      >
                        {busyId === alert.id ? 'Working…' : 'Acknowledge'}
                      </button>
                    )}
                    {alert.status !== 'resolved' && (
                      <button
                        onClick={() => act(alert.id, 'resolve')}
                        disabled={busyId === alert.id}
                        className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-1.5 text-xs font-semibold text-emerald-300 hover:bg-emerald-500/20 disabled:opacity-50"
                      >
                        Resolve
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}