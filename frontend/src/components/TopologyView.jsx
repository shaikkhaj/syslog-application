
import { useEffect, useRef, useState } from 'react';

const TYPE_COLORS = {
  router: '#3b82f6',
  switch: '#14b8a6',
  firewall: '#ef4444',
  server: '#64748b',
};

const SEVERITY_RING = {
  CRITICAL: '#ef4444',
  HIGH: '#f97316',
  MEDIUM: '#f59e0b',
  LOW: '#eab308',
  INFO: '#38bdf8',
};

const BAND_COLORS = {
  critical: '#ef4444',
  degraded: '#f59e0b',
  healthy: '#10b981',
};

function severityRing(node) {
  return node.affected
    ? SEVERITY_RING[node.max_severity] || '#f97316'
    : '#475569';
}

export default function TopologyView({
  nodes,
  links,
  health = {},
  selected,
  onSelect,
}) {
  const positionsRef = useRef({});
  const dragRef = useRef(null);
  const [, forceRender] = useState(0);

  useEffect(() => {
    const count = nodes.length;

    nodes.forEach((node, index) => {
      if (!positionsRef.current[node.id]) {
        const angle =
          (2 * Math.PI * index) / Math.max(count, 1) - Math.PI / 2;

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

  const onPointerMove = (event) => {
    const drag = dragRef.current;
    if (drag === null) return;

    const svg = event.currentTarget;
    const point = svg.createSVGPoint();

    point.x = event.clientX;
    point.y = event.clientY;

    const svgPoint = point.matrixTransform(svg.getScreenCTM().inverse());

    positionsRef.current[drag] = {
      x: Math.max(30, Math.min(770, svgPoint.x)),
      y: Math.max(35, Math.min(445, svgPoint.y)),
    };

    forceRender((value) => value + 1);
  };

  const stopDragging = () => {
    dragRef.current = null;
  };

  return (
    <svg
      viewBox="0 0 800 480"
      preserveAspectRatio="xMidYMid meet"
      className="h-[520px] w-full select-none rounded-xl border border-slate-700 bg-[#111c2e]"
      onPointerMove={onPointerMove}
      onPointerUp={stopDragging}
      onPointerLeave={stopDragging}
      onPointerCancel={stopDragging}
    >
      <defs>
        <pattern
          id="topology-grid"
          width="24"
          height="24"
          patternUnits="userSpaceOnUse"
        >
          <path
            d="M 24 0 L 0 0 0 24"
            fill="none"
            stroke="#26364c"
            strokeWidth="0.7"
          />
        </pattern>

        <filter id="node-glow" x="-100%" y="-100%" width="300%" height="300%">
          <feGaussianBlur stdDeviation="5" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <rect width="800" height="480" fill="url(#topology-grid)" />

      <text
        x="20"
        y="28"
        fill="#64748b"
        fontSize="10"
        letterSpacing="1.5"
      >
        NETWORK MAP
      </text>

      {links.map((link) => {
        const from = positionOf(link.source_device_id);
        const to = positionOf(link.target_device_id);
        const isSelected =
          selected?.kind === 'link' && selected.id === link.id;

        const lineColor = isSelected
          ? '#60a5fa'
          : link.status === 'down'
            ? '#ef4444'
            : link.affected
              ? severityRing(link)
              : '#52647d';

        return (
          <g key={link.id}>
            <line
              x1={from.x}
              y1={from.y}
              x2={to.x}
              y2={to.y}
              stroke={lineColor}
              strokeWidth={isSelected ? 4 : 2.5}
              strokeDasharray={link.status === 'down' ? '7 5' : undefined}
              opacity={link.status === 'down' ? 0.95 : 0.8}
              onClick={() =>
                onSelect({ kind: 'link', id: link.id, data: link })
              }
              className="cursor-pointer"
            />

            <line
              x1={from.x}
              y1={from.y}
              x2={to.x}
              y2={to.y}
              stroke="transparent"
              strokeWidth="14"
              onClick={() =>
                onSelect({ kind: 'link', id: link.id, data: link })
              }
              className="cursor-pointer"
            />

            <text
              x={(from.x + to.x) / 2}
              y={(from.y + to.y) / 2 - 9}
              fontSize="9"
              fill="#94a3b8"
              textAnchor="middle"
              pointerEvents="none"
            >
              {link.source_interface} ↔ {link.target_interface}
            </text>

            {link.status === 'down' && (
              <circle
                cx={(from.x + to.x) / 2}
                cy={(from.y + to.y) / 2}
                r="5"
                fill="#ef4444"
                stroke="#111c2e"
                strokeWidth="2"
                pointerEvents="none"
              />
            )}
          </g>
        );
      })}

      {nodes.map((node) => {
        const { x, y } = positionOf(node.id);
        const isSelected =
          selected?.kind === 'node' && selected.id === node.id;
        const nodeHealth = health[node.id];
        const bandColor = nodeHealth
          ? BAND_COLORS[nodeHealth.band] || '#94a3b8'
          : null;

        return (
          <g
            key={node.id}
            transform={`translate(${x}, ${y})`}
            onPointerDown={(event) => {
              if (event.button !== 0) return;
              dragRef.current = node.id;
              event.currentTarget.ownerSVGElement.setPointerCapture(
                event.pointerId
              );
            }}
            onClick={(event) => {
              event.stopPropagation();
              onSelect({ kind: 'node', id: node.id, data: node });
            }}
            className="cursor-grab active:cursor-grabbing"
          >
            {isSelected && (
              <circle
                r="31"
                fill="none"
                stroke="#60a5fa"
                strokeWidth="2"
                opacity="0.8"
                filter="url(#node-glow)"
              />
            )}

            <circle
              r="23"
              fill={TYPE_COLORS[node.device_type] || '#64748b'}
              stroke={isSelected ? '#93c5fd' : severityRing(node)}
              strokeWidth={isSelected ? 4 : 3}
              opacity={node.status === 'offline' ? 0.45 : 1}
            />

            <text
              y="5"
              textAnchor="middle"
              fontSize="13"
              fontWeight="bold"
              fill="#ffffff"
              pointerEvents="none"
            >
              {node.device_type === 'firewall'
                ? 'F'
                : node.device_type?.[0]?.toUpperCase() || '?'}
            </text>

            {nodeHealth && (
              <g transform="translate(19, -19)" pointerEvents="none">
                <circle
                  r="11"
                  fill="#0f1b2d"
                  stroke={bandColor}
                  strokeWidth="2"
                />
                <text
                  y="3"
                  textAnchor="middle"
                  fontSize="8"
                  fontWeight="bold"
                  fill="#ffffff"
                >
                  {Math.round(nodeHealth.score)}
                </text>
              </g>
            )}

            <text
              y="43"
              textAnchor="middle"
              fontSize="11"
              fontWeight="600"
              fill="#e2e8f0"
              pointerEvents="none"
            >
              {node.hostname || node.ip_address}
            </text>

            <text
              y="57"
              textAnchor="middle"
              fontSize="9"
              fill="#94a3b8"
              pointerEvents="none"
            >
              {node.ip_address || node.device_type}
            </text>

            {node.affected && (
              <text
                y="70"
                textAnchor="middle"
                fontSize="9"
                fill={SEVERITY_RING[node.max_severity] || '#f97316'}
                pointerEvents="none"
              >
                {node.max_severity} · {node.open_alert_count} alert(s)
              </text>
            )}
          </g>
        );
      })}

      {nodes.length === 0 && (
        <text
          x="400"
          y="235"
          textAnchor="middle"
          fontSize="15"
          fill="#94a3b8"
        >
          No network devices added yet
        </text>
      )}

      <text
        x="780"
        y="463"
        textAnchor="end"
        fontSize="9"
        fill="#64748b"
      >
        Drag devices to rearrange
      </text>
    </svg>
  );
}
