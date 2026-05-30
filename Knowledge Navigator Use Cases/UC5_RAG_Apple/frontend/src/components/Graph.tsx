import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D, { type ForceGraphMethods } from "react-force-graph-2d";
import {
  api, type GraphCommunity, type GraphEdge, type GraphNode, type GraphPayload,
} from "../api";

// ─── Restrained palette ────────────────────────────────────────────────────
// Inspired by Aicher's systematic categorical coding and Tufte's
// "use colour to encode information, not to decorate". Each type gets a
// distinct but desaturated tone that reads cleanly on warm paper.
const TYPE_COLORS: Record<string, string> = {
  PERSON:       "#1f1f1f", // ink
  ORGANIZATION: "#8c4a3c", // brick
  PRODUCT:      "#2c4a6b", // ink-navy
  EVENT:        "#8a6a3a", // umber
  LOCATION:     "#4a6b3a", // olive
  CONCEPT:      "#5a4a6b", // dust-purple
};
const ACCENT      = "#c8503c"; // Munich-1972 warm red — used only for state
const TEXT_INK    = "#111111";
const TEXT_MUTED  = "#6b6b6b";
const RULE        = "#d8d4cf"; // hairline rule colour
const PAPER       = "#f7f5ef";
const PAPER_SOFT  = "#efebe2";

const DEFAULT_COLOR = "#9c9c9c";
const TYPE_OPTIONS = ["PERSON", "ORGANIZATION", "PRODUCT", "EVENT", "LOCATION", "CONCEPT"];

interface FGNode extends GraphNode {
  x?: number; y?: number;
  fx?: number | null; fy?: number | null;
  __radius?: number;
}

interface FGLink extends GraphEdge {
  source: string | FGNode;
  target: string | FGNode;
}

type ColourBy = "type" | "community";
type Layout   = "cluster" | "concentric";

// Ring order for concentric layout — closest to Apple = most directly
// related types (persons running the company, then orgs, then products
// they make, then events shaping the firm, then peripheral location/
// concept references on the outer rings).
const RING_ORDER = ["PERSON", "ORGANIZATION", "PRODUCT", "EVENT", "LOCATION", "CONCEPT"];

// ─── Geometry helpers (no extra deps) ──────────────────────────────────────

/** Graham-scan convex hull, returns the boundary points in order.
 *  Input: array of [x, y]; output: subset of those points forming the hull.
 *  Returns at most the input (fewer when many points are collinear). */
function convexHull(points: [number, number][]): [number, number][] {
  if (points.length < 3) return points.slice();
  const sorted = [...points].sort((a, b) => a[0] === b[0] ? a[1] - b[1] : a[0] - b[0]);
  const cross = (o: [number, number], a: [number, number], b: [number, number]) =>
    (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower: [number, number][] = [];
  for (const p of sorted) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop();
    lower.push(p);
  }
  const upper: [number, number][] = [];
  for (let i = sorted.length - 1; i >= 0; i--) {
    const p = sorted[i];
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop();
    upper.push(p);
  }
  lower.pop(); upper.pop();
  return lower.concat(upper);
}

/** BFS shortest path on the link list (unweighted, undirected).
 *  Returns ids in order from→to, or [] if unreachable / same. */
function shortestPath(nodes: FGNode[], links: FGLink[], from: string, to: string): string[] {
  if (from === to) return [from];
  const idOf = (x: string | FGNode) => typeof x === "string" ? x : x.id;
  const adj = new Map<string, Set<string>>();
  for (const n of nodes) adj.set(n.id, new Set());
  for (const l of links) {
    const a = idOf(l.source), b = idOf(l.target);
    adj.get(a)?.add(b); adj.get(b)?.add(a);
  }
  const prev = new Map<string, string>();
  const seen = new Set<string>([from]);
  const queue = [from];
  while (queue.length) {
    const cur = queue.shift()!;
    if (cur === to) {
      const path = [to];
      let p = to;
      while (prev.has(p)) { p = prev.get(p)!; path.push(p); }
      return path.reverse();
    }
    for (const nb of adj.get(cur) || []) {
      if (seen.has(nb)) continue;
      seen.add(nb); prev.set(nb, cur); queue.push(nb);
    }
  }
  return [];
}

/** Find the entity considered the "centre of the graph" — Apple Inc.
 *  Falls back to the most-mentioned ORGANIZATION if no exact match. */
function findCentreNode(nodes: FGNode[]): FGNode | null {
  const exact = nodes.find(n => /^Apple($| Inc)/i.test(n.name));
  if (exact) return exact;
  const orgs = nodes.filter(n => n.type === "ORGANIZATION");
  if (!orgs.length) return null;
  return orgs.reduce((best, n) => n.mentions > best.mentions ? n : best, orgs[0]);
}

/** Humanise an UPPER_SNAKE relation type for display.
 *  "DESIGNED_BY" → "designed by", "associatedWith" → "associated with". */
function prettifyRelation(t: string): string {
  if (!t) return "verbunden mit";
  // Split camelCase into words first, then handle UPPER_SNAKE.
  const spaced = t
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/_/g, " ")
    .toLowerCase()
    .trim();
  return spaced || "verbunden mit";
}

/** Group all neighbours of `node` by the relation type on the edge,
 *  preserving direction (selected→other = "out", other→selected = "in").
 *  Each group is sorted by weight desc, then by neighbour mentions. */
interface ConnectionGroup {
  relType: string;
  direction: "out" | "in";
  entries: { node: GraphNode; weight: number }[];
}
function buildConnections(
  node: GraphNode | null,
  allNodes: GraphNode[],
  edges: GraphEdge[],
): ConnectionGroup[] {
  if (!node) return [];
  const byId = new Map(allNodes.map(n => [n.id, n]));
  const groups = new Map<string, ConnectionGroup>();
  for (const e of edges) {
    let other: GraphNode | undefined;
    let dir: "out" | "in" | null = null;
    if (e.source === node.id) { other = byId.get(e.target); dir = "out"; }
    else if (e.target === node.id) { other = byId.get(e.source); dir = "in"; }
    if (!other || !dir) continue;
    const key = `${e.type}::${dir}`;
    if (!groups.has(key)) groups.set(key, { relType: e.type, direction: dir, entries: [] });
    groups.get(key)!.entries.push({ node: other, weight: e.weight });
  }
  for (const g of groups.values()) {
    g.entries.sort((a, b) =>
      b.weight - a.weight || b.node.mentions - a.node.mentions
    );
  }
  // Order groups: outgoing first (you "act on"), then incoming, then by
  // number of entries desc so the most-populated relation is on top.
  return Array.from(groups.values()).sort((a, b) => {
    if (a.direction !== b.direction) return a.direction === "out" ? -1 : 1;
    return b.entries.length - a.entries.length;
  });
}

