const SEVERITY_BADGES = {
  0: 'bg-red-700 text-white',
  1: 'bg-red-600 text-white',
  2: 'bg-red-500 text-white',
  3: 'bg-orange-500 text-white',
  4: 'bg-yellow-400 text-slate-900',
  5: 'bg-blue-400 text-white',
  6: 'bg-sky-200 text-sky-900',
  7: 'bg-slate-300 text-slate-700',
};

const VENDOR_STYLES = {
  cisco: 'bg-blue-100 text-blue-700',
  fortinet: 'bg-red-100 text-red-700',
  juniper: 'bg-emerald-100 text-emerald-700',
  linux: 'bg-amber-100 text-amber-700',
  unknown: 'bg-slate-100 text-slate-500',
};

function formatTime(value) {
  if (!value) return '—';
  return new Date(value).toLocaleString();
}

export default function EventsTable({ events, total }) {
  if (!events || events.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-slate-300 bg-white p-10 text-center">
        <p className="font-medium text-slate-600">No syslog events yet</p>
        <p className="mt-1 text-sm text-slate-500">
          Send a test message, e.g.{' '}
          <code className="rounded bg-slate-100 px-1 py-0.5 text-xs">
            python tools/syslog_generator.py --host 127.0.0.1 --count 20
          </code>
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Syslog Events
        </h2>
        <span className="text-xs text-slate-500">{total} total</span>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2">Received</th>
              <th className="px-4 py-2">Sev</th>
              <th className="px-4 py-2">Host</th>
              <th className="px-4 py-2">Vendor</th>
              <th className="px-4 py-2">Type</th>
              <th className="px-4 py-2">Message</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {events.map((event) => (
              <tr key={event.id} className="hover:bg-slate-50">
                <td className="whitespace-nowrap px-4 py-2 text-xs text-slate-500">
                  {formatTime(event.received_at)}
                </td>
                <td className="px-4 py-2">
                  <span
                    className={`inline-block rounded px-2 py-0.5 text-xs font-bold ${
                      SEVERITY_BADGES[event.severity] || SEVERITY_BADGES[7]
                    }`}
                    title={event.severity_label || 'unknown'}
                  >
                    {event.severity ?? '—'}
                  </span>
                </td>
                <td className="whitespace-nowrap px-4 py-2 font-medium text-slate-700">
                  {event.hostname || event.source_ip}
                </td>
                <td className="px-4 py-2">
                  <span
                    className={`rounded px-2 py-0.5 text-xs font-medium ${
                      VENDOR_STYLES[event.vendor] || VENDOR_STYLES.unknown
                    }`}
                  >
                    {event.vendor}
                  </span>
                </td>
                <td className="whitespace-nowrap px-4 py-2 text-xs text-slate-600">
                  {event.event_type_code || '—'}
                </td>
                <td className="max-w-xl truncate px-4 py-2 font-mono text-xs text-slate-700">
                  {event.message}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
