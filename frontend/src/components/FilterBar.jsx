import { useState } from 'react';

const SEVERITIES = [
  { value: '', label: 'All severities' },
  { value: '0', label: '0 · Emergency' },
  { value: '1', label: '1 · Alert' },
  { value: '2', label: '2 · Critical' },
  { value: '3', label: '3 · Error' },
  { value: '4', label: '4 · Warning' },
  { value: '5', label: '5 · Notice' },
  { value: '6', label: '6 · Info' },
  { value: '7', label: '7 · Debug' },
];

export default function FilterBar({ filters, onApply }) {
  const [draft, setDraft] = useState(filters);

  const update = (key, value) => setDraft((prev) => ({ ...prev, [key]: value }));

  const submit = (event) => {
    event.preventDefault();
    onApply(draft);
  };

  const reset = () => {
    const empty = { q: '', severity: '', device_ip: '', event_type: '' };
    setDraft(empty);
    onApply(empty);
  };

  const inputClass =
    'rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500';

  return (
    <form
      onSubmit={submit}
      className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
    >
      <label className="flex flex-col gap-1 text-xs font-medium text-slate-500">
        Search
        <input
          type="text"
          value={draft.q}
          onChange={(e) => update('q', e.target.value)}
          placeholder="message / hostname…"
          className={`${inputClass} w-64`}
        />
      </label>

      <label className="flex flex-col gap-1 text-xs font-medium text-slate-500">
        Severity
        <select
          value={draft.severity}
          onChange={(e) => update('severity', e.target.value)}
          className={inputClass}
        >
          {SEVERITIES.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1 text-xs font-medium text-slate-500">
        Source IP
        <input
          type="text"
          value={draft.device_ip}
          onChange={(e) => update('device_ip', e.target.value)}
          placeholder="10.0.0.1"
          className={`${inputClass} w-40`}
        />
      </label>

      <label className="flex flex-col gap-1 text-xs font-medium text-slate-500">
        Event type
        <input
          type="text"
          value={draft.event_type}
          onChange={(e) => update('event_type', e.target.value)}
          placeholder="link_down…"
          className={`${inputClass} w-40`}
        />
      </label>

      <button
        type="submit"
        className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
      >
        Apply
      </button>
      <button
        type="button"
        onClick={reset}
        className="rounded border border-slate-300 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
      >
        Reset
      </button>
    </form>
  );
}
