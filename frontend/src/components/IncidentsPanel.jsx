import { useCallback, useState } from 'react';
import {
  acknowledgeIncident,
  closeIncident,
  fetchIncidentRca,
  fetchIncidentTimeline,
  resolveIncident,
} from '../api/client.js';
import { ErrorBlock, LoadingBlock } from './States.jsx';

const SEVERITY_STYLES = {
  CRITICAL: 'bg-red-700 text-white',
  HIGH: 'bg-red-500 text-white',
  MEDIUM: 'bg-orange-500 text-white',
  LOW: 'bg-yellow-400 text-slate-900',
};

const STATUS_STYLES = {
  OPEN: 'bg-red-100 text-red-700',
  INVESTIGATING: 'bg-amber-100 text-amber-700',
  ACKNOWLEDGED: 'bg-blue-100 text-blue-700',
  RESOLVED: 'bg-emerald-100 text-emerald-700',
  CLOSED: 'bg-slate-200 text-slate-600',
};

function formatTime(value) {
  if (!value) return '—';
  return new Date(value).toLocaleString();
}

function TimelineEntryRow({ entry }) {
  const label =
    entry.type === 'state_change'
      ? `${entry.from_status || 'CREATED'} → ${entry.to_status}` +
        (entry.actor ? ` (${entry.actor})` : '')
      : entry.type === 'alert'
        ? `Alert: ${entry.title}${entry.recovery ? ' · recovery' : ''}`
        : `Event: ${entry.message}`;
  return (
    <li className="flex gap-3 text-xs">
      <span className="w-40 shrink-0 text-slate-400">
        {formatTime(entry.timestamp)}
      </span>
      <span className="text-slate-700">{label}</span>
    </li>
  );
}

