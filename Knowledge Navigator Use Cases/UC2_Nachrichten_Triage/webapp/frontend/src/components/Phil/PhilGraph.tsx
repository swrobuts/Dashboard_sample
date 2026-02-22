import { useEffect, useRef, useState } from 'react'
import type {
  SimulationNodeDatum,
  SimulationLinkDatum,
} from 'd3-force'

export interface GraphNode { id: string; label: string; type: string }
export interface GraphEdge { source: string; target: string; label: string }
export interface GraphData { nodes: GraphNode[]; edges: GraphEdge[] }

// ── Visual config ─────────────────────────────────────────────────────────────
const W = 860, H = 580

const GRADIENT_STOPS: Record<string, [string, string]> = {
  center:       ['#0F2B5B', '#2563EB'],
  person:       ['#991B1B', '#EF4444'],
  thema:        ['#1D4ED8', '#60A5FA'],
  datum:        ['#92400E', '#F59E0B'],
  ort:          ['#065F46', '#10B981'],
  aktion:       ['#5B21B6', '#A78BFA'],
  organisation: ['#155E75', '#22D3EE'],
}

const NODE_LABEL: Record<string, string> = {
  person: 'Person', thema: 'Thema', datum: 'Datum',
  ort: 'Ort', aktion: 'Aktion', organisation: 'Org.',
}

// ── D3 force types ────────────────────────────────────────────────────────────
interface SimNode extends SimulationNodeDatum, GraphNode {
  x: number; y: number
  fx?: number | null; fy?: number | null
}

function truncate(s: string, n: number) { return s.length > n ? s.slice(0, n - 1) + '…' : s }

// ── Component ─────────────────────────────────────────────────────────────────
interface Props { data: GraphData }

