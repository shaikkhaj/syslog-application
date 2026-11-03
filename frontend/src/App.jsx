import { useEffect, useState } from 'react';
import Dashboard from './pages/Dashboard.jsx';
import TopologyPage from './pages/TopologyPage.jsx';
import NotificationBell from './components/NotificationBell.jsx';

function parseHash() {
  const raw = window.location.hash.replace(/^#\/?/, '');
  const [path, queryString = ''] = raw.split('?');
  const page = path === 'topology' ? 'topology' : 'dashboard';
  const params = new URLSearchParams(queryString);
  const device = params.get('device');

  return { page, device: device ? Number(device) : null };
}

const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard', icon: '▦' },
  { id: 'topology', label: 'Network Topology', icon: '◇' },
];

export default function App() {
  const [{ page, device }, setRoute] = useState(parseHash);

  useEffect(() => {
    const onHashChange = () => setRoute(parseHash());
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  const navigate = (nextPage) => {
    window.location.hash =
      nextPage === 'topology' ? '#/topology' : '#/dashboard';
  };

  return (
    <div className="min-h-screen bg-[#0b1220] text-slate-100">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-slate-800 bg-[#101a2b] lg:flex">
        <div className="flex h-20 items-center gap-3 border-b border-slate-800 px-6">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600 text-xl font-bold shadow-lg shadow-blue-950/40">
            N
          </div>
          <div>
            <h1 className="text-sm font-bold tracking-wide text-white">
              NETWATCH
            </h1>
            <p className="mt-0.5 text-[10px] uppercase tracking-[0.2em] text-slate-500">
              Network operations
            </p>
          </div>
        </div>

        <div className="px-4 pt-8">
          <p className="mb-3 px-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
            Workspace
          </p>

          <nav className="space-y-2" aria-label="Main navigation">
            {NAV_ITEMS.map((item) => {
              const active = page === item.id;

              return (
                <button
                  key={item.id}
                  onClick={() => navigate(item.id)}
                  className={`group flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left text-sm font-medium transition ${
                    active
                      ? 'bg-blue-600/15 text-blue-300 ring-1 ring-inset ring-blue-500/30'
                      : 'text-slate-400 hover:bg-slate-800/80 hover:text-white'
                  }`}
                >
                  <span
                    className={`flex h-8 w-8 items-center justify-center rounded-lg text-lg ${
                      active
                        ? 'bg-blue-600 text-white'
                        : 'bg-slate-800 text-slate-400 group-hover:text-white'
                    }`}
                  >
                    {item.icon}
                  </span>
                  {item.label}
                  {active && (
                    <span className="ml-auto h-1.5 w-1.5 rounded-full bg-blue-400" />
                  )}
                </button>
              );
            })}
          </nav>
        </div>

        <div className="mt-auto border-t border-slate-800 p-5">
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
            <div className="flex items-center gap-2">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-50" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
              </span>
              <span className="text-xs font-medium text-emerald-300">
                Platform active
              </span>
            </div>
            <p className="mt-2 text-[11px] leading-5 text-slate-500">
              Network monitoring and incident visibility
            </p>
          </div>
          <p className="mt-4 text-center text-[10px] text-slate-600">
            Network Monitoring Platform
          </p>
        </div>
      </aside>

      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-slate-800 bg-[#101a2b]/95 px-4 backdrop-blur-md sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-sm font-bold lg:hidden">
              N
            </div>
            <div>
              <p className="text-sm font-semibold text-white">
                {page === 'topology' ? 'Network Topology' : 'Dashboard'}
              </p>
              <p className="hidden text-[11px] text-slate-500 sm:block">
                Network visibility and infrastructure monitoring
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <span className="hidden items-center gap-2 rounded-full border border-slate-700 bg-slate-900 px-3 py-1.5 text-[11px] text-slate-400 sm:flex">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              Live monitoring
            </span>
            <NotificationBell />
          </div>
        </header>

        <nav className="flex gap-2 border-b border-slate-800 bg-[#101a2b] px-4 py-2 lg:hidden">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              onClick={() => navigate(item.id)}
              className={`rounded-lg px-3 py-2 text-xs font-medium transition ${
                page === item.id
                  ? 'bg-blue-600 text-white'
                  : 'text-slate-400 hover:bg-slate-800 hover:text-white'
              }`}
            >
              {item.label}
            </button>
          ))}
        </nav>

        <main className="min-h-[calc(100vh-4rem)]">
          {page === 'dashboard' ? (
            <Dashboard />
          ) : (
            <TopologyPage initialDeviceId={device} />
          )}
        </main>
      </div>
    </div>
  );
}