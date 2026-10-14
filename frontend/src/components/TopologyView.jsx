import { useEffect, useRef, useState } from 'react';

const TYPE_COLORS = {
  router: '#2563eb', // blue
  switch: '#0d9488', // teal
  firewall: '#dc2626', // red
  server: '#475569', // slate
};

const SEVERITY_RING = {
  CRITICAL: '#b91c1c',
  HIGH: '#ea580c',
  MEDIUM: '#f59e0b',
  LOW: '#eab308',
  INFO: '#38bdf8',
};

const BAND_COLORS = {
  critical: '#dc2626',
  degraded: '#d97706',
  healthy: '#059669',
};

function severityRing(node) {
  return node.affected ? SEVERITY_RING[node.max_severity] || '#f97316' : '#cbd5e1';
}

/**
 * Dependency-free interactive SVG topology:
 *  - deterministic circle layout, nodes stay where users drag them
 *  - click a node / link to select it (parent renders the editor panel)
 *  - optional `health` map (device_id → health item) draws score badges
 */
export default function TopologyView({ nodes, links, health = {}, selected, onSelect }) {
  const positionsRef = useRef({});
  const dragRef = useRef(null);
  const [, forceRender] = useState(0);

  // Place newly seen nodes on a circle (keeping user-dragged positions).
  useEffect(() => {
    const count = nodes.length;
    nodes.forEach((node, index) => {
      if (!positionsRef.current[node.id]) {
        const angle = (2 * Math.PI * index) / Math.max(count, 1) - Math.PI / 2;
        positionsRef.current[node.id] = {
          x: 400 + 260 * Math.cos(angle),
          y: 240 + 170 * Math.sin(angle),
        };
      }
    });
    forceRender((value) => value + 1);
  }, [nodes]);

  const positionOf = (id) =>
    positionsRef.current[id] || { x: 400, y: 240 };

  const onMouseMove = (event) => {
    const drag = dragRef.current;
    if (!drag) return;
    const svg = event.currentTarget;
    const rect = svg.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * 800;
    const y = ((event.clientY - rect.top) / rect.height) * 480;
    positionsRef.current[drag] = { x, y };
    forceRender((value) => value + 1);
  };

  return (
    <svg
      viewBox="0 0 800 480"
      className="h-[520px] w-full cursor-pointer select-none rounded-lg border border-slate-200 bg-slate-50"
      onMouseMove={onMouseMove}
      onMouseUp={() => {
        dragRef.current = null;
      }}
      onMouseLeave={() => {
        dragRef.current = null;
      }}
    >
      {/* links */}
      {links.map((link) => {
        const from = positionOf(link.source_device_id);
        const to = positionOf(link.target_device_id);
        const isSelected = selected?.kind === 'link' && selected.id === link.id;
        return (
          <g key={link.id}>
            <line
              x1={from.x}
              y1={from.y}
              x2={to.x}
              y2={to.y}
              stroke={
                isSelected
                  ? '#2563eb'
                  : link.status === 'down'
                    ? '#dc2626'
                    : link.affected
                      ? severityRing(link)
                      : '#94a3b8'
              }
              strokeWidth={isSelected ? 4 : 2.5}
              strokeDasharray={link.status === 'down' ? '6 4' : undefined}
              onClick={() => onSelect({ kind: 'link', id: link.id, data: link })}
            />
            <text
              x={(from.x + to.x) / 2}
              y={(from.y + to.y) / 2 - 5}
              fontSize="9"
              fill="#64748b"
              textAnchor="middle"
            >
              {link.source_interface} ↔ {link.target_interface}
            </text>
          </g>
        );
      })}

      {/* nodes */}
      {nodes.map((node) => {
        const { x, y } = positionOf(node.id);
        const isSelected = selected?.kind === 'node' && selected.id === node.id;
        const nodeHealth = health[node.id];
        const bandColor = nodeHealth ? BAND_COLORS[nodeHealth.band] : null;
        return (
          <g
            key={node.id}
            transform={`translate(${x}, ${y})`}
            onMouseDown={() => {
              dragRef.current = node.id;
            }}
            onClick={(event) => {
              event.stopPropagation();
              onSelect({ kind: 'node', id: node.id, data: node });
            }}
            className="cursor-grab"
          >
            <circle
              r={22}
              fill={TYPE_COLORS[node.device_type] || '#64748b'}
              stroke={isSelected ? '#2563eb' : severityRing(node)}
              strokeWidth={isSelected ? 5 : 3.5}
              opacity={node.status === 'offline' ? 0.45 : 1}
            />
            <text y={4} textAnchor="middle" fontSize="12" fill="#fff">
              {node.device_type === 'firewall' ? '🛡' : node.device_type[0].toUpperCase()}
            </text>
            {nodeHealth && (
              <g transform="translate(17, -17)">
                <circle r={10} fill="#fff" stroke={bandColor} strokeWidth={1.5} />
                <text
                  y={3}
                  textAnchor="middle"
                  fontSize="8"
                  fontWeight="bold"
                  fill={bandColor}
                >
                  {Math.round(nodeHealth.score)}
                </text>
              </g>
            )}
            <text y={38} textAnchor="middle" fontSize="11" fill="#0f172a">
              {node.hostname || node.ip_address}
            </text>
            {node.affected && (
              <text y={50} textAnchor="middle" fontSize="9" fill="#dc2626">
                {node.max_severity} · {node.open_alert_count} alert(s)
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
