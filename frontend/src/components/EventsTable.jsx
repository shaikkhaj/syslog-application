import { ErrorBlock, LoadingBlock } from './States.jsx';

const SEVERITY_BADGES = {
  0: 'border-red-500/30 bg-red-500/15 text-red-400',
  1: 'border-red-500/30 bg-red-500/15 text-red-400',
  2: 'border-orange-500/30 bg-orange-500/15 text-orange-400',
  3: 'border-amber-500/30 bg-amber-500/15 text-amber-400',
  4: 'border-yellow-500/30 bg-yellow-500/15 text-yellow-400',
  5: 'border-blue-500/30 bg-blue-500/15 text-blue-400',
  6: 'border-sky-500/30 bg-sky-500/15 text-sky-400',
  7: 'border-slate-600 bg-slate-700/60 text-slate-300',
};

const VENDOR_STYLES = {
  cisco: 'border-blue-500/30 bg-blue-500/10 text-blue-400',
  fortinet: 'border-red-500/30 bg-red-500/10 text-red-400',
  juniper: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400',
  linux: 'border-amber-500/30 bg-amber-500/10 text-amber-400',
  unknown: 'border-slate-600 bg-slate-700/50 text-slate-400',
};

function formatTime(value) {
  if (!value) return '—';
  return new Date(value).toLocaleString();
}

export default function EventsTable({
  events,
  total,
  loading,
  error,
  onRetry,
  filtered,
}) {
  if (error) {
    return (
      <section className="rounded-xl border border-slate-700 bg-[#142136] shadow-lg">
        <ErrorBlock message={error} onRetry={onRetry} />
      </section>
    );
  }

  if (loading) {
    return (
      <section className="rounded-xl border border-slate-700 bg-[#142136] shadow-lg">
        <LoadingBlock label="Loading events…" rows={5} />
      </section>
    );
  }

  if (!events || events.length === 0) {
    return (
      <section className="rounded-xl border border-dashed border-slate-600 bg-[#142136] p-10 text-center">
        <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-slate-800 text-xl text-slate-400">
          ◷
        </div>
        <p className="font-semibold text-slate-200">
          {filtered ? 'No matching events' : 'No syslog events yet'}
        </p>
        <p className="mt-2 text-sm text-slate-400">
          {filtered
            ? 'Try widening the time range or clearing the filters.'
            : 'Send a syslog test message to start populating the event stream.'}
        </p>
        {!filtered && (
          <code className="mt-3 inline-block rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-blue-300">
            python tools/syslog_generator.py --host 127.0.0.1 --count 20
          </code>
        )}
      </section>
    );
  }

  return (
    <section className="overflow-hidden rounded-xl border border-slate-700/80 bg-[#142136] shadow-lg shadow-black/10">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-700/80 px-5 py-4">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wider text-slate-200">
            Syslog Events
          </h2>
          <p className="mt-1 text-xs text-slate-400">
            Incoming messages collected from monitored network devices.
          </p>
        </div>
        <span className="rounded-full border border-blue-500/30 bg-blue-500/10 px-3 py-1.5 text-xs font-semibold text-blue-300">
          {Number(total || 0).toLocaleString()} total events
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-800/70 text-left text-[10px] font-bold uppercase tracking-wider text-slate-400">
            <tr>
              <th className="whitespace-nowrap px-4 py-3">Received</th>
              <th className="px-4 py-3">Severity</th>
              <th className="px-4 py-3">Hostname / IP</th>
              <th className="px-4 py-3">Vendor</th>
              <th className="px-4 py-3">Event type</th>
              <th className="px-4 py-3">Message</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700/70">
            {events.map((event) => (
              <tr
                key={event.id}
                className="transition-colors hover:bg-blue-500/5"
              >
                <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-400">
                  {formatTime(event.received_at)}
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  <span
                    className={`inline-flex rounded-md border px-2.5 py-1 text-[10px] font-bold ${
                      SEVERITY_BADGES[event.severity] || SEVERITY_BADGES[7]
                    }`}
                    title={event.severity_label || 'Unknown severity'}
                  >
                    {event.severity_label || `Level ${event.severity ?? '—'}`}
                  </span>
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  <p className="font-semibold text-slate-200">
                    {event.hostname || 'Unknown host'}
                  </p>
                  <p className="mt-0.5 font-mono text-[11px] text-slate-500">
                    {event.source_ip || '—'}
                  </p>
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  <span
                    className={`inline-flex rounded-md border px-2 py-1 text-[10px] font-semibold capitalize ${
                      VENDOR_STYLES[event.vendor] || VENDOR_STYLES.unknown
                    }`}
                  >
                    {event.vendor || 'unknown'}
                  </span>
                </td>
                <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-slate-400">
                  {event.event_type_code || '—'}
                </td>
                <td
                  className="max-w-xl truncate px-4 py-3 font-mono text-xs text-slate-300"
                  title={event.message}
                >
                  {event.message}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="border-t border-slate-700/70 px-5 py-2.5">
        <p className="text-[11px] text-slate-500">
          Showing {events.length} events in the current view
        </p>
      </div>
    </section>
  );
}