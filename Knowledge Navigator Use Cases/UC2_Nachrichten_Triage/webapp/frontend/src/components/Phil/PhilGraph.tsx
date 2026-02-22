import { useEffect, useRef, useState } from 'react'
import type {
  SimulationNodeDatum,
  SimulationLinkDatum,
} from 'd3-force'

export interface GraphNode { id: string; label: string; type: string }
export interface GraphEdge { source: string; target: string; label: string }
export interface GraphData { nodes: GraphNode[]; edges: GraphEdge[] }

// ── Visual config ─────────────────────────────────────────────────────────────
const W = 900, H = 600

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
  const [selected, setSelected] = useState<string | null>(null)
  const tickRef = useRef(0)

  // Reset selection when data changes
  useEffect(() => { setSelected(null) }, [data])

  useEffect(() => {
    if (data.nodes.length === 0) return
    const cx = W / 2, cy = H / 2

    import('d3-force').then((d3) => {
      const nodes: SimNode[] = data.nodes.map((n) => ({
        ...n,
        x: n.id === 'center' ? cx : cx + (Math.random() - 0.5) * 260,
        y: n.id === 'center' ? cy : cy + (Math.random() - 0.5) * 260,
      }))
      const nodeById = new Map(nodes.map((n) => [n.id, n]))

      const links = data.edges
        .map((e) => {
          const s = nodeById.get(e.source), t = nodeById.get(e.target)
          if (!s || !t) return null
          return { source: s, target: t, label: e.label } as SimulationLinkDatum<SimNode> & { label: string }
        })
        .filter(Boolean) as (SimulationLinkDatum<SimNode> & { label: string })[]

      const centerNode = nodes.find((n) => n.id === 'center')
      if (centerNode) { centerNode.fx = cx; centerNode.fy = cy }

      const sim = d3
        .forceSimulation(nodes)
        .force('charge', d3.forceManyBody().strength(-300))
        .force('link', d3.forceLink(links).distance(170).strength(0.85))
        .force('center', d3.forceCenter(cx, cy).strength(0.35))
        .force('collide', d3.forceCollide(62))
        .stop()

      sim.tick(400)

      const pos: Record<string, { x: number; y: number }> = {}
      for (const n of nodes) {
        pos[n.id] = {
          x: Math.max(62, Math.min(W - 62, n.x ?? cx)),
          y: Math.max(62, Math.min(H - 62, n.y ?? cy)),
        }
      }
      tickRef.current++
      setPositions(pos)
    })
  }, [data])

  // ── Selection helpers ────────────────────────────────────────────────────────
  const connectedIds: Set<string> | null = selected
    ? new Set([
        selected,
        ...data.edges
          .filter((e) => e.source === selected || e.target === selected)
          .flatMap((e) => [e.source, e.target]),
      ])
    : null

  function nodeOpacity(id: string) {
    if (!connectedIds) return 1
    return connectedIds.has(id) ? 1 : 0.12
  }

  function edgeActive(e: GraphEdge) {
    return !selected || e.source === selected || e.target === selected
  }

  function toggleNode(id: string) {
    setSelected((prev) => (prev === id ? null : id))
  }

  // ── Edge bezier paths ────────────────────────────────────────────────────────
  const edgePaths = data.edges.map((e, i) => {
    const s = positions[e.source], t = positions[e.target]
    if (!s || !t) return null
    const dx = t.x - s.x, dy = t.y - s.y
    const len = Math.sqrt(dx * dx + dy * dy) || 1
    const bend = Math.min(50, len * 0.22)
    const mx = (s.x + t.x) / 2 - (dy / len) * bend
    const my = (s.y + t.y) / 2 + (dx / len) * bend
    return { ...e, s, t, mx, my, d: `M${s.x},${s.y} Q${mx},${my} ${t.x},${t.y}`, i }
  }).filter(Boolean) as Array<{
    source: string; target: string; label: string
    s: {x:number;y:number}; t: {x:number;y:number}
    mx: number; my: number; d: string; i: number
  }>

  const hasPositions = Object.keys(positions).length > 0

  return (
    <svg
      width="100%"
      viewBox={`0 0 ${W} ${H}`}
      style={{ display: 'block', background: 'transparent' }}
    >
      <defs>
        {Object.entries(GRADIENT_STOPS).map(([type, [dark, light]]) => (
          <radialGradient key={type} id={`grad-${type}`} cx="38%" cy="32%" r="72%">
            <stop offset="0%" stopColor={light} />
            <stop offset="100%" stopColor={dark} />
          </radialGradient>
        ))}
        {Object.entries(GRADIENT_STOPS).map(([type, [dark, light]]) => (
          <radialGradient key={`sel-${type}`} id={`grad-sel-${type}`} cx="38%" cy="32%" r="72%">
            <stop offset="0%" stopColor={light} stopOpacity="1" />
            <stop offset="100%" stopColor={dark} stopOpacity="0.85" />
          </radialGradient>
        ))}

        <filter id="glow-center" x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="6" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
        <filter id="glow-selected" x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="8" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
        <filter id="shadow-node" x="-30%" y="-30%" width="160%" height="160%">
          <feDropShadow dx="0" dy="3" stdDeviation="5" floodColor="#00000040" />
        </filter>

        <style>{`
          @keyframes gNodeIn {
            from { opacity: 0; transform: scale(0.15); }
            to   { opacity: 1; transform: scale(1); }
          }
          @keyframes gEdgeDraw {
            from { stroke-dashoffset: 500; opacity: 0; }
            to   { stroke-dashoffset: 0; opacity: 1; }
          }
          @keyframes pulse-ring {
            0%   { r: 52; opacity: .45; }
            100% { r: 70; opacity: 0; }
          }
          .g-node { animation: gNodeIn 0.5s cubic-bezier(.34,1.56,.64,1) both; }
          .g-edge-line {
            stroke-dasharray: 500;
            animation: gEdgeDraw 0.55s ease both;
          }
          .g-node-circle { transition: opacity 0.25s ease, r 0.18s ease; }
          .g-node-group { cursor: pointer; }
          .g-node-group:hover .g-node-circle { filter: brightness(1.15); }
          .g-edge-path { transition: opacity 0.25s ease, stroke-width 0.15s ease; }
          .pulse-ring { animation: pulse-ring 1.6s ease-out infinite; transform-box: fill-box; transform-origin: center; }
        `}</style>
      </defs>

      {/* ── Edges ── */}
      {hasPositions && edgePaths.map((ep) => {
        const active = edgeActive(ep)
        return (
          <g
            key={`${ep.source}-${ep.target}-${ep.i}`}
            style={{ animationDelay: `${120 + ep.i * 40}ms` }}
          >
            <path
              d={ep.d}
              fill="none"
              stroke={active && selected ? '#6366F1' : '#CBD5E1'}
              strokeWidth={active && selected ? 2.5 : 1.8}
              opacity={active ? 0.8 : 0.08}
              className="g-edge-path g-edge-line"
              style={{ animationDelay: `${120 + ep.i * 40}ms` }}
            />
            {/* Edge label — only visible when edge is active */}
            {active && (
              <>
                <rect
                  x={ep.mx - 28} y={ep.my - 10}
                  width={56} height={18}
                  rx={6}
                  fill="white"
                  stroke={selected ? '#C7D2FE' : '#E2E8F0'}
                  strokeWidth={0.8}
                  opacity={0.95}
                />
                <text
                  x={ep.mx} y={ep.my + 4}
                  textAnchor="middle"
                  fontSize={9}
                  fill={selected ? '#4338CA' : '#475569'}
                  fontFamily="inherit"
                  fontWeight={600}
                >
                  {truncate(ep.label, 14)}
                </text>
              </>
            )}
          </g>
        )
      })}

      {/* ── Nodes ── */}
      {hasPositions && data.nodes.map((node, idx) => {
        const p = positions[node.id]
        if (!p) return null
        const isCenter = node.id === 'center'
        const isSel = selected === node.id
        const op = nodeOpacity(node.id)
        const r = isCenter ? 52 : isSel ? 44 : 40
        const delay = isCenter ? 0 : 60 + idx * 50
        const gradId = isSel ? `grad-sel-${node.type}` : `grad-${node.type}`
        const fs = isCenter ? 13 : 11

        const words = node.label.split(' ')
        const half = Math.ceil(words.length / 2)
        const line1 = words.slice(0, half).join(' ')
        const line2 = words.slice(half).join(' ')

        return (
          <g
            key={node.id}
            className="g-node g-node-group"
            style={{
              transformOrigin: `${p.x}px ${p.y}px`,
              animationDelay: `${delay}ms`,
              opacity: op,
              transition: 'opacity 0.25s ease',
            }}
            onClick={() => toggleNode(node.id)}
          >
            {/* Pulse ring — always on center, also on selected non-center */}
            {(isCenter || isSel) && (
              <circle
                cx={p.x} cy={p.y}
                r={r + 10}
                fill="none"
                stroke={GRADIENT_STOPS[node.type]?.[1] ?? '#60A5FA'}
                strokeWidth={isSel ? 2.5 : 1.5}
                className={isSel ? 'pulse-ring' : undefined}
                opacity={isSel ? 0.55 : 0.2}
              />
            )}

            {/* Invisible larger hit target */}
            <circle cx={p.x} cy={p.y} r={r + 14} fill="transparent" />

            {/* Shadow ring for depth */}
            <circle
              cx={p.x} cy={p.y} r={r + 2}
              fill="none"
              stroke="rgba(0,0,0,0.12)"
              strokeWidth={4}
            />

            {/* Main circle */}
            <circle
              cx={p.x} cy={p.y} r={r}
              fill={`url(#${gradId})`}
              filter={isCenter ? 'url(#glow-center)' : isSel ? 'url(#glow-selected)' : 'url(#shadow-node)'}
              className="g-node-circle"
            />

            {/* White rim */}
            <circle
              cx={p.x} cy={p.y} r={r}
              fill="none"
              stroke="white"
              strokeWidth={isSel ? 3 : 2}
              opacity={isSel ? 0.55 : 0.2}
            />

            {/* Label */}
            {line2 ? (
              <>
                <text x={p.x} y={p.y - 7}
                  textAnchor="middle" dominantBaseline="middle"
                  fontSize={fs} fill="white"
                  fontWeight={isCenter ? 800 : 700}
                  fontFamily="inherit"
                  style={{ pointerEvents: 'none', letterSpacing: isCenter ? '-0.02em' : '0' }}
                >
                  {truncate(line1, 14)}
                </text>
                <text x={p.x} y={p.y + 9}
                  textAnchor="middle" dominantBaseline="middle"
                  fontSize={fs} fill="white"
                  fontWeight={isCenter ? 800 : 700}
                  fontFamily="inherit"
                  style={{ pointerEvents: 'none' }}
                >
                  {truncate(line2, 14)}
                </text>
              </>
            ) : (
              <text x={p.x} y={p.y}
                textAnchor="middle" dominantBaseline="middle"
                fontSize={isCenter ? 14 : fs} fill="white"
                fontWeight={isCenter ? 800 : 700}
                fontFamily="inherit"
                style={{ pointerEvents: 'none', letterSpacing: isCenter ? '-0.02em' : '0' }}
              >
                {truncate(node.label, 16)}
              </text>
            )}

            {/* Type badge */}
            {!isCenter && NODE_LABEL[node.type] && (
              <>
                <rect
                  x={p.x - 18} y={p.y + r - 8}
                  width={36} height={15}
                  rx={7}
                  fill={GRADIENT_STOPS[node.type]?.[0] ?? '#6B7280'}
                  stroke="white" strokeWidth={1.5}
                  style={{ pointerEvents: 'none' }}
                />
                <text x={p.x} y={p.y + r + 1}
                  textAnchor="middle" dominantBaseline="middle"
                  fontSize={8} fill="white"
                  fontWeight={700}
                  fontFamily="inherit"
                  letterSpacing="0.04em"
                  style={{ pointerEvents: 'none' }}
                >
                  {NODE_LABEL[node.type].toUpperCase()}
                </text>
              </>
            )}
          </g>
        )
      })}

      {/* ── Hint text when nothing selected ── */}
      {hasPositions && !selected && (
        <text
          x={W / 2} y={H - 12}
          textAnchor="middle"
          fontSize={10}
          fill="#94A3B8"
          fontFamily="inherit"
        >
          Knoten anklicken zum Hervorheben
        </text>
      )}
      {/* ── Deselect hint when selected ── */}
      {hasPositions && selected && (
        <text
          x={W / 2} y={H - 12}
          textAnchor="middle"
          fontSize={10}
          fill="#94A3B8"
          fontFamily="inherit"
        >
          Erneut klicken zum Zurücksetzen
        </text>
      )}

      {/* ── Legend ── */}
      {hasPositions && (
        <g transform={`translate(8, 14)`}>
          {Object.entries(NODE_LABEL).map(([type, label], i) => (
            <g key={type} transform={`translate(${i * 100}, 0)`}>
              <circle cx={8} cy={0} r={7} fill={`url(#grad-${type})`} />
              <text x={20} y={4} fontSize={10} fill="#6B7280" fontFamily="inherit" fontWeight={500}>
                {label}
              </text>
            </g>
          ))}
        </g>
      )}
    </svg>
  )
}