function IncidentRow({ incident, busy, expanded, timeline, rca, onAct, onToggle }) {
  return (
    <>
      <tr className="hover:bg-slate-50">
        <td className="px-4 py-2">
          <span
            className={`inline-block rounded px-2 py-0.5 text-xs font-bold ${
              SEVERITY_STYLES[incident.severity] || 'bg-slate-300'
            }`}
          >
            {incident.severity}
          </span>
        </td>
        <td className="max-w-md px-4 py-2">
          <button
            onClick={onToggle}
            className="text-left font-medium text-slate-700 hover:text-blue-600"
            title="Show timeline"
          >
            {incident.title}
          </button>
          <div className="text-xs text-slate-400">
            #{incident.id} · {incident.category || 'uncategorized'} ·{' '}
            {(incident.affected_devices || []).length} device(s)
          </div>
        </td>
        <td className="px-4 py-2 font-mono text-xs">{incident.score}</td>
        <td className="px-4 py-2 text-center">{incident.alert_count}</td>
        <td className="max-w-sm px-4 py-2 text-xs text-slate-600">
          {incident.root_cause || '—'}
          {incident.confidence != null && (
            <span className="ml-1 text-slate-400">
              ({Math.round(incident.confidence * 100)}%)
            </span>
          )}
        </td>
        <td className="px-4 py-2">
          <span
            className={`rounded px-2 py-0.5 text-xs font-medium ${
              STATUS_STYLES[incident.status] || 'bg-slate-100'
            }`}
          >
            {incident.status}
          </span>
        </td>
        <td className="whitespace-nowrap px-4 py-2">
          {(incident.status === 'OPEN' ||
            incident.status === 'INVESTIGATING') && (
            <button
              onClick={() => onAct(incident.id, 'acknowledge')}
              disabled={busy}
              className="mr-1 rounded border border-blue-300 px-2 py-1 text-xs font-medium text-blue-700 hover:bg-blue-50 disabled:opacity-50"
            >
              Ack
            </button>
          )}
          {incident.status !== 'RESOLVED' && incident.status !== 'CLOSED' && (
            <button
              onClick={() => onAct(incident.id, 'resolve')}
              disabled={busy}
              className="mr-1 rounded border border-emerald-300 px-2 py-1 text-xs font-medium text-emerald-700 hover:bg-emerald-50 disabled:opacity-50"
            >
              Resolve
            </button>
          )}
          {incident.status === 'RESOLVED' && (
            <button
              onClick={() => onAct(incident.id, 'close')}
              disabled={busy}
              className="rounded border border-slate-300 px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
            >
              Close
            </button>
          )}
        </td>
      </tr>
      {expanded && (
        <tr className="bg-slate-50">
          <td colSpan={7} className="px-6 py-3">
            {rca && (
              <div className="mb-3 rounded border border-indigo-200 bg-indigo-50/60 p-3">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-indigo-700">
                  Root-cause analysis
                </p>
                <p className="mb-2 text-sm text-slate-700">{rca.summary}</p>
                {rca.device_ranking?.length > 0 && (
                  <ul className="mb-2 space-y-1">
                    {rca.device_ranking.map((device) => (
                      <li key={device.device_id} className="text-xs text-slate-600">
                        <span className="font-mono font-semibold text-slate-800">
                          #{device.rank}
                        </span>{' '}
                        <span className="font-medium">
                          {device.hostname || device.ip_address || `device ${device.device_id}`}
                        </span>{' '}
                        <span className="font-mono text-slate-500">
                          ({device.score})
                        </span>
                        {device.reasons?.length > 0 && (
                          <span className="text-slate-400"> — {device.reasons.join('; ')}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
                {rca.upstream_dependencies?.length > 0 && (
                  <p className="text-xs text-slate-600">
                    <span className="font-medium">Upstream dependencies:</span>{' '}
                    {rca.upstream_dependencies
                      .map(
                        (dep) =>
                          `${dep.hostname || dep.ip_address || `device ${dep.device_id}`} (${dep.hops} hop${dep.hops === 1 ? '' : 's'})`
                      )
                      .join(' · ')}
                  </p>
                )}
              </div>
            )}
            <ul className="space-y-1">
              {timeline.map((entry, index) => (
                <TimelineEntryRow key={index} entry={entry} />
              ))}
            </ul>
          </td>
        </tr>
      )}
    </>
  );
}

export default function IncidentsPanel({
  incidents,
  live,
  onChanged,
  onError,
  loading,
  error,
  onRetry,
}) {
  const [busyId, setBusyId] = useState(null);
  const [expandedId, setExpandedId] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [rca, setRca] = useState(null);

  const act = async (id, action) => {
    setBusyId(id);
    try {
      if (action === 'acknowledge') await acknowledgeIncident(id);
      else if (action === 'resolve') await resolveIncident(id);
      else await closeIncident(id);
      onChanged();
      onError(null);
    } catch (err) {
      onError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  const toggleTimeline = useCallback(async (id) => {
    if (expandedId === id) {
      setExpandedId(null);
      setRca(null);
      return;
    }
    try {
      const [timelineData, rcaData] = await Promise.all([
        fetchIncidentTimeline(id),
        fetchIncidentRca(id),
      ]);
      setTimeline(timelineData.entries);
      setRca(rcaData);
      setExpandedId(id);
    } catch (err) {
      /* keep panel usable even if timeline/RCA fails */
    }
  }, [expandedId]);

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Incidents
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

      {error ? (
        <ErrorBlock message={error} onRetry={onRetry} />
      ) : loading ? (
        <LoadingBlock label="Loading incidents…" />
      ) : incidents.length === 0 ? (
        <p className="p-6 text-center text-sm text-slate-500">
          No incidents yet — related alerts are correlated automatically.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-2">Sev</th>
                <th className="px-4 py-2">Incident</th>
                <th className="px-4 py-2">Score</th>
                <th className="px-4 py-2">Alerts</th>
                <th className="px-4 py-2">Root cause</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {incidents.map((incident) => (
                <IncidentRow
                  key={incident.id}
                  incident={incident}
                  busy={busyId === incident.id}
                  expanded={expandedId === incident.id}
                  timeline={timeline}
                  rca={expandedId === incident.id ? rca : null}
                  onAct={act}
                  onToggle={() => toggleTimeline(incident.id)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
