import { useState } from 'react';
import Dashboard from './pages/Dashboard.jsx';
import TopologyPage from './pages/TopologyPage.jsx';

export default function App() {
  const [page, setPage] = useState('dashboard');

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
              onClick={() => setPage(key)}
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
      {page === 'dashboard' ? <Dashboard /> : <TopologyPage />}
    </div>
  );
}
