/**
 * Shared loading / error / empty state blocks (Phase 6).
 * Reused by dashboard panels and charts so states stay consistent.
 */

export function LoadingBlock({ label = 'Loading…', rows = 3 }) {
  return (
    <div className="animate-pulse p-4" role="status" aria-label={label}>
      <p className="mb-3 text-xs font-medium uppercase tracking-wide text-slate-400">
        {label}
      </p>
      <div className="space-y-2">
        {Array.from({ length: rows }, (_, index) => (
          <div key={index} className="h-4 rounded bg-slate-200" />
        ))}
      </div>
    </div>
  );
}

export function ErrorBlock({ message, onRetry }) {
  return (
    <div className="p-4">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded border border-red-200 bg-red-50 px-3 py-2">
        <p className="text-sm text-red-700">
          {message || 'Request failed'} — is the backend running?
        </p>
        {onRetry && (
          <button
            onClick={onRetry}
            className="rounded border border-red-300 px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-100"
          >
            Retry
          </button>
        )}
      </div>
    </div>
  );
}

export function EmptyBlock({ title, hint }) {
  return (
    <div className="border-dashed p-8 text-center">
      <p className="font-medium text-slate-600">{title}</p>
      {hint && <p className="mt-1 text-sm text-slate-500">{hint}</p>}
    </div>
  );
}
