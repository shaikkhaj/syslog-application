import { useCallback, useEffect, useState } from 'react';
import {
  createDevice,
  createLink,
  deleteDevice,
  deleteLink,
  fetchTopology,
  updateDevice,
  updateLink,
} from '../api/client.js';
import TopologyView from '../components/TopologyView.jsx';

const INPUT =
  'rounded border border-slate-300 px-2 py-1 text-sm w-full disabled:bg-slate-100';
const DEVICE_TYPES = ['router', 'switch', 'firewall', 'server'];

function Field({ label, children }) {
  return (
    <label className="block text-xs font-medium text-slate-500">
      {label}
      {children}
    </label>
  );
}

export default function TopologyPage() {
  const [graph, setGraph] = useState({ nodes: [], links: [] });
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState(null);
  const [mode, setMode] = useState(null); // 'device' | 'link'
  const [nodeForm, setNodeForm] = useState({});
  const [linkForm, setLinkForm] = useState({});
  const [deviceDraft, setDeviceDraft] = useState({
    hostname: '',
    ip_address: '',
    device_type: 'router',
    status: 'active',
  });
  const [linkDraft, setLinkDraft] = useState({
    source_device_id: '',
    source_interface: '',
    target_device_id: '',
    target_interface: '',
    status: 'up',
  });

  const reload = useCallback(async () => {
    try {
      setGraph(await fetchTopology());
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  // Keep editor form state in sync with the current graph/selection.
  useEffect(() => {
    if (selected?.kind === 'node') {
      const node = graph.nodes.find((n) => n.id === selected.id);
      if (node) {
        setNodeForm({
          hostname: node.hostname || '',
          device_type: node.device_type,
          status: node.status,
        });
      }
    } else if (selected?.kind === 'link') {
      const link = graph.links.find((l) => l.id === selected.id);
      if (link) {
        setLinkForm({
          source_interface: link.source_interface,
          target_interface: link.target_interface,
          status: link.status,
        });
      }
    }
  }, [selected, graph]);

  const run = async (action) => {
    try {
      await action();
      setError(null);
      await reload();
    } catch (err) {
      setError(err.message);
    }
  };

  const saveSelected = () => {
    if (selected?.kind === 'node') return run(() => updateDevice(selected.id, nodeForm));
    if (selected?.kind === 'link') return run(() => updateLink(selected.id, linkForm));
    return Promise.resolve();
  };

  const removeSelected = () => {
    const kind = selected?.kind;
    const id = selected?.id;
    return run(async () => {
      if (kind === 'node') await deleteDevice(id);
      else if (kind === 'link') await deleteLink(id);
      setSelected(null);
    });
  };

  const affectedCount = graph.nodes.filter((node) => node.affected).length;

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Network Topology</h1>
          <p className="text-sm text-slate-500">
            {graph.nodes.length} devices · {graph.links.length} links ·{' '}
            <span className="font-medium text-red-600">{affectedCount} affected</span>
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setMode(mode === 'device' ? null : 'device')}
            className="rounded bg-blue-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-700"
          >
            + Device
          </button>
          <button
            onClick={() => setMode(mode === 'link' ? null : 'link')}
            className="rounded bg-teal-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-teal-700"
          >
            + Link
          </button>
        </div>
      </header>

      {error && (
        <div className="mb-3 rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <TopologyView
            nodes={graph.nodes}
            links={graph.links}
            selected={selected}
            onSelect={setSelected}
          />
          <div className="mt-2 flex flex-wrap gap-4 text-xs text-slate-600">
            {DEVICE_TYPES.map((type) => (
              <span key={type} className="flex items-center gap-1">
                <span
                  className="inline-block h-3 w-3 rounded-full"
                  style={{
                    backgroundColor: {
                      router: '#2563eb',
                      switch: '#0d9488',
                      firewall: '#dc2626',
                      server: '#475569',
                    }[type],
                  }}
                />
                {type}
              </span>
            ))}
            <span className="flex items-center gap-1">
              <span className="inline-block h-3 w-3 rounded-full border-2 border-orange-500 bg-white" />
              affected (ring = max severity)
            </span>
            <span>dashed red = link down</span>
          </div>
        </div>

        <aside className="space-y-4">
          {mode === 'device' && (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                run(async () => {
                  await createDevice(deviceDraft);
                  setMode(null);
                  setDeviceDraft({ ...deviceDraft, hostname: '', ip_address: '' });
                });
              }}
              className="space-y-2 rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
            >
              <h2 className="text-sm font-semibold text-slate-700">Add device</h2>
              <Field label="Hostname">
                <input
                  className={INPUT}
                  value={deviceDraft.hostname}
                  onChange={(e) =>
                    setDeviceDraft({ ...deviceDraft, hostname: e.target.value })
                  }
                  required
                />
              </Field>
              <Field label="IP address">
                <input
                  className={INPUT}
                  value={deviceDraft.ip_address}
                  onChange={(e) =>
                    setDeviceDraft({ ...deviceDraft, ip_address: e.target.value })
                  }
                  placeholder="10.0.0.1"
                  required
                />
              </Field>
              <Field label="Type">
                <select
                  className={INPUT}
                  value={deviceDraft.device_type}
                  onChange={(e) =>
                    setDeviceDraft({ ...deviceDraft, device_type: e.target.value })
                  }
                >
                  {DEVICE_TYPES.map((t) => (
                    <option key={t}>{t}</option>
                  ))}
                </select>
              </Field>
              <button className="rounded bg-blue-600 px-3 py-1.5 text-sm font-semibold text-white">
                Create
              </button>
            </form>
          )}

          {mode === 'link' && (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                run(async () => {
                  await createLink({
                    ...linkDraft,
                    source_device_id: Number(linkDraft.source_device_id),
                    target_device_id: Number(linkDraft.target_device_id),
                  });
                  setMode(null);
                });
              }}
              className="space-y-2 rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
            >
              <h2 className="text-sm font-semibold text-slate-700">Add link</h2>
              <Field label="Source device">
                <select
                  className={INPUT}
                  value={linkDraft.source_device_id}
                  onChange={(e) =>
                    setLinkDraft({ ...linkDraft, source_device_id: e.target.value })
                  }
                  required
                >
                  <option value="">select…</option>
                  {graph.nodes.map((node) => (
                    <option key={node.id} value={node.id}>
                      {node.hostname || node.ip_address}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Source interface">
                <input
                  className={INPUT}
                  value={linkDraft.source_interface}
                  onChange={(e) =>
                    setLinkDraft({ ...linkDraft, source_interface: e.target.value })
                  }
                  placeholder="Gi0/1"
                  required
                />
              </Field>
              <Field label="Target device">
                <select
                  className={INPUT}
                  value={linkDraft.target_device_id}
                  onChange={(e) =>
                    setLinkDraft({ ...linkDraft, target_device_id: e.target.value })
                  }
                  required
                >
                  <option value="">select…</option>
                  {graph.nodes.map((node) => (
                    <option key={node.id} value={node.id}>
                      {node.hostname || node.ip_address}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Target interface">
                <input
                  className={INPUT}
                  value={linkDraft.target_interface}
                  onChange={(e) =>
                    setLinkDraft({ ...linkDraft, target_interface: e.target.value })
                  }
                  placeholder="Gi0/2"
                  required
                />
              </Field>
              <button className="rounded bg-teal-600 px-3 py-1.5 text-sm font-semibold text-white">
                Create
              </button>
            </form>
          )}

          {selected?.kind === 'node' && (
            <div className="space-y-2 rounded-lg border border-blue-300 bg-white p-4 shadow-sm">
              <h2 className="text-sm font-semibold text-slate-700">
                Device #{selected.id}
                {selected.data.affected && (
                  <span className="ml-2 rounded bg-red-100 px-1.5 py-0.5 text-xs text-red-700">
                    affected · {selected.data.max_severity}
                  </span>
                )}
              </h2>
              <Field label="Hostname">
                <input
                  className={INPUT}
                  value={nodeForm.hostname ?? ''}
                  onChange={(e) => setNodeForm({ ...nodeForm, hostname: e.target.value })}
                />
              </Field>
              <Field label="Type">
                <select
                  className={INPUT}
                  value={nodeForm.device_type || 'router'}
                  onChange={(e) => setNodeForm({ ...nodeForm, device_type: e.target.value })}
                >
                  {DEVICE_TYPES.map((t) => (
                    <option key={t}>{t}</option>
                  ))}
                </select>
              </Field>
              <Field label="Status">
                <select
                  className={INPUT}
                  value={nodeForm.status || 'active'}
                  onChange={(e) => setNodeForm({ ...nodeForm, status: e.target.value })}
                >
                  {['active', 'offline', 'maintenance'].map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </Field>
              <div className="flex gap-2">
                <button
                  onClick={saveSelected}
                  className="rounded bg-blue-600 px-3 py-1.5 text-sm font-semibold text-white"
                >
                  Save
                </button>
                <button
                  onClick={removeSelected}
                  className="rounded border border-red-300 px-3 py-1.5 text-sm font-semibold text-red-700 hover:bg-red-50"
                >
                  Delete
                </button>
              </div>
            </div>
          )}

          {selected?.kind === 'link' && (
            <div className="space-y-2 rounded-lg border border-teal-300 bg-white p-4 shadow-sm">
              <h2 className="text-sm font-semibold text-slate-700">Link #{selected.id}</h2>
              <Field label="Source interface">
                <input
                  className={INPUT}
                  value={linkForm.source_interface ?? ''}
                  onChange={(e) =>
                    setLinkForm({ ...linkForm, source_interface: e.target.value })
                  }
                />
              </Field>
              <Field label="Target interface">
                <input
                  className={INPUT}
                  value={linkForm.target_interface ?? ''}
                  onChange={(e) =>
                    setLinkForm({ ...linkForm, target_interface: e.target.value })
                  }
                />
              </Field>
              <Field label="Status">
                <select
                  className={INPUT}
                  value={linkForm.status || 'up'}
                  onChange={(e) => setLinkForm({ ...linkForm, status: e.target.value })}
                >
                  <option>up</option>
                  <option>down</option>
                </select>
              </Field>
              <div className="flex gap-2">
                <button
                  onClick={saveSelected}
                  className="rounded bg-teal-600 px-3 py-1.5 text-sm font-semibold text-white"
                >
                  Save
                </button>
                <button
                  onClick={removeSelected}
                  className="rounded border border-red-300 px-3 py-1.5 text-sm font-semibold text-red-700 hover:bg-red-50"
                >
                  Delete
                </button>
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