export function PhilGraph({ data }: Props) {
  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>({})
  const tickRef = useRef(0)

  useEffect(() => {
    if (data.nodes.length === 0) return

    const cx = W / 2, cy = H / 2

    import('d3-force').then((d3) => {
      const nodes: SimNode[] = data.nodes.map((n) => ({
        ...n,
        x: n.id === 'center' ? cx : cx + (Math.random() - 0.5) * 200,
        y: n.id === 'center' ? cy : cy + (Math.random() - 0.5) * 200,
      }))
      const nodeById = new Map(nodes.map((n) => [n.id, n]))

      const links = data.edges
        .map((e) => {
          const s = nodeById.get(e.source), t = nodeById.get(e.target)
          if (!s || !t) return null
          return { source: s, target: t, label: e.label } as SimulationLinkDatum<SimNode> & { label: string }
        })
        .filter(Boolean) as (SimulationLinkDatum<SimNode> & { label: string })[]

      // Pin center node
      const centerNode = nodes.find((n) => n.id === 'center')
      if (centerNode) { centerNode.fx = cx; centerNode.fy = cy }

      const sim = d3
        .forceSimulation(nodes)
        .force('charge', d3.forceManyBody().strength(-220))
        .force('link', d3.forceLink(links).distance(140).strength(0.9))
        .force('center', d3.forceCenter(cx, cy).strength(0.4))
        .force('collide', d3.forceCollide(52))
        .stop()

      // Converge
      sim.tick(350)

      const pos: Record<string, { x: number; y: number }> = {}
      for (const n of nodes) {
        pos[n.id] = {
          x: Math.max(55, Math.min(W - 55, n.x ?? cx)),
          y: Math.max(55, Math.min(H - 55, n.y ?? cy)),
        }
      }
      tickRef.current++
      setPositions(pos)
    })
  }, [data])

  // Build bezier edge paths
  const edgePaths = data.edges.map((e, i) => {
    const s = positions[e.source], t = positions[e.target]
    if (!s || !t) return null
    // Perpendicular offset for curve
    const dx = t.x - s.x, dy = t.y - s.y
    const len = Math.sqrt(dx * dx + dy * dy) || 1
    const bend = Math.min(40, len * 0.2)
    const mx = (s.x + t.x) / 2 - (dy / len) * bend
    const my = (s.y + t.y) / 2 + (dx / len) * bend
    return { ...e, s, t, mx, my, d: `M${s.x},${s.y} Q${mx},${my} ${t.x},${t.y}`, i }
  }).filter(Boolean) as Array<{ source: string; target: string; label: string; s: {x:number;y:number}; t: {x:number;y:number}; mx: number; my: number; d: string; i: number }>

  const hasPositions = Object.keys(positions).length > 0

  return (
    <svg
      width="100%"
      viewBox={`0 0 ${W} ${H}`}
      style={{ display: 'block', background: 'transparent' }}
    >
      <defs>
        {/* Per-type radial gradients */}
        {Object.entries(GRADIENT_STOPS).map(([type, [dark, light]]) => (
          <radialGradient key={type} id={`grad-${type}`} cx="38%" cy="32%" r="72%">
            <stop offset="0%" stopColor={light} />
            <stop offset="100%" stopColor={dark} />
          </radialGradient>
        ))}

        {/* Subtle glow for center node */}
        <filter id="glow-center" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="5" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>

        {/* Drop shadow for peripheral nodes */}
        <filter id="shadow-node" x="-30%" y="-30%" width="160%" height="160%">
          <feDropShadow dx="0" dy="2" stdDeviation="4" floodColor="#00000038" />
        </filter>

        {/* Edge label pill bg: use white with slight blur */}
        <filter id="pill-bg" x="-10%" y="-20%" width="120%" height="140%">
          <feFlood floodColor="white" floodOpacity="0.95" result="bg"/>
          <feComposite in="bg" in2="SourceGraphic" operator="in" result="bg2"/>
          <feMerge><feMergeNode in="bg2"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>

        <style>{`
          @keyframes gNodeIn {
            from { opacity: 0; transform: scale(0.2); }
            to   { opacity: 1; transform: scale(1); }
          }
          @keyframes gEdgeIn {
            from { opacity: 0; }
            to   { opacity: 1; }
          }
          @keyframes gEdgeDraw {
            from { stroke-dashoffset: 400; }
            to   { stroke-dashoffset: 0; }
          }
          .g-node {
            animation: gNodeIn 0.55s cubic-bezier(.34,1.56,.64,1) both;
          }
          .g-edge {
            animation: gEdgeIn 0.45s ease both;
          }
          .g-edge-line {
            stroke-dasharray: 400;
            animation: gEdgeDraw 0.6s ease both;
          }
        `}</style>
      </defs>

      {/* ── Edges ── */}
      {hasPositions && edgePaths.map((ep) => (
        <g
          key={`${ep.source}-${ep.target}-${ep.i}`}
          className="g-edge"
          style={{ animationDelay: `${150 + ep.i * 45}ms` }}
        >
          <path
            d={ep.d}
            fill="none"
            stroke="#CBD5E1"
            strokeWidth={1.8}
            opacity={0.65}
            className="g-edge-line"
            style={{ animationDelay: `${150 + ep.i * 45}ms` }}
          />
          {/* Edge label pill */}
          <rect
            x={ep.mx - 26} y={ep.my - 9}
            width={52} height={16}
            rx={5}
            fill="white"
            stroke="#E2E8F0"
            strokeWidth={0.8}
            opacity={0.92}
          />
          <text
            x={ep.mx} y={ep.my + 4}
            textAnchor="middle"
            fontSize={8.5}
            fill="#475569"
            fontFamily="inherit"
            fontWeight={500}
          >
            {truncate(ep.label, 16)}
          </text>
        </g>
      ))}

      {/* ── Nodes ── */}
      {hasPositions && data.nodes.map((node, idx) => {
        const p = positions[node.id]
        if (!p) return null
        const isCenter = node.id === 'center'
        const r = isCenter ? 48 : 36
        const delay = isCenter ? 0 : 80 + idx * 55
        const gradId = `grad-${node.type}`

        const words = node.label.split(' ')
        const half = Math.ceil(words.length / 2)
        const line1 = words.slice(0, half).join(' ')
        const line2 = words.slice(half).join(' ')
        const fs = isCenter ? 12 : 10.5

        return (
          <g
            key={node.id}
            className="g-node"
            style={{
              transformOrigin: `${p.x}px ${p.y}px`,
              animationDelay: `${delay}ms`,
              cursor: 'default',
            }}
          >
            {/* Outer pulse ring for center */}
            {isCenter && (
              <circle
                cx={p.x} cy={p.y} r={r + 10}
                fill="none"
                stroke={GRADIENT_STOPS.center[1]}
                strokeWidth={1.5}
                opacity={0.2}
              />
            )}

            {/* Main circle */}
            <circle
              cx={p.x} cy={p.y} r={r}
              fill={`url(#${gradId})`}
              filter={isCenter ? 'url(#glow-center)' : 'url(#shadow-node)'}
            />

            {/* White inner rim */}
            <circle
              cx={p.x} cy={p.y} r={r}
              fill="none"
              stroke="white"
              strokeWidth={2}
              opacity={0.22}
            />

            {/* Label text — wrap to two lines if needed */}
            {line2 ? (
              <>
                <text
                  x={p.x} y={p.y - 6}
                  textAnchor="middle" dominantBaseline="middle"
                  fontSize={fs} fill="white"
                  fontWeight={isCenter ? 800 : 700}
                  fontFamily="inherit"
                  letterSpacing={isCenter ? '-0.02em' : '0'}
                >
                  {truncate(line1, 13)}
                </text>
                <text
                  x={p.x} y={p.y + 8}
                  textAnchor="middle" dominantBaseline="middle"
                  fontSize={fs} fill="white"
                  fontWeight={isCenter ? 800 : 700}
                  fontFamily="inherit"
                >
                  {truncate(line2, 13)}
                </text>
              </>
            ) : (
              <text
                x={p.x} y={p.y}
                textAnchor="middle" dominantBaseline="middle"
                fontSize={isCenter ? 13 : fs} fill="white"
                fontWeight={isCenter ? 800 : 700}
                fontFamily="inherit"
                letterSpacing={isCenter ? '-0.02em' : '0'}
              >
                {truncate(node.label, 15)}
              </text>
            )}

            {/* Type badge for non-center nodes */}
            {!isCenter && NODE_LABEL[node.type] && (
              <>
                <rect
                  x={p.x - 16} y={p.y + r - 7}
                  width={32} height={13}
                  rx={6}
                  fill={GRADIENT_STOPS[node.type]?.[0] ?? '#6B7280'}
                  stroke="white" strokeWidth={1.2}
                />
                <text
                  x={p.x} y={p.y + r}
                  textAnchor="middle" dominantBaseline="middle"
                  fontSize={7.5} fill="white"
                  fontWeight={700}
                  fontFamily="inherit"
                  letterSpacing="0.03em"
                >
                  {NODE_LABEL[node.type].toUpperCase()}
                </text>
              </>
            )}
          </g>
        )
      })}

      {/* ── Legend ── */}
      {hasPositions && (
        <g transform={`translate(8, ${H - 18})`}>
          {Object.entries(NODE_LABEL).map(([type, label], i) => (
            <g key={type} transform={`translate(${i * 90}, 0)`}>
              <circle cx={7} cy={0} r={6} fill={`url(#grad-${type})`} />
              <text x={17} y={4} fontSize={9.5} fill="#6B7280" fontFamily="inherit" fontWeight={500}>
                {label}
              </text>
            </g>
          ))}
        </g>
      )}
    </svg>
  )
}
