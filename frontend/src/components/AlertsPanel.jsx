import { useState } from 'react';
import { acknowledgeAlert, resolveAlert } from '../api/client.js';

const SEVERITY_STYLES = {
  CRITICAL: 'bg-red-700 text-white',
  HIGH: 'bg-red-500 text-white',
  MEDIUM: 'bg-orange-500 text-white',
  LOW: 'bg-yellow-400 text-slate-900',
  INFO: 'bg-sky-200 text-sky-900',
};

const STATUS_STYLES = {
  new: 'bg-red-100 text-red-700',
  acknowledged: 'bg-amber-100 text-amber-700',
  resolved: 'bg-emerald-100 text-emerald-700',
};

function formatTime(value) {
  if (!value) return '—';
  return new Date(value).toLocaleString();
}

export default function AlertsPanel({ alerts, live, onChanged, onError }) {
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
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Alerts
        </h2>
        <span className="flex items-center gap-2 text-xs text-slate-500">
          <span
            className={`inline-block h-2 w-2 rounded-full ${
              live ? 'animate-pulse bg-emerald-500' : 'bg-slate-400'
            }`}
          />
          {live ? 'live (websocket)' : 'polling'}
        </span>
      </div>

      {alerts.length === 0 ? (
        <p className="p-6 text-center text-sm text-slate-500">
          No alerts yet — detection is watching for interface, routing,
          authentication and performance events.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-2">Severity</th>
                <th className="px-4 py-2">Alert</th>
                <th className="px-4 py-2">Type</th>
                <th className="px-4 py-2">Count</th>
                <th className="px-4 py-2">Last seen</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {alerts.map((alert) => (
                <tr key={alert.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2">
                    <span
                      className={`inline-block rounded px-2 py-0.5 text-xs font-bold ${
                        SEVERITY_STYLES[alert.severity] || 'bg-slate-300'
                      }`}
                    >
                      {alert.severity}
                    </span>
                  </td>
                  <td className="max-w-md px-4 py-2 text-slate-700">
                    {alert.title}
                  </td>
                  <td className="whitespace-nowrap px-4 py-2 font-mono text-xs text-slate-600">
                    {alert.event_type}
                  </td>
                  <td className="px-4 py-2 text-center">{alert.event_count}</td>
                  <td className="whitespace-nowrap px-4 py-2 text-xs text-slate-500">
                    {formatTime(alert.last_seen_at)}
                  </td>
                  <td className="px-4 py-2">
                    <span
                      className={`rounded px-2 py-0.5 text-xs font-medium ${
                        STATUS_STYLES[alert.status] || 'bg-slate-100'
                      }`}
                    >
                      {alert.status}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-2">
                    {alert.status === 'new' && (
                      <button
                        onClick={() => act(alert.id, 'acknowledge')}
                        disabled={busyId === alert.id}
                        className="mr-2 rounded border border-amber-300 px-2 py-1 text-xs font-medium text-amber-700 hover:bg-amber-50 disabled:opacity-50"
                      >
                        Ack
                      </button>
                    )}
                    {alert.status !== 'resolved' && (
                      <button
                        onClick={() => act(alert.id, 'resolve')}
                        disabled={busyId === alert.id}
                        className="rounded border border-emerald-300 px-2 py-1 text-xs font-medium text-emerald-700 hover:bg-emerald-50 disabled:opacity-50"
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
    </div>
  );
}
