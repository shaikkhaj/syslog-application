
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  fetchNotifications,
  fetchUnreadCount,
  markNotificationRead,
  markAllNotificationsRead,
} from '../api/client.js';

const SEVERITY_STYLES = {
  CRITICAL: 'bg-red-700 text-white',
  HIGH: 'bg-red-500 text-white',
  MEDIUM: 'bg-orange-500 text-white',
  LOW: 'bg-yellow-400 text-slate-900',
  INFO: 'bg-sky-200 text-sky-900',
};

const TYPE_LABELS = { alert: 'Alert', incident: 'Incident', escalation: 'Escalation' };

function formatTime(value) {
  if (!value) return '—';
  return new Date(value).toLocaleString();
}

export default function NotificationBell() {
  const [unreadCount, setUnreadCount] = useState(0);
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const panelRef = useRef(null);
  const pollRef = useRef(null);

  const loadUnread = useCallback(async () => {
    try {
      const data = await fetchUnreadCount();
      setUnreadCount(data.unread_count ?? 0);
    } catch { /* keep last known value */ }
  }, []);

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchNotifications({ limit: 30 });
      setNotifications(data.items || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUnread();
    pollRef.current = setInterval(loadUnread, 15_000);
    const onNotify = () => loadUnread();
    window.addEventListener('notification-update', onNotify);
    return () => {
      clearInterval(pollRef.current);
      window.removeEventListener('notification-update', onNotify);
    };
  }, [loadUnread]);

  useEffect(() => {
    if (open) loadList();
  }, [open, loadList]);

  useEffect(() => {
    if (!open) return undefined;
    const handler = (event) => {
      if (panelRef.current && !panelRef.current.contains(event.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);


  const markRead = async (id) => {
    try {
      await markNotificationRead(id);
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
    } catch (err) {
      setError(err.message);
    }
  };

  const markAllRead = async () => {
    try {
      await markAllNotificationsRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="relative" ref={panelRef}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-700"
        aria-label={`Notifications (${unreadCount} unread)`}
      >
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
        </svg>
        {unreadCount > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-bold text-white">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-2 w-96 rounded-lg border border-slate-200 bg-white shadow-lg">
          <div className="flex items-center justify-between border-b border-slate-200 px-4 py-2">
            <h3 className="text-sm font-semibold text-slate-700">Notifications</h3>
            {unreadCount > 0 && (
              <button onClick={markAllRead} className="text-xs text-blue-600 hover:underline">
                Mark all read
              </button>
            )}
          </div>
          {error && <p className="px-4 py-2 text-xs text-red-600">{error}</p>}
          {loading ? (
            <p className="px-4 py-6 text-center text-sm text-slate-400">Loading…</p>
          ) : notifications.length === 0 ? (
            <p className="px-4 py-6 text-center text-sm text-slate-400">No notifications yet.</p>
          ) : (
            <ul className="max-h-96 divide-y divide-slate-100 overflow-y-auto">
              {notifications.map((n) => (
                <li key={n.id} className={`flex items-start gap-3 px-4 py-3 text-sm ${n.is_read ? 'opacity-60' : ''}`}>
                  <span className={`mt-0.5 inline-block shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold ${SEVERITY_STYLES[n.severity] || 'bg-slate-300'}`}>
                    {n.severity}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium text-slate-800">{n.title}</p>
                    {n.message && <p className="mt-0.5 text-xs text-slate-500">{n.message}</p>}
                    <p className="mt-1 text-[11px] text-slate-400">
                      {TYPE_LABELS[n.type] || n.type} · {formatTime(n.created_at)}
                    </p>
                  </div>
                  {!n.is_read && (
                    <button onClick={() => markRead(n.id)} className="shrink-0 text-xs text-blue-600 hover:underline">
                      Mark read
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