export function Graph() {
  const [data, setData] = useState<GraphPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<FGNode | null>(null);
  const [hovered, setHovered] = useState<FGNode | null>(null);
  const [minMentions, setMinMentions] = useState(1);
  const [search, setSearch] = useState("");
  const [typesEnabled, setTypesEnabled] = useState<Set<string>>(new Set(TYPE_OPTIONS));
  const [colourBy, setColourBy] = useState<ColourBy>("type");
  const [layout, setLayout] = useState<Layout>("cluster");
  const [showHulls, setShowHulls] = useState(true);
  const [pathMode, setPathMode] = useState(false);
  const [pathFrom, setPathFrom] = useState<FGNode | null>(null);
  const [pathIds, setPathIds] = useState<string[]>([]);
  const [highlightedIds, setHighlightedIds] = useState<Set<string>>(new Set());
  const [sparqlOpen, setSparqlOpen] = useState(true);
  // Navigation history (breadcrumb) — last few selected entities, so the
  // user can wander Wikipedia-style through the graph and step back.
  const [history, setHistory] = useState<FGNode[]>([]);
  // Focus mode: hide everything except the 1-hop ego network of `selected`.
  const [focusMode, setFocusMode] = useState(false);
  const graphRef = useRef<ForceGraphMethods<FGNode, FGLink> | undefined>(undefined);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ w: 800, h: 600 });

  const load = async () => {
    setLoading(true); setError(null);
    try {
      const types = TYPE_OPTIONS.every(t => typesEnabled.has(t))
        ? undefined : Array.from(typesEnabled).join(",");
      const r = await api.graph({ min_mentions: minMentions, types, limit_entities: 500 });
      setData(r);
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver(([entry]) => {
      setSize({ w: entry.contentRect.width, h: entry.contentRect.height });
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  const graphData = useMemo(() => {
    if (!data) return { nodes: [] as FGNode[], links: [] as FGLink[] };
    const q = search.trim().toLowerCase();
    let keep = new Set(data.nodes.map(n => n.id));
    if (q) {
      const matches = new Set(
        data.nodes.filter(n =>
          n.name.toLowerCase().includes(q) ||
          n.description.toLowerCase().includes(q)
        ).map(n => n.id)
      );
      const neighbours = new Set<string>();
      for (const e of data.edges) {
        if (matches.has(e.source)) neighbours.add(e.target);
        if (matches.has(e.target)) neighbours.add(e.source);
      }
      keep = new Set([...matches, ...neighbours]);
    }
    const nodes = data.nodes.filter(n => keep.has(n.id)).map(n => ({ ...n })) as FGNode[];
    const ids = new Set(nodes.map(n => n.id));
    const links: FGLink[] = data.edges
      .filter(e => ids.has(e.source) && ids.has(e.target))
      .map(e => ({ ...e }));

    // ─── Concentric layout: pin nodes to type-stratified rings ──────────
    //
    // Aicher-grade radial composition: Apple at the centre, then rings by
    // type. Within each ring, sort by mentions (most-mentioned at 12
    // o'clock, rotating clockwise) so the eye lands on important nodes
    // immediately. fx/fy are honoured by d3-force as fixed positions.
    if (layout === "concentric") {
      const centre = findCentreNode(nodes);
      const ringRadius = Math.max(120, Math.min(size.w, size.h) * 0.08);
      const types = RING_ORDER.filter(t => nodes.some(n => n.type === t && n !== centre));
      const radiusFor = (typeIdx: number) => ringRadius + typeIdx * ringRadius * 0.85;
      for (const n of nodes) {
        if (n === centre) {
          n.fx = 0; n.fy = 0;
          continue;
        }
        const typeIdx = types.indexOf(n.type);
        if (typeIdx < 0) { n.fx = null; n.fy = null; continue; }
        const peers = nodes
          .filter(m => m.type === n.type && m !== centre)
          .sort((a, b) => b.mentions - a.mentions);
        const peerIdx = peers.indexOf(n);
        const r = radiusFor(typeIdx);
        const theta = -Math.PI / 2 + (peerIdx / peers.length) * Math.PI * 2;
        n.fx = r * Math.cos(theta);
        n.fy = r * Math.sin(theta);
      }
    } else {
      // Cluster mode — release pinning so the force simulation runs.
      for (const n of nodes) { n.fx = null; n.fy = null; }
    }

    return { nodes, links };
  }, [data, search, layout, size.w, size.h]);

  // ─── Cluster force: in cluster mode, pull each node toward its
  // community's centroid. Without this, d3-force produces the classic
  // "hairball"; with it, communities visibly separate into islands.
  // We compute centroids on every tick from current node positions.
  useEffect(() => {
    if (!graphRef.current) return;
    const charge = graphRef.current.d3Force("charge") as any;
    if (charge && typeof charge.strength === "function") {
      charge.strength(layout === "concentric" ? 0 : -90);
    }
    const link = graphRef.current.d3Force("link") as any;
    if (link && typeof link.distance === "function") {
      link.distance(layout === "concentric" ? 1 : 36);
    }
    if (layout === "concentric") {
      graphRef.current.d3Force("cluster", null as any);
    } else {
      const clusterForce = (alpha: number) => {
        if (!data) return;
        const buckets = new Map<string, { x: number; y: number; n: number }>();
        for (const n of graphData.nodes) {
          if (!n.community_id || n.x == null || n.y == null) continue;
          const b = buckets.get(n.community_id) || { x: 0, y: 0, n: 0 };
          b.x += n.x; b.y += n.y; b.n += 1;
          buckets.set(n.community_id, b);
        }
        for (const [, b] of buckets) { b.x /= b.n; b.y /= b.n; }
        const k = 0.6 * alpha;
        for (const n of graphData.nodes) {
          if (!n.community_id || n.x == null || n.y == null) continue;
          const c = buckets.get(n.community_id);
          if (!c) continue;
          (n as any).vx = ((n as any).vx || 0) + (c.x - n.x) * k;
          (n as any).vy = ((n as any).vy || 0) + (c.y - n.y) * k;
        }
      };
      graphRef.current.d3Force("cluster", clusterForce as any);
    }
    graphRef.current.d3ReheatSimulation();
  }, [layout, graphData.nodes, data]);

  // Communities → restrained categorical palette (still desaturated)
  const communityColour = useMemo(() => {
    const palette = [
      "#5a4a6b", "#8c4a3c", "#2c4a6b", "#4a6b3a", "#8a6a3a", "#6b4a5a",
      "#4a5a6b", "#6b5a4a", "#3a6b5a", "#6b3a5a", "#5a6b3a", "#3a4a6b",
      "#7c4f3c", "#3c5a7c", "#6b5a3a", "#5a3a4a", "#3a6b6b", "#4a3a6b",
    ];
    const m = new Map<string, string>();
    let i = 0;
    for (const c of data?.communities || []) {
      m.set(c.id, palette[i % palette.length]); i++;
    }
    return m;
  }, [data]);

  const colourOf = (n: FGNode): string => {
    if (colourBy === "community")
      return n.community_id ? (communityColour.get(n.community_id) || DEFAULT_COLOR) : DEFAULT_COLOR;
    return TYPE_COLORS[n.type] || DEFAULT_COLOR;
  };

  // 1-hop neighbour set of a given node (used for hover-dim and selection-
  // spotlight). Returns null if no node is given.
  const computeNeighbours = (n: GraphNode | null): Set<string> | null => {
    if (!n || !data) return null;
    const ids = new Set<string>([n.id]);
    for (const e of data.edges) {
      if (e.source === n.id) ids.add(e.target);
      if (e.target === n.id) ids.add(e.source);
    }
    return ids;
  };
  const neighbourIds   = useMemo(() => computeNeighbours(hovered),  [hovered, data]);
  const selectedEgoIds = useMemo(() => computeNeighbours(selected), [selected, data]);

  // Connections grouped by relation type (incoming/outgoing) for the
  // selected entity — feeds the Connection Panel.
  const connections = useMemo<ConnectionGroup[]>(() => {
    if (!selected || !data) return [];
    return buildConnections(selected, data.nodes, data.edges);
  }, [selected, data]);

  const isDimmed = (id: string) => {
    if (highlightedIds.size > 0) return !highlightedIds.has(id);
    if (focusMode && selectedEgoIds) return !selectedEgoIds.has(id);
    if (neighbourIds != null) return !neighbourIds.has(id);
    if (selectedEgoIds != null) return !selectedEgoIds.has(id);
    return false;
  };

  // Wander to another entity (clicking in the Connection Panel calls this).
  // Pushes the previous selection onto history so the user can go back.
  const navigateTo = (id: string) => {
    if (!data) return;
    const target = data.nodes.find(n => n.id === id) as FGNode | undefined;
    if (!target) return;
    if (selected && selected.id !== target.id) {
      setHistory(h => [...h.slice(-9), selected]);
    }
    setSelected(target);
    // Try to fly to the existing live node (in graphData with x/y) — if
    // present. data.nodes lacks live coordinates.
    const live = graphData.nodes.find(n => n.id === id);
    if (live && live.x != null && live.y != null && graphRef.current) {
      graphRef.current.centerAt(live.x, live.y, 700);
      graphRef.current.zoom(Math.max(graphRef.current.zoom(), 2.0), 700);
    }
  };
  const goBack = () => {
    setHistory(h => {
      if (h.length === 0) return h;
      const prev = h[h.length - 1];
      setSelected(prev);
      const live = graphData.nodes.find(n => n.id === prev.id);
      if (live && live.x != null && live.y != null && graphRef.current) {
        graphRef.current.centerAt(live.x, live.y, 600);
      }
      return h.slice(0, -1);
    });
  };

  const toggleType = (t: string) => {
    setTypesEnabled(cur => {
      const next = new Set(cur);
      if (next.has(t)) next.delete(t); else next.add(t);
      return next;
    });
  };

  const handleSparqlExecuted = (matched: string[]) => {
    setHighlightedIds(new Set(matched));
    if (matched.length > 0 && graphRef.current && data) {
      const n = graphData.nodes.find(nn => nn.id === matched[0]);
      if (n && n.x != null && n.y != null) {
        graphRef.current.centerAt(n.x, n.y, 800);
        graphRef.current.zoom(2.0, 800);
      }
    }
  };

  // Fly camera to the top fuzzy-match when the search field changes.
  useEffect(() => {
    if (!search.trim() || !graphRef.current) return;
    const q = search.trim().toLowerCase();
    const match = graphData.nodes
      .filter(n => n.name.toLowerCase().includes(q))
      .sort((a, b) => {
        // Prefer label-startsWith, then by mentions
        const sa = a.name.toLowerCase().startsWith(q) ? 0 : 1;
        const sb = b.name.toLowerCase().startsWith(q) ? 0 : 1;
        return sa - sb || b.mentions - a.mentions;
      })[0];
    if (match && match.x != null && match.y != null) {
      graphRef.current.centerAt(match.x, match.y, 700);
      graphRef.current.zoom(2.4, 700);
    }
  }, [search, graphData.nodes]);

  const handleNodeClick = (n: FGNode) => {
    if (pathMode) {
      if (!pathFrom) {
        setPathFrom(n); setPathIds([n.id]); setSelected(n);
        return;
      }
      const path = shortestPath(graphData.nodes, graphData.links, pathFrom.id, n.id);
      if (path.length > 0) {
        setPathIds(path);
        // Frame the path: fit the bbox of pathway nodes
        const pts = path
          .map(id => graphData.nodes.find(nn => nn.id === id))
          .filter((nn): nn is FGNode => !!nn && nn.x != null && nn.y != null);
        if (pts.length > 0 && graphRef.current) {
          const xs = pts.map(p => p.x!), ys = pts.map(p => p.y!);
          const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
          const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
          graphRef.current.centerAt(cx, cy, 800);
        }
      } else {
        setPathIds([pathFrom.id, n.id]); // unreachable visualised as endpoints only
      }
      setPathFrom(null);
      setSelected(n);
      return;
    }
    if (selected && selected.id !== n.id) setHistory(h => [...h.slice(-9), selected]);
    setSelected(n);
    if (n.x != null && n.y != null) graphRef.current?.centerAt(n.x, n.y, 500);
  };

  const pathIdSet = useMemo(() => new Set(pathIds), [pathIds]);

  // Top 15 mentions get their label drawn always — Tufte: don't hide
  // important data points behind hover.
  const alwaysLabeled = useMemo(() => {
    const sorted = [...graphData.nodes].sort((a, b) => b.mentions - a.mentions);
    return new Set(sorted.slice(0, 15).map(n => n.id));
  }, [graphData.nodes]);

  return (
    <div className="flex-1 flex min-h-0 overflow-hidden"
         style={{ background: PAPER, color: TEXT_INK,
                  fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, sans-serif" }}>
      {/* Left rail */}
      <LeftRail
        data={data}
        graphData={graphData}
        loading={loading}
        error={error}
        minMentions={minMentions}
        setMinMentions={setMinMentions}
        typesEnabled={typesEnabled}
        toggleType={toggleType}
        colourBy={colourBy}
        setColourBy={setColourBy}
        layout={layout}
        setLayout={setLayout}
        showHulls={showHulls}
        setShowHulls={setShowHulls}
        pathMode={pathMode}
        setPathMode={(v) => { setPathMode(v); if (!v) { setPathFrom(null); setPathIds([]); } }}
        pathFrom={pathFrom}
        pathIds={pathIds}
        clearPath={() => { setPathFrom(null); setPathIds([]); }}
        load={load}
        selected={selected}
        communityById={Object.fromEntries((data?.communities || []).map(c => [c.id, c]))}
        colourOf={colourOf}
        connections={connections}
        navigateTo={navigateTo}
        history={history}
        goBack={goBack}
        focusMode={focusMode}
        setFocusMode={setFocusMode}
      />

      {/* Canvas */}
      <main ref={containerRef} className="flex-1 relative" style={{ background: PAPER }}>
        {/* Search rule, top */}
        <div className="absolute top-0 left-0 right-0 z-10 px-6 py-3 flex items-center gap-4"
             style={{ borderBottom: `1px solid ${RULE}`, background: PAPER }}>
          <label className="text-[10px] uppercase tracking-[0.2em]" style={{ color: TEXT_MUTED }}>
            Suche
          </label>
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Name oder Beschreibung"
            className="flex-1 max-w-md bg-transparent text-sm focus:outline-none"
            style={{ borderBottom: `1px solid ${RULE}`, color: TEXT_INK, paddingBottom: "2px" }}
            onFocus={e => e.target.style.borderBottomColor = ACCENT}
            onBlur={e => e.target.style.borderBottomColor = RULE}
          />
          {highlightedIds.size > 0 && (
            <button
              onClick={() => setHighlightedIds(new Set())}
              className="text-[11px] uppercase tracking-wider hover:opacity-70 transition"
              style={{ color: ACCENT }}
            >
              SPARQL-Auswahl auflösen ({highlightedIds.size})
            </button>
          )}
          <div className="text-[11px]" style={{ color: TEXT_MUTED }}>
            {graphData.nodes.length}/{data?.nodes.length ?? 0} Entitäten
            <span className="mx-2" style={{ color: RULE }}>·</span>
            {graphData.links.length} Relationen
          </div>
        </div>

        {/* Inline legend, bottom-left — Tufte-style with type counts */}
        <div className="absolute bottom-4 left-6 z-10 text-[11px]" style={{ color: TEXT_MUTED }}>
          <div className="uppercase tracking-[0.2em] mb-2" style={{ color: TEXT_INK, fontSize: "10px" }}>Legende</div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1">
            {TYPE_OPTIONS.map(t => {
              const count = (data?.nodes || []).filter(n => n.type === t).length;
              return (
                <div key={t} className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full" style={{ background: TYPE_COLORS[t] }} />
                  <span style={{ color: TEXT_INK }}>{t}</span>
                  <span className="font-mono" style={{ color: TEXT_MUTED }}>{count}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Zoom — three plain buttons, no decoration */}
        <div className="absolute bottom-4 right-6 z-10 flex items-center gap-3 text-[11px] uppercase tracking-wider"
             style={{ color: TEXT_MUTED }}>
          <button onClick={() => graphRef.current?.zoom(graphRef.current.zoom() * 1.4, 300)}
                  className="hover:opacity-100 transition" style={{ opacity: 0.7 }}>Heran</button>
          <span style={{ color: RULE }}>·</span>
          <button onClick={() => graphRef.current?.zoom(graphRef.current.zoom() * 0.7, 300)}
                  className="hover:opacity-100 transition" style={{ opacity: 0.7 }}>Weg</button>
          <span style={{ color: RULE }}>·</span>
          <button onClick={() => graphRef.current?.zoomToFit(600, 80)}
                  className="hover:opacity-100 transition" style={{ opacity: 0.7 }}>Anpassen</button>
        </div>

        {/* The graph */}
        <div className="absolute inset-0" style={{ paddingTop: "44px" }}>
          <ForceGraph2D<FGNode, FGLink>
            ref={graphRef}
            width={size.w}
            height={size.h - 44}
            backgroundColor={PAPER}
            graphData={graphData}
            nodeId="id"
            nodeRelSize={1}
            d3AlphaDecay={layout === "concentric" ? 0.06 : 0.018}
            d3VelocityDecay={layout === "concentric" ? 0.5 : 0.28}
            cooldownTicks={layout === "concentric" ? 60 : 500}
            warmupTicks={layout === "concentric" ? 0 : 80}
            enableNodeDrag={layout === "cluster"}
            enableZoomInteraction
            onNodeHover={(n) => setHovered(n)}
            onNodeClick={(n) => handleNodeClick(n as FGNode)}
            onBackgroundClick={() => {
              setSelected(null);
              if (pathMode) { setPathFrom(null); setPathIds([]); }
            }}
            onEngineStop={() => {
              // Frame the graph nicely after the first layout settles
              if (!graphRef.current) return;
              graphRef.current.zoomToFit(600, 60);
            }}

            // ─── Hulls (cluster mode only): one soft convex polygon per
            // community, drawn UNDER nodes and edges so structure reads at
            // a glance without colour overload. Updated every frame to
            // follow the simulation. ─────────────────────────────────────
            onRenderFramePre={(ctx, scale) => {
              if (layout !== "cluster" || !showHulls) return;
              const groups = new Map<string, [number, number][]>();
              for (const n of graphData.nodes) {
                if (!n.community_id || n.x == null || n.y == null) continue;
                if (!groups.has(n.community_id)) groups.set(n.community_id, []);
                groups.get(n.community_id)!.push([n.x, n.y]);
              }
              for (const [cid, pts] of groups) {
                if (pts.length < 3) continue;
                const hull = convexHull(pts);
                if (hull.length < 3) continue;
                const colour = communityColour.get(cid) || DEFAULT_COLOR;
                // Expand the hull outward a bit for breathing room.
                const cx = hull.reduce((s, p) => s + p[0], 0) / hull.length;
                const cy = hull.reduce((s, p) => s + p[1], 0) / hull.length;
                const pad = 14 / scale;
                ctx.beginPath();
                hull.forEach((p, i) => {
                  const dx = p[0] - cx, dy = p[1] - cy;
                  const len = Math.hypot(dx, dy) || 1;
                  const x = p[0] + dx / len * pad, y = p[1] + dy / len * pad;
                  if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
                });
                ctx.closePath();
                ctx.fillStyle   = colour + "0d";   // ~5% alpha
                ctx.strokeStyle = colour + "55";   // ~33% alpha hairline
                ctx.lineWidth   = 0.6 / scale;
                ctx.fill();
                ctx.stroke();
              }
            }}

            // Restrained node rendering: filled disk sized by mentions,
            // accent ring only for hover/selection/SPARQL-highlight/path.
            nodeCanvasObjectMode={() => "replace"}
            nodeCanvasObject={(n, ctx, scale) => {
              const colour = colourOf(n);
              // Bigger base so they read on a busy canvas — addresses
              // "optisch zu klein". sqrt scaling keeps top nodes legible
              // without crushing the long tail.
              const baseR = 3.2 + Math.sqrt(n.mentions + 1) * 2.1;
              const isHovered = hovered?.id === n.id;
              const isSelected = selected?.id === n.id;
              const isHighlight = highlightedIds.has(n.id);
              const isOnPath = pathIdSet.has(n.id);
              const isPathFrom = pathFrom?.id === n.id;
              const dim = isDimmed(n.id) || (pathIds.length > 1 && !isOnPath);
              const r = isHovered ? baseR * 1.3 : baseR;
              n.__radius = r;
              ctx.save();
              if (dim) ctx.globalAlpha = 0.15;
              // Single filled disk — no halo, no glow
              ctx.beginPath();
              ctx.arc(n.x!, n.y!, r, 0, Math.PI * 2);
              ctx.fillStyle = isOnPath ? ACCENT : colour;
              ctx.fill();
              // Accent ring for state
              if (isHovered || isSelected || isHighlight || isOnPath || isPathFrom) {
                ctx.beginPath();
                ctx.arc(n.x!, n.y!, r + 3 / scale, 0, Math.PI * 2);
                ctx.strokeStyle = ACCENT;
                ctx.lineWidth = (isPathFrom ? 1.8 : 1.2) / scale;
                ctx.stroke();
              }
              // Labels
              const showLabel = isHovered || isSelected || isOnPath || alwaysLabeled.has(n.id) || scale > 1.6;
              if (showLabel) {
                const fontSize = (isHovered || isOnPath ? 13 : 11) / scale;
                ctx.font = `${fontSize}px Inter, ui-sans-serif`;
                ctx.textAlign = "center";
                ctx.textBaseline = "top";
                const label = n.name.length > 32 ? n.name.slice(0, 30) + "…" : n.name;
                ctx.lineWidth = 3.5 / scale;
                ctx.strokeStyle = PAPER;
                ctx.strokeText(label, n.x!, n.y! + r + 3 / scale);
                ctx.fillStyle = isOnPath ? ACCENT : TEXT_INK;
                ctx.fillText(label, n.x!, n.y! + r + 3 / scale);
              }
              ctx.restore();
            }}
            // Edges
            linkCanvasObjectMode={() => "replace"}
            linkCanvasObject={(l, ctx, scale) => {
              const src = l.source as FGNode;
              const tgt = l.target as FGNode;
              if (!src.x || !src.y || !tgt.x || !tgt.y) return;
              const involved = hovered != null && (src.id === hovered.id || tgt.id === hovered.id);
              const sparqlHl = highlightedIds.size > 0 && (highlightedIds.has(src.id) && highlightedIds.has(tgt.id));
              // path: an edge is "on path" if both endpoints AND they are
              // adjacent in the path sequence
              const pathHl = (() => {
                if (pathIds.length < 2) return false;
                for (let i = 0; i < pathIds.length - 1; i++) {
                  if ((pathIds[i] === src.id && pathIds[i+1] === tgt.id) ||
                      (pathIds[i] === tgt.id && pathIds[i+1] === src.id)) return true;
                }
                return false;
              })();
              const dim = ((neighbourIds && !involved && !(neighbourIds.has(src.id) && neighbourIds.has(tgt.id)))
                       || (highlightedIds.size > 0 && !sparqlHl && !(highlightedIds.has(src.id) || highlightedIds.has(tgt.id)))
                       || (pathIds.length > 1 && !pathHl));
              ctx.save();
              if (dim) ctx.globalAlpha = 0.14;
              ctx.strokeStyle = (pathHl || sparqlHl) ? ACCENT : (involved ? "#525252" : "#cfcbc3");
              ctx.lineWidth = (pathHl ? 2 : (involved || sparqlHl) ? 1 : 0.5) / scale;
              ctx.beginPath();
              ctx.moveTo(src.x, src.y);
              ctx.lineTo(tgt.x, tgt.y);
              ctx.stroke();
              ctx.restore();
            }}
            linkDirectionalParticles={0}
          />
        </div>

        {hovered && (
          <NodeTooltip
            node={hovered}
            community={(data?.communities || []).find(c => c.id === hovered.community_id) || null}
            colour={colourOf(hovered)}
          />
        )}

        <button
          onClick={() => setSparqlOpen(o => !o)}
          className="absolute top-2.5 z-10 text-[10px] uppercase tracking-[0.2em] hover:opacity-100 transition"
          style={{
            right: sparqlOpen ? "30rem" : "24px",
            color: TEXT_MUTED,
            opacity: 0.8,
          }}
        >
          {sparqlOpen ? "SPARQL  ›" : "‹  SPARQL"}
        </button>
      </main>

      {sparqlOpen && (
        <SparqlConsole
          onResults={handleSparqlExecuted}
          nodeIds={new Set(graphData.nodes.map(n => n.id))}
        />
      )}
    </div>
  );
}


// ─── Left rail ─────────────────────────────────────────────────────────────
function LeftRail(props: {
  data: GraphPayload | null;
  graphData: { nodes: FGNode[]; links: FGLink[] };
  loading: boolean;
  error: string | null;
  minMentions: number;
  setMinMentions: (n: number) => void;
  typesEnabled: Set<string>;
  toggleType: (t: string) => void;
  colourBy: ColourBy;
  setColourBy: (c: ColourBy) => void;
  layout: Layout;
  setLayout: (l: Layout) => void;
  showHulls: boolean;
  setShowHulls: (v: boolean) => void;
  pathMode: boolean;
  setPathMode: (v: boolean) => void;
  pathFrom: FGNode | null;
  pathIds: string[];
  clearPath: () => void;
  load: () => void;
  selected: FGNode | null;
  communityById: Record<string, GraphCommunity>;
  colourOf: (n: FGNode) => string;
  connections: ConnectionGroup[];
  navigateTo: (id: string) => void;
  history: FGNode[];
  goBack: () => void;
  focusMode: boolean;
  setFocusMode: (v: boolean) => void;
}) {
  const {
    data, loading, error, minMentions, setMinMentions, typesEnabled,
    toggleType, colourBy, setColourBy, layout, setLayout, showHulls, setShowHulls,
    pathMode, setPathMode, pathFrom, pathIds, clearPath,
    load, selected, communityById, colourOf,
    connections, navigateTo, history, goBack, focusMode, setFocusMode,
  } = props;
  return (
    <aside className="w-72 shrink-0 overflow-y-auto"
           style={{ background: PAPER, borderRight: `1px solid ${RULE}`, color: TEXT_INK }}>
      <div className="px-5 pt-6 pb-5" style={{ borderBottom: `1px solid ${RULE}` }}>
        <div className="text-[10px] uppercase tracking-[0.25em]" style={{ color: TEXT_MUTED }}>
          UC5 · Knowledge Graph
        </div>
        <h2 className="font-medium text-base mt-1" style={{ letterSpacing: "-0.01em" }}>
          Apple Ontologie
        </h2>
        {data && (
          <dl className="mt-4 text-[11px]" style={{ color: TEXT_MUTED }}>
            <Row label="Entitäten" value={`${data.nodes.length}`} />
            <Row label="Relationen" value={`${data.edges.length}`} />
            <Row label="Communities" value={`${data.communities.length}`} />
          </dl>
        )}
      </div>

      <Section title="Anzeige">
        <Label>Mindesterwähnungen <span className="font-mono ml-2" style={{ color: TEXT_INK }}>{minMentions}</span></Label>
        <input
          type="range" min={1} max={10} value={minMentions}
          onChange={e => setMinMentions(Number(e.target.value))}
          className="w-full mt-1"
          style={{ accentColor: ACCENT }}
        />
      </Section>

      <Section title="Entitätstypen">
        <div className="space-y-1">
          {TYPE_OPTIONS.map(t => {
            const on = typesEnabled.has(t);
            const count = (data?.nodes || []).filter(n => n.type === t).length;
            return (
              <label key={t} className="flex items-center gap-2.5 cursor-pointer text-[13px]">
                <input type="checkbox" checked={on} onChange={() => toggleType(t)}
                       className="rounded" style={{ accentColor: ACCENT }} />
                <span className="w-2 h-2 rounded-full shrink-0" style={{ background: TYPE_COLORS[t] }} />
                <span className="flex-1" style={{ color: on ? TEXT_INK : TEXT_MUTED }}>{t}</span>
                <span className="font-mono text-[11px]" style={{ color: TEXT_MUTED }}>{count}</span>
              </label>
            );
          })}
        </div>
      </Section>

      <Section title="Farbcodierung">
        <div className="flex gap-1" style={{ border: `1px solid ${RULE}` }}>
          {(["type", "community"] as ColourBy[]).map(opt => (
            <button key={opt} onClick={() => setColourBy(opt)}
                    className="flex-1 px-2 py-1.5 text-[11px] uppercase tracking-wider transition"
                    style={{
                      background: colourBy === opt ? TEXT_INK : "transparent",
                      color: colourBy === opt ? PAPER : TEXT_MUTED,
                    }}>
              {opt === "type" ? "Typ" : "Community"}
            </button>
          ))}
        </div>
      </Section>

      <Section title="Layout">
        <div className="flex gap-1 mb-3" style={{ border: `1px solid ${RULE}` }}>
          {(["cluster", "concentric"] as Layout[]).map(opt => (
            <button key={opt} onClick={() => setLayout(opt)}
                    className="flex-1 px-2 py-1.5 text-[11px] uppercase tracking-wider transition"
                    style={{
                      background: layout === opt ? TEXT_INK : "transparent",
                      color: layout === opt ? PAPER : TEXT_MUTED,
                    }}>
              {opt === "cluster" ? "Cluster" : "Konzentrik"}
            </button>
          ))}
        </div>
        {layout === "cluster" && (
          <label className="flex items-center gap-2 cursor-pointer text-[12px]" style={{ color: TEXT_INK }}>
            <input type="checkbox" checked={showHulls}
                   onChange={e => setShowHulls(e.target.checked)}
                   className="rounded" style={{ accentColor: ACCENT }} />
            Community-Polygone zeigen
          </label>
        )}
        {layout === "concentric" && (
          <p className="text-[11px] leading-relaxed mt-1" style={{ color: TEXT_MUTED }}>
            Apple im Zentrum, Ringe nach Typ. Innerhalb eines Rings
            sortiert nach Erwähnungen (12 Uhr = häufigste).
          </p>
        )}
      </Section>

      <Section title="Pfad-Modus">
        <button onClick={() => setPathMode(!pathMode)}
                className="w-full px-3 py-1.5 text-[11px] uppercase tracking-wider transition"
                style={{
                  border: `1px solid ${pathMode ? ACCENT : TEXT_INK}`,
                  background: pathMode ? ACCENT : "transparent",
                  color: pathMode ? PAPER : TEXT_INK,
                }}>
          {pathMode ? "aktiv  ·  beenden" : "aktivieren"}
        </button>
        {pathMode && (
          <p className="text-[11px] leading-relaxed mt-2" style={{ color: TEXT_MUTED }}>
            {pathFrom == null && pathIds.length === 0 && "Klicke den Startknoten."}
            {pathFrom != null && (
              <>Start: <span style={{ color: TEXT_INK }}>{pathFrom.name}</span> · klicke Ziel.</>
            )}
            {pathIds.length > 1 && (
              <>Pfad mit <span className="font-mono" style={{ color: TEXT_INK }}>{pathIds.length}</span> Knoten · {pathIds.length - 1} Schritte.</>
            )}
          </p>
        )}
        {pathIds.length > 0 && (
          <button onClick={clearPath}
                  className="mt-2 text-[10px] uppercase tracking-wider hover:opacity-100 transition"
                  style={{ color: TEXT_MUTED, opacity: 0.7 }}>
            Pfad löschen
          </button>
        )}
      </Section>

      <div className="px-5 py-4">
        <button onClick={load} disabled={loading}
                className="w-full px-3 py-2 text-[11px] uppercase tracking-wider transition"
                style={{
                  border: `1px solid ${TEXT_INK}`,
                  background: loading ? PAPER_SOFT : "transparent",
                  color: TEXT_INK,
                  opacity: loading ? 0.5 : 1,
                }}
                onMouseEnter={e => { if (!loading) { e.currentTarget.style.background = TEXT_INK; e.currentTarget.style.color = PAPER; } }}
                onMouseLeave={e => { if (!loading) { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = TEXT_INK; } }}>
          {loading ? "Lädt …" : "Aktualisieren"}
        </button>
      </div>

      <DBpediaValidator onComplete={load} />


      {error && (
        <div className="mx-5 mb-4 text-[11px] p-2.5"
             style={{ border: `1px solid ${ACCENT}`, color: ACCENT }}>{error}</div>
      )}

      {selected && (
        <ConnectionPanel
          selected={selected}
          connections={connections}
          history={history}
          goBack={goBack}
          navigateTo={navigateTo}
          focusMode={focusMode}
          setFocusMode={setFocusMode}
          colourOf={colourOf}
          communityById={communityById}
        />
      )}
    </aside>
  );
}


// ─── Connection Panel — Wikipedia-style hyperlinked navigation ────────────
// When an entity is selected, this panel shows ALL its connections grouped
// by relation type and direction. Clicking any neighbour navigates to it
// (which fires camera fly-to, updates the panel, pushes the previous
// selection onto a back-stack so the user can wander Wikipedia-style).
function ConnectionPanel(props: {
  selected: FGNode;
  connections: ConnectionGroup[];
  history: FGNode[];
  goBack: () => void;
  navigateTo: (id: string) => void;
  focusMode: boolean;
  setFocusMode: (v: boolean) => void;
  colourOf: (n: FGNode) => string;
  communityById: Record<string, GraphCommunity>;
}) {
  const {
    selected, connections, history, goBack, navigateTo,
    focusMode, setFocusMode, colourOf, communityById,
  } = props;

  const totalConnections = connections.reduce((s, g) => s + g.entries.length, 0);
  const community = selected.community_id ? communityById[selected.community_id] : null;

  return (
    <div className="px-5 py-5" style={{ borderTop: `1px solid ${RULE}` }}>
      {/* Breadcrumb */}
      {history.length > 0 && (
        <div className="mb-3 text-[10px] uppercase tracking-[0.2em]">
          <button onClick={goBack} className="hover:opacity-100 transition"
                  style={{ color: ACCENT, opacity: 0.85 }}>
            ‹ zurück zu {history[history.length - 1].name}
          </button>
          <span className="mx-2" style={{ color: RULE }}>·</span>
          <span style={{ color: TEXT_MUTED }}>{history.length} Schritt{history.length === 1 ? "" : "e"}</span>
        </div>
      )}

      {/* Identity card */}
      <div className="text-[10px] uppercase tracking-[0.25em] mb-2" style={{ color: TEXT_MUTED }}>
        Ausgewählt
      </div>
      <div className="flex items-center gap-2 mb-1">
        <span className="w-2.5 h-2.5 rounded-full" style={{ background: colourOf(selected) }} />
        <span className="font-medium text-[16px]" style={{ letterSpacing: "-0.01em" }}>
          {selected.name}
        </span>
      </div>
      <div className="text-[11px] font-mono" style={{ color: TEXT_MUTED }}>
        {selected.type} · {selected.mentions} Erwähnungen
        {selected.community_id && <> · {selected.community_id}</>}
      </div>
      {selected.description && (
        <p className="text-[13px] mt-3 leading-relaxed whitespace-pre-wrap">
          {selected.description}
        </p>
      )}

      {/* Focus toggle — only this entity's ego network visible in the graph */}
      <button onClick={() => setFocusMode(!focusMode)}
              className="mt-3 px-2.5 py-1 text-[10px] uppercase tracking-wider transition"
              style={{
                border: `1px solid ${focusMode ? ACCENT : RULE}`,
                background: focusMode ? ACCENT : "transparent",
                color: focusMode ? PAPER : TEXT_MUTED,
              }}>
        {focusMode ? "Fokus aktiv · auflösen" : "Nur Nachbarschaft zeigen"}
      </button>

      {/* Connections grouped by relation type */}
      <div className="mt-5">
        <div className="flex items-baseline justify-between mb-3">
          <div className="text-[10px] uppercase tracking-[0.25em]" style={{ color: TEXT_INK }}>
            Verbindungen
          </div>
          <div className="text-[10px] font-mono" style={{ color: TEXT_MUTED }}>
            {totalConnections}
          </div>
        </div>

        {connections.length === 0 && (
          <p className="text-[11px]" style={{ color: TEXT_MUTED }}>
            Keine Verbindungen im aktuellen Sub-Graphen.
          </p>
        )}

        <div className="space-y-4">
          {connections.map(group => (
            <div key={`${group.relType}-${group.direction}`}>
              <div className="flex items-center gap-1.5 mb-1.5 text-[10px] uppercase tracking-[0.2em]"
                   style={{ color: TEXT_MUTED }}>
                <span style={{ color: TEXT_INK, fontFamily: "monospace" }}>
                  {group.direction === "out" ? "→" : "←"}
                </span>
                <span>{prettifyRelation(group.relType)}</span>
                <span className="ml-auto font-mono" style={{ color: TEXT_MUTED }}>
                  {group.entries.length}
                </span>
              </div>
              <div>
                {group.entries.map(e => (
                  <button
                    key={e.node.id}
                    onClick={() => navigateTo(e.node.id)}
                    className="w-full text-left flex items-center gap-2 py-1 px-1 -mx-1 transition group"
                    style={{ color: TEXT_INK }}
                    onMouseEnter={ev => ev.currentTarget.style.background = PAPER_SOFT}
                    onMouseLeave={ev => ev.currentTarget.style.background = "transparent"}
                  >
                    <span className="w-1.5 h-1.5 rounded-full shrink-0"
                          style={{ background: TYPE_COLORS[e.node.type] || DEFAULT_COLOR }} />
                    <span className="text-[12.5px] truncate flex-1" title={e.node.name}>
                      {e.node.name}
                    </span>
                    <span className="text-[10px] font-mono opacity-60 group-hover:opacity-100 transition"
                          style={{ color: TEXT_MUTED }}>
                      {e.node.mentions}
                    </span>
                    <span className="text-[10px] opacity-0 group-hover:opacity-100 transition"
                          style={{ color: ACCENT }}>↗</span>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Community context */}
      {community && (
        <div className="mt-5 pt-4" style={{ borderTop: `1px solid ${RULE}` }}>
          <div className="text-[10px] uppercase tracking-[0.25em]" style={{ color: TEXT_MUTED }}>
            Community {community.id}
          </div>
          <div className="text-[11px] mt-1 mb-2 font-mono" style={{ color: TEXT_MUTED }}>
            Level {community.level} · {community.size} Mitglieder
          </div>
          <p className="text-[12px] leading-relaxed">{community.summary}</p>
        </div>
      )}
    </div>
  );
}


// ─── DBpedia validator — cross-checks UE3 extractions against DBpedia ─────
function DBpediaValidator({ onComplete }: { onComplete: () => void }) {
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<null | {
    canonical_persons_fetched: number;
    canonical_persons_added: number;
    unverified_persons_total: number;
    persons_confirmed: number;
    persons_demoted: number;
  }>(null);

  const run = async () => {
    setRunning(true); setError(null); setStats(null);
    try {
      const r = await api.ue4Validate();
      if (!r.ok) { setError(r.error || "Validator fehlgeschlagen"); return; }
      setStats(r.stats || null);
      onComplete();
    } catch (e) { setError(String(e)); }
    finally { setRunning(false); }
  };

  return (
    <div className="px-5 py-4" style={{ borderTop: `1px solid ${RULE}` }}>
      <div className="text-[10px] uppercase tracking-[0.25em] mb-3" style={{ color: TEXT_MUTED }}>
        DBpedia · Validierung
      </div>
      <p className="text-[11px] leading-relaxed mb-3" style={{ color: TEXT_MUTED }}>
        Holt kanonische Apple-Personen aus DBpedia und entfernt Kontext-only
        Personen aus den Rollen-Queries.
      </p>
      <button onClick={run} disabled={running}
              className="w-full px-3 py-2 text-[11px] uppercase tracking-wider transition"
              style={{
                border: `1px solid ${ACCENT}`,
                background: running ? PAPER_SOFT : "transparent",
                color: ACCENT,
                opacity: running ? 0.5 : 1,
              }}
              onMouseEnter={e => { if (!running) { e.currentTarget.style.background = ACCENT; e.currentTarget.style.color = PAPER; } }}
              onMouseLeave={e => { if (!running) { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = ACCENT; } }}>
        {running ? "Validiert …" : "DBpedia validieren"}
      </button>
      {error && (
        <div className="mt-3 text-[11px] font-mono p-2 break-all"
             style={{ border: `1px solid ${ACCENT}`, color: ACCENT }}>{error}</div>
      )}
      {stats && (
        <dl className="mt-3 text-[11px] space-y-0.5" style={{ color: TEXT_MUTED }}>
          <Row label="aus DBpedia geholt" value={String(stats.canonical_persons_fetched)} />
          <Row label="neu eingefügt"      value={String(stats.canonical_persons_added)} />
          <Row label="ungeprüft (Start)"  value={String(stats.unverified_persons_total)} />
          <Row label="bestätigt"          value={String(stats.persons_confirmed)} />
          <Row label="demoted"            value={String(stats.persons_demoted)} />
        </dl>
      )}
    </div>
  );
}


// ─── Tooltip (small, restrained, no glow) ───────────────────────────────────
function NodeTooltip({ node, community, colour }: { node: FGNode; community: GraphCommunity | null; colour: string }) {
  return (
    <div className="absolute z-20 pointer-events-none bottom-6 left-1/2 -translate-x-1/2 max-w-md p-3"
         style={{ background: PAPER, border: `1px solid ${TEXT_INK}` }}>
      <div className="flex items-baseline gap-2 mb-1">
        <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: colour }} />
        <span className="font-medium text-[13px]" style={{ color: TEXT_INK }}>{node.name}</span>
        <span className="text-[10px] uppercase tracking-wider ml-auto" style={{ color: TEXT_MUTED }}>{node.type}</span>
      </div>
      <div className="text-[11px] font-mono mb-1.5" style={{ color: TEXT_MUTED }}>
        {node.mentions} Erwähnungen{community && <> · Community {community.id}</>}
      </div>
      {node.description && (
        <p className="text-[12px] leading-relaxed" style={{ color: TEXT_INK }}>{node.description}</p>
      )}
    </div>
  );
}


// ─── Small typographic helpers (Aicher: signage built on lockup grids) ─────
function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between py-0.5">
      <dt>{label}</dt><dd className="font-mono" style={{ color: TEXT_INK }}>{value}</dd>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="px-5 py-4" style={{ borderBottom: `1px solid ${RULE}` }}>
      <div className="text-[10px] uppercase tracking-[0.25em] mb-3" style={{ color: TEXT_MUTED }}>
        {title}
      </div>
      {children}
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[11px] uppercase tracking-wider" style={{ color: TEXT_MUTED }}>{children}</div>
  );
}


// ─── SPARQL console ────────────────────────────────────────────────────────
const EXAMPLE_QUERIES: { label: string; sparql: string }[] = [
  {
    label: "Personen mit Rolle (CEO, Founder, Designer)",
    sparql: `PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX apple: <http://uc5.butscher.cloud/apple#>
SELECT DISTINCT ?name ?role WHERE {
  VALUES ?role { apple:CEO apple:Founder apple:Designer apple:Executive apple:Engineer }
  ?p a ?role ; rdfs:label ?name .
} ORDER BY ?role ?name`,
  },
  {
    label: "Subklassen-Inferenz: alle Smartphones",
    sparql: `PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX apple: <http://uc5.butscher.cloud/apple#>
SELECT DISTINCT ?name WHERE {
  ?p rdf:type/rdfs:subClassOf* apple:Smartphone ; rdfs:label ?name .
}`,
  },
  {
    label: "Verteilung der Entitätstypen",
    sparql: `PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX apple: <http://uc5.butscher.cloud/apple#>
SELECT ?type (COUNT(?s) AS ?anzahl) WHERE {
  ?s a ?type .
  FILTER(STRSTARTS(STR(?type), "http://uc5.butscher.cloud/apple#"))
} GROUP BY ?type ORDER BY DESC(?anzahl)`,
  },
];


function SparqlConsole({ onResults, nodeIds }: {
  onResults: (matched: string[]) => void;
  nodeIds: Set<string>;
}) {
  const [nlQuery, setNlQuery] = useState("");
  const [sparql, setSparql] = useState("");
  const [translating, setTranslating] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [result, setResult] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);

  const translate = async () => {
    if (!nlQuery.trim()) return;
    setTranslating(true); setError(null); setResult(null);
    try {
      const r = await api.sparqlTranslate(nlQuery.trim());
      if (r.ok && r.sparql) {
        setSparql(r.sparql);
        // Auto-execute so the user sees the answer in one click.
        await executeWith(r.sparql);
      } else {
        setError(r.error || "Übersetzung fehlgeschlagen");
      }
    } catch (e) { setError(String(e)); }
    finally { setTranslating(false); }
  };

  const executeWith = async (querySparql: string) => {
    const s = querySparql.trim();
    if (!s) return;
    setExecuting(true); setError(null); setResult(null);
    try {
      const r = await api.sparqlExecute(s);
      if (!r.ok) { setError(r.error || "Fehler"); return; }
      setResult(r.result);
      const matched: string[] = [];
      const bindings = r.result?.results?.bindings || [];
      for (const b of bindings) {
        for (const v of Object.values(b) as any[]) {
          if (v?.type === "uri" && v.value.startsWith("http://uc5.butscher.cloud/apple#")) {
            const last = v.value.split("#")[1].toLowerCase();
            for (const id of nodeIds) {
              const idNorm = id.split(":")[1]?.replace(/\s+/g, "").toLowerCase();
              if (idNorm && (idNorm === last || last.includes(idNorm) || idNorm.includes(last))) {
                if (!matched.includes(id)) matched.push(id);
              }
            }
          }
        }
      }
      onResults(matched);
    } catch (e) { setError(String(e)); }
    finally { setExecuting(false); }
  };

  const execute = () => executeWith(sparql);

  return (
    <aside className="w-[30rem] shrink-0 flex flex-col"
           style={{ background: PAPER, borderLeft: `1px solid ${RULE}`, color: TEXT_INK }}>
      <div className="px-6 pt-6 pb-4" style={{ borderBottom: `1px solid ${RULE}` }}>
        <div className="text-[10px] uppercase tracking-[0.25em]" style={{ color: TEXT_MUTED }}>
          UE4 · Konsole
        </div>
        <h2 className="font-medium text-base mt-1" style={{ letterSpacing: "-0.01em" }}>
          SPARQL Query
        </h2>
      </div>

      <div className="px-6 py-5 space-y-5 overflow-y-auto flex-1">
        {/* NL → SPARQL */}
        <div>
          <Label>Frage in natürlicher Sprache</Label>
          <div className="flex gap-2 mt-1.5">
            <input
              value={nlQuery}
              onChange={e => setNlQuery(e.target.value)}
              onKeyDown={e => e.key === "Enter" && translate()}
              placeholder="Wer sind die CEOs?"
              className="flex-1 px-0 py-2 text-[13px] bg-transparent focus:outline-none"
              style={{ borderBottom: `1px solid ${RULE}`, color: TEXT_INK }}
              onFocus={e => e.target.style.borderBottomColor = ACCENT}
              onBlur={e => e.target.style.borderBottomColor = RULE}
            />
            <button onClick={translate} disabled={translating || !nlQuery.trim()}
                    className="px-3 py-1.5 text-[11px] uppercase tracking-wider transition disabled:opacity-30"
                    style={{ border: `1px solid ${TEXT_INK}`, color: TEXT_INK }}
                    onMouseEnter={e => { if (!translating && nlQuery.trim()) { e.currentTarget.style.background = TEXT_INK; e.currentTarget.style.color = PAPER; } }}
                    onMouseLeave={e => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = TEXT_INK; }}>
              {translating ? "…" : "Übersetzen"}
            </button>
          </div>
        </div>

        {/* Examples */}
        <div>
          <Label>Beispielqueries</Label>
          <div className="mt-1.5 space-y-1">
            {EXAMPLE_QUERIES.map((ex, i) => (
              <button key={i} onClick={() => setSparql(ex.sparql)}
                      className="block w-full text-left text-[12px] py-1.5 hover:opacity-100 transition"
                      style={{ color: TEXT_MUTED, opacity: 0.85 }}
                      onMouseEnter={e => e.currentTarget.style.color = ACCENT}
                      onMouseLeave={e => e.currentTarget.style.color = TEXT_MUTED}>
                <span className="font-mono mr-2" style={{ color: TEXT_INK }}>{(i + 1).toString().padStart(2, "0")}</span>
                {ex.label}
              </button>
            ))}
          </div>
        </div>

        {/* Editor */}
        <div>
          <Label>SPARQL</Label>
          <textarea
            value={sparql}
            onChange={e => setSparql(e.target.value)}
            placeholder="SELECT ?s WHERE { ?s a apple:CEO } …"
            spellCheck={false}
            className="w-full h-56 mt-1.5 px-3 py-2.5 text-[12px] font-mono leading-relaxed focus:outline-none resize-none"
            style={{ background: PAPER_SOFT, border: `1px solid ${RULE}`, color: TEXT_INK }}
            onFocus={e => e.target.style.borderColor = TEXT_INK}
            onBlur={e => e.target.style.borderColor = RULE}
          />
        </div>

        <div className="flex gap-2">
          <button onClick={execute} disabled={executing || !sparql.trim()}
                  className="flex-1 px-4 py-2 text-[11px] uppercase tracking-wider transition disabled:opacity-30"
                  style={{
                    background: TEXT_INK, color: PAPER,
                    border: `1px solid ${TEXT_INK}`,
                  }}
                  onMouseEnter={e => { if (!executing && sparql.trim()) { e.currentTarget.style.background = ACCENT; e.currentTarget.style.borderColor = ACCENT; } }}
                  onMouseLeave={e => { e.currentTarget.style.background = TEXT_INK; e.currentTarget.style.borderColor = TEXT_INK; }}>
            {executing ? "Läuft …" : "Ausführen"}
          </button>
          <button onClick={() => { setSparql(""); setResult(null); setError(null); onResults([]); }}
                  className="px-3 py-2 text-[11px] uppercase tracking-wider hover:opacity-100 transition"
                  style={{ color: TEXT_MUTED, opacity: 0.7 }}>
            Zurücksetzen
          </button>
        </div>

        {error && (
          <div className="text-[12px] font-mono p-2.5 break-all"
               style={{ border: `1px solid ${ACCENT}`, color: ACCENT }}>{error}</div>
        )}

        {executing && (
          <div className="text-[11px] uppercase tracking-wider" style={{ color: TEXT_MUTED }}>
            führt SPARQL aus …
          </div>
        )}

        {result && !executing && <ResultTable result={result} />}
      </div>
    </aside>
  );
}


function ResultTable({ result }: { result: any }) {
  const headVars: string[] = result?.head?.vars || [];
  const bindings: any[] = result?.results?.bindings || [];
  // ASK queries: GraphDB returns { boolean: true/false }
  if (typeof result?.boolean === "boolean") {
    return (
      <div className="py-2" style={{ borderTop: `1px solid ${RULE}`, borderBottom: `1px solid ${RULE}` }}>
        <span className="text-[10px] uppercase tracking-wider mr-3" style={{ color: TEXT_MUTED }}>ASK</span>
        <span className="font-mono text-[14px]"
              style={{ color: result.boolean ? TEXT_INK : ACCENT }}>
          {String(result.boolean)}
        </span>
      </div>
    );
  }
  // SELECT with zero rows — show explicit empty state so the user knows
  // the query *did* run, it just had no matches.
  if (Array.isArray(bindings) && bindings.length === 0) {
    return (
      <div className="space-y-2">
        <div className="text-[10px] uppercase tracking-[0.2em]" style={{ color: TEXT_MUTED }}>
          Ergebnis · <span className="font-mono" style={{ color: TEXT_INK }}>0</span> Zeilen
        </div>
        <div className="p-3 text-[12px] leading-relaxed"
             style={{ border: `1px solid ${RULE}`, background: PAPER_SOFT, color: TEXT_INK }}>
          Die Query lief erfolgreich, lieferte aber keine Bindings.
          Mögliche Ursachen:
          <ul className="mt-1.5 list-disc pl-5" style={{ color: TEXT_MUTED }}>
            <li>zu enger Filter (z.&nbsp;B. zusätzliches <code className="font-mono">apple:associatedWith apple:AppleInc</code>)</li>
            <li>falsche Klasse — versuche eine Oberklasse wie <code className="font-mono">apple:Person</code></li>
            <li>Reasoning greift nicht — prüfe Prefixe und <code className="font-mono">rdf:type</code></li>
          </ul>
        </div>
      </div>
    );
  }
  if (!Array.isArray(bindings)) {
    return <div className="text-[11px]" style={{ color: TEXT_MUTED }}>(kein Tabellenergebnis)</div>;
  }
  return (
    <div className="space-y-2">
      <div className="text-[10px] uppercase tracking-[0.2em]" style={{ color: TEXT_MUTED }}>
        Ergebnis · <span className="font-mono" style={{ color: TEXT_INK }}>{bindings.length}</span> Zeilen
      </div>
      {/* Tufte-style table: only horizontal hairlines, no vertical, sparse */}
      <div className="overflow-x-auto" style={{ borderTop: `1px solid ${TEXT_INK}`, borderBottom: `1px solid ${TEXT_INK}` }}>
        <table className="text-[12px] w-full" style={{ borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: `1px solid ${RULE}` }}>
              {headVars.map(v => (
                <th key={v} className="text-left px-2 py-1.5 font-mono font-normal text-[10px] uppercase tracking-wider"
                    style={{ color: TEXT_MUTED }}>{v}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {bindings.slice(0, 100).map((row: any, i: number) => (
              <tr key={i}>
                {headVars.map(v => {
                  const val = row[v];
                  if (!val) return <td key={v} className="px-2 py-1" style={{ color: TEXT_MUTED }}>—</td>;
                  const display = val.type === "uri"
                    ? val.value.split(/[/#]/).pop()
                    : val.value;
                  return (
                    <td key={v}
                        title={val.value}
                        className={"px-2 py-1 truncate max-w-[16rem] " + (val.type === "uri" ? "font-mono" : "")}
                        style={{ color: TEXT_INK }}>
                      {display}
                    </td>
                  );
                })}
              </tr>
            ))}
            {bindings.length > 100 && (
              <tr><td colSpan={headVars.length} className="text-center text-[11px] py-1.5"
                       style={{ color: TEXT_MUTED }}>… {bindings.length - 100} weitere</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
