import { useEffect, useState } from 'react';
import Dashboard from './pages/Dashboard.jsx';
import TopologyPage from './pages/TopologyPage.jsx';

/** Parse `#/topology?device=3` into `{ page, device }`. */
function parseHash() {
  const raw = window.location.hash.replace(/^#\/?/, '');
  const [path, queryString = ''] = raw.split('?');
  const page = path === 'topology' ? 'topology' : 'dashboard';
  const params = new URLSearchParams(queryString);
  const device = params.get('device');
  return { page, device: device ? Number(device) : null };
}

export default function App() {
  const [{ page, device }, setRoute] = useState(parseHash);

  useEffect(() => {
    const onHashChange = () => setRoute(parseHash());
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  const navigate = (nextPage) => {
    window.location.hash = nextPage === 'topology' ? '#/topology' : '#/dashboard';
  };

  return (
    <div>
      <nav className="border-b border-slate-200 bg-white px-6 py-2">
        <div className="mx-auto flex max-w-7xl gap-4">
          {[
            ['dashboard', 'Dashboard'],
            ['topology', 'Topology'],
          ].map(([key, label]) => (
            <button
              key={key}
              onClick={() => navigate(key)}
              className={`rounded px-3 py-1 text-sm font-medium ${
                page === key
                  ? 'bg-blue-600 text-white'
                  : 'text-slate-600 hover:bg-slate-100'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </nav>
      {page === 'dashboard' ? <Dashboard /> : <TopologyPage initialDeviceId={device} />}
    </div>
  );
}
