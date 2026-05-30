import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D, { type ForceGraphMethods } from "react-force-graph-2d";
import {
  api, type GraphCommunity, type GraphEdge, type GraphNode, type GraphPayload,
} from "../api";

// ─── Neon palette — colors per entity type (high-saturation for dark bg) ────
const TYPE_COLORS: Record<string, string> = {
  PERSON:       "#22d3ee", // cyan-400
  ORGANIZATION: "#a78bfa", // violet-400
  PRODUCT:      "#f472b6", // pink-400
  EVENT:        "#fbbf24", // amber-400
  LOCATION:     "#34d399", // emerald-400
  CONCEPT:      "#fb7185", // rose-400
};
const DEFAULT_COLOR = "#94a3b8";

const TYPE_OPTIONS = ["PERSON", "ORGANIZATION", "PRODUCT", "EVENT", "LOCATION", "CONCEPT"];

interface FGNode extends GraphNode {
  x?: number; y?: number; vx?: number; vy?: number;
  __radius?: number;     // cached for hover hit-test
  __highlight?: boolean; // dimmed vs. highlighted
}

interface FGLink extends GraphEdge {
  source: string | FGNode;
  target: string | FGNode;
}

type ColourBy = "type" | "community";

export function Graph() {
  const [data, setData] = useState<GraphPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<FGNode | null>(null);
  const [hovered, setHovered] = useState<FGNode | null>(null);
  const [mousePos, setMousePos] = useState<{ x: number; y: number } | null>(null);
  const [minMentions, setMinMentions] = useState(1);
  const [search, setSearch] = useState("");
  const [typesEnabled, setTypesEnabled] = useState<Set<string>>(new Set(TYPE_OPTIONS));
  const [colourBy, setColourBy] = useState<ColourBy>("type");
  const [highlightedIds, setHighlightedIds] = useState<Set<string>>(new Set());
  const [sparqlOpen, setSparqlOpen] = useState(true);
  const graphRef = useRef<ForceGraphMethods<FGNode, FGLink> | undefined>(undefined);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ w: 800, h: 600 });

  // ── Data loading ────────────────────────────────────────────────────────
  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const types = TYPE_OPTIONS.every(t => typesEnabled.has(t))
        ? undefined
        : Array.from(typesEnabled).join(",");
      const r = await api.graph({ min_mentions: minMentions, types, limit_entities: 500 });
      setData(r);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Container resize
  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver(([entry]) => {
      setSize({ w: entry.contentRect.width, h: entry.contentRect.height });
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  // ── Derived graph data with search filter applied client-side ───────────
  const graphData = useMemo(() => {
    if (!data) return { nodes: [], links: [] as FGLink[] };
    const q = search.trim().toLowerCase();
    const allKeep = new Set(data.nodes.map(n => n.id));
    // If a search term is given, keep matching nodes + their direct neighbours
    let keep = allKeep;
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
    const nodeIds = new Set(nodes.map(n => n.id));
    const links: FGLink[] = data.edges
      .filter(e => nodeIds.has(e.source) && nodeIds.has(e.target))
      .map(e => ({ ...e }));
    return { nodes, links };
  }, [data, search]);

  // Community → colour mapping (vibrant palette)
  const communityColour = useMemo(() => {
    const palette = [
      "#22d3ee", "#a78bfa", "#f472b6", "#fbbf24", "#34d399", "#fb7185",
      "#60a5fa", "#c084fc", "#fb923c", "#4ade80", "#f87171", "#2dd4bf",
      "#facc15", "#e879f9", "#38bdf8", "#a3e635", "#fb7185", "#818cf8",
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

  // ── Hover highlighting: dim non-connected nodes/links ───────────────────
  const neighbourIds = useMemo(() => {
    if (!hovered || !data) return null as Set<string> | null;
    const ids = new Set<string>([hovered.id]);
    for (const e of data.edges) {
      if (e.source === hovered.id) ids.add(e.target);
      if (e.target === hovered.id) ids.add(e.source);
    }
    return ids;
  }, [hovered, data]);

  const isDimmed = (id: string) =>
    (neighbourIds != null && !neighbourIds.has(id) && highlightedIds.size === 0) ||
    (highlightedIds.size > 0 && !highlightedIds.has(id));

  const toggleType = (t: string) => {
    setTypesEnabled(cur => {
      const next = new Set(cur);
      if (next.has(t)) next.delete(t); else next.add(t);
      return next;
    });
  };

  const handleSparqlExecuted = (matchedNodeIds: string[]) => {
    setHighlightedIds(new Set(matchedNodeIds));
    // Recentre on the first match
    if (matchedNodeIds.length > 0 && graphRef.current && data) {
      const n = graphData.nodes.find(nn => nn.id === matchedNodeIds[0]);
      if (n && n.x != null && n.y != null) {
        graphRef.current.centerAt(n.x, n.y, 800);
        graphRef.current.zoom(2.5, 800);
      }
    }
  };

  return (
    <div className="flex-1 flex bg-slate-950 text-slate-100 min-h-0 overflow-hidden">
      {/* ── Left sidebar ─────────────────────────────────────────────── */}
      <LeftSidebar
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
        load={load}
        selected={selected}
        communityById={Object.fromEntries((data?.communities || []).map(c => [c.id, c]))}
        colourOf={colourOf}
      />

      {/* ── Main: graph with overlays ────────────────────────────────── */}
      <main ref={containerRef} className="flex-1 relative bg-[#06080f]">
        {/* Animated star background */}
        <StarField w={size.w} h={size.h} />

        {/* Search overlay top-left */}
        <div className="absolute top-3 left-3 z-10 flex items-center gap-2">
          <div className="relative">
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Suche Entitäten…"
              className="w-72 pl-9 pr-3 py-2 rounded-lg bg-slate-900/70 backdrop-blur border border-cyan-500/30 text-sm placeholder-slate-500 text-slate-100 focus:outline-none focus:border-cyan-400 focus:shadow-[0_0_15px_rgba(34,211,238,0.4)] transition-all"
            />
            <svg className="absolute left-2.5 top-2.5 w-4 h-4 text-cyan-400" viewBox="0 0 20 20" fill="none">
              <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="2"/>
              <path d="M14 14L18 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
          </div>
          {(highlightedIds.size > 0) && (
            <button
              onClick={() => setHighlightedIds(new Set())}
              className="px-3 py-2 text-xs rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 hover:bg-cyan-500/20 backdrop-blur transition"
            >
              SPARQL-Highlight aufheben ({highlightedIds.size})
            </button>
          )}
        </div>

        {/* Legend top-right */}
        <div className="absolute top-3 right-3 z-10 bg-slate-900/70 backdrop-blur border border-slate-700/50 rounded-lg p-3 text-xs flex gap-3">
          {TYPE_OPTIONS.map(t => (
            <div key={t} className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full" style={{
                background: TYPE_COLORS[t],
                boxShadow: `0 0 8px ${TYPE_COLORS[t]}`,
              }} />
              <span className="text-slate-300">{t}</span>
            </div>
          ))}
        </div>

        {/* Zoom controls bottom-right */}
        <div className="absolute bottom-3 right-3 z-10 flex flex-col gap-1 bg-slate-900/70 backdrop-blur rounded-lg border border-slate-700/50 p-1">
          <button title="Zoom in" onClick={() => graphRef.current?.zoom(graphRef.current.zoom() * 1.4, 300)}
                  className="w-8 h-8 rounded text-slate-300 hover:bg-cyan-500/20 hover:text-cyan-300 transition">+</button>
          <button title="Zoom out" onClick={() => graphRef.current?.zoom(graphRef.current.zoom() * 0.7, 300)}
                  className="w-8 h-8 rounded text-slate-300 hover:bg-cyan-500/20 hover:text-cyan-300 transition">−</button>
          <button title="Zentrieren" onClick={() => graphRef.current?.zoomToFit(600, 80)}
                  className="w-8 h-8 rounded text-slate-300 hover:bg-cyan-500/20 hover:text-cyan-300 transition">⤢</button>
        </div>

        {/* Graph itself */}
        <ForceGraph2D<FGNode, FGLink>
          ref={graphRef}
          width={size.w}
          height={size.h}
          backgroundColor="rgba(6,8,15,0)"
          graphData={graphData}
          nodeId="id"
          nodeRelSize={1}
          d3AlphaDecay={0.02}
          d3VelocityDecay={0.3}
          cooldownTicks={400}
          warmupTicks={60}
          enableNodeDrag={true}
          enableZoomInteraction={true}
          onNodeHover={(n) => setHovered(n)}
          onNodeClick={(n, evt) => {
            setSelected(n);
            if (n.x != null && n.y != null) graphRef.current?.centerAt(n.x, n.y, 500);
          }}
          onBackgroundClick={() => setSelected(null)}
          // Custom node rendering: glowing disk + label on hover or zoomed-in
          nodeCanvasObjectMode={() => "replace"}
          nodeCanvasObject={(n, ctx, scale) => {
            const colour = colourOf(n);
            const baseSize = 3 + Math.sqrt(n.mentions + 1) * 1.5;
            const isHovered = hovered?.id === n.id;
            const isSelected = selected?.id === n.id;
            const isHighlight = highlightedIds.has(n.id);
            const dim = isDimmed(n.id);
            const r = isHovered ? baseSize * 1.6 : baseSize;
            n.__radius = r;
            ctx.save();
            if (dim) ctx.globalAlpha = 0.18;
            // Outer glow halo
            const haloR = r * (isHovered || isHighlight ? 4 : 2.6);
            const grad = ctx.createRadialGradient(n.x!, n.y!, r * 0.4, n.x!, n.y!, haloR);
            grad.addColorStop(0, colour + (isHovered || isHighlight ? "cc" : "66"));
            grad.addColorStop(1, colour + "00");
            ctx.fillStyle = grad;
            ctx.beginPath();
            ctx.arc(n.x!, n.y!, haloR, 0, Math.PI * 2);
            ctx.fill();
            // Inner disk
            ctx.beginPath();
            ctx.arc(n.x!, n.y!, r, 0, Math.PI * 2);
            ctx.fillStyle = colour;
            ctx.fill();
            // Crisp white core
            ctx.beginPath();
            ctx.arc(n.x!, n.y!, r * 0.4, 0, Math.PI * 2);
            ctx.fillStyle = "rgba(255,255,255,0.85)";
            ctx.fill();
            // Selection ring
            if (isSelected || isHighlight) {
              ctx.beginPath();
              ctx.arc(n.x!, n.y!, r + 2, 0, Math.PI * 2);
              ctx.strokeStyle = isHighlight ? "#fcd34d" : "#fde047";
              ctx.lineWidth = 1.5 / scale;
              ctx.stroke();
            }
            // Label when zoomed or hovered
            if (isHovered || isSelected || scale > 1.6) {
              const fontSize = isHovered ? 14 / scale : 11 / scale;
              ctx.font = `${fontSize}px ui-sans-serif, system-ui`;
              ctx.textAlign = "center";
              ctx.textBaseline = "top";
              ctx.fillStyle = "rgba(248, 250, 252, 0.95)";
              ctx.strokeStyle = "rgba(6, 8, 15, 0.9)";
              ctx.lineWidth = 3 / scale;
              const label = n.name.length > 32 ? n.name.slice(0, 30) + "…" : n.name;
              ctx.strokeText(label, n.x!, n.y! + r + 3 / scale);
              ctx.fillText(label, n.x!, n.y! + r + 3 / scale);
            }
            ctx.restore();
          }}
          // Custom link rendering with hover-highlight
          linkCanvasObjectMode={() => "replace"}
          linkCanvasObject={(l, ctx, scale) => {
            const src = l.source as FGNode;
            const tgt = l.target as FGNode;
            if (!src.x || !src.y || !tgt.x || !tgt.y) return;
            const involved = hovered != null && (src.id === hovered.id || tgt.id === hovered.id);
            const dim = (neighbourIds && !involved && !(neighbourIds.has(src.id) && neighbourIds.has(tgt.id)))
                     || (highlightedIds.size > 0 && !(highlightedIds.has(src.id) || highlightedIds.has(tgt.id)));
            ctx.save();
            if (dim) ctx.globalAlpha = 0.08;
            ctx.strokeStyle = involved ? "rgba(34, 211, 238, 0.7)" : "rgba(148, 163, 184, 0.25)";
            ctx.lineWidth = involved ? 1.5 / scale : 0.5 / scale;
            ctx.beginPath();
            ctx.moveTo(src.x, src.y);
            ctx.lineTo(tgt.x, tgt.y);
            ctx.stroke();
            ctx.restore();
          }}
          linkDirectionalParticles={(l) => {
            const src = l.source as FGNode; const tgt = l.target as FGNode;
            const involved = hovered != null && (src.id === hovered.id || tgt.id === hovered.id);
            return involved ? 3 : 0;
          }}
          linkDirectionalParticleWidth={2}
          linkDirectionalParticleColor={() => "rgba(34, 211, 238, 0.9)"}
        />

        {/* HTML tooltip on hover */}
        {hovered && (
          <NodeTooltip
            node={hovered}
            community={(data?.communities || []).find(c => c.id === hovered.community_id) || null}
            colour={colourOf(hovered)}
          />
        )}

        {/* Toggle SPARQL panel */}
        <button
          onClick={() => setSparqlOpen(o => !o)}
          className={"absolute z-10 top-3 transition-all px-3 py-2 rounded-lg bg-cyan-500/10 border border-cyan-500/40 text-cyan-300 hover:bg-cyan-500/20 backdrop-blur text-sm font-mono shadow-[0_0_15px_rgba(34,211,238,0.2)] " + (sparqlOpen ? "right-[26rem]" : "right-3 top-16")}
        >
          {sparqlOpen ? "› SPARQL" : "‹ SPARQL"}
        </button>
      </main>

      {/* ── Right SPARQL console ─────────────────────────────────────── */}
      {sparqlOpen && (
        <SparqlConsole
          onResults={handleSparqlExecuted}
          nodeIds={new Set(graphData.nodes.map(n => n.id))}
        />
      )}
    </div>
  );
}


// ─── Left sidebar ──────────────────────────────────────────────────────────
function LeftSidebar(props: {
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
  load: () => void;
  selected: FGNode | null;
  communityById: Record<string, GraphCommunity>;
  colourOf: (n: FGNode) => string;
}) {
  const {
    data, graphData, loading, error, minMentions, setMinMentions, typesEnabled,
    toggleType, colourBy, setColourBy, load, selected, communityById, colourOf,
  } = props;
  return (
    <aside className="w-72 shrink-0 bg-slate-900/60 backdrop-blur-xl border-r border-slate-800/80 p-4 overflow-y-auto space-y-5">
      <div>
        <div className="text-[10px] uppercase tracking-[0.3em] text-cyan-400/70 mb-1">UC5 · Knowledge Graph</div>
        <h3 className="font-bold text-lg text-slate-100">Apple Ontologie</h3>
        {data ? (
          <div className="text-xs text-slate-400 mt-2 space-y-0.5">
            <div><span className="text-cyan-300 font-mono">{graphData.nodes.length}</span>/{data.nodes.length} Entities</div>
            <div><span className="text-cyan-300 font-mono">{graphData.links.length}</span> Relations sichtbar</div>
            <div><span className="text-cyan-300 font-mono">{data.communities.length}</span> Communities</div>
          </div>
        ) : (
          <div className="text-xs text-slate-500 mt-2">Lade…</div>
        )}
      </div>

      <div>
        <label className="text-[11px] font-semibold text-slate-300 uppercase tracking-wider block mb-1.5">
          Min. Erwähnungen: <span className="text-cyan-300">{minMentions}</span>
        </label>
        <input type="range" min={1} max={10} value={minMentions}
               onChange={e => setMinMentions(Number(e.target.value))}
               className="w-full accent-cyan-400" />
      </div>

      <div>
        <div className="text-[11px] font-semibold text-slate-300 uppercase tracking-wider mb-2">Entitätstypen</div>
        <div className="space-y-1.5">
          {TYPE_OPTIONS.map(t => (
            <label key={t} className="flex items-center gap-2 text-sm group cursor-pointer">
              <input type="checkbox" checked={typesEnabled.has(t)} onChange={() => toggleType(t)}
                     className="accent-cyan-400" />
              <span className="w-3 h-3 rounded-full" style={{
                background: TYPE_COLORS[t],
                boxShadow: `0 0 8px ${TYPE_COLORS[t]}80`,
              }} />
              <span className="text-slate-300 group-hover:text-slate-100 transition">{t}</span>
            </label>
          ))}
        </div>
      </div>

      <div>
        <div className="text-[11px] font-semibold text-slate-300 uppercase tracking-wider mb-2">Farben nach</div>
        <div className="flex gap-1.5">
          {(["type", "community"] as ColourBy[]).map(opt => (
            <button key={opt} onClick={() => setColourBy(opt)}
                    className={"flex-1 px-2 py-1.5 text-xs rounded transition " +
                      (colourBy === opt
                        ? "bg-cyan-500/20 border border-cyan-400 text-cyan-200"
                        : "bg-slate-800/50 border border-slate-700 text-slate-400 hover:text-slate-200")}>
              {opt === "type" ? "Typ" : "Community"}
            </button>
          ))}
        </div>
      </div>

      <button onClick={load} disabled={loading}
              className="w-full px-3 py-2 text-sm rounded-lg bg-gradient-to-r from-cyan-500 to-blue-500 text-white font-semibold hover:from-cyan-400 hover:to-blue-400 shadow-[0_0_20px_rgba(34,211,238,0.3)] disabled:opacity-50 transition">
        {loading ? "Lädt…" : "Aktualisieren"}
      </button>

      {error && (
        <div className="text-xs text-rose-300 bg-rose-950/40 border border-rose-700/50 rounded p-2">{error}</div>
      )}

      {selected && (
        <div className="border-t border-slate-800 pt-4 space-y-2">
          <div className="text-[10px] uppercase tracking-wider text-slate-500">Ausgewählt</div>
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full shrink-0" style={{
              background: colourOf(selected),
              boxShadow: `0 0 10px ${colourOf(selected)}`,
            }} />
            <span className="font-bold text-slate-100">{selected.name}</span>
          </div>
          <div className="text-xs text-slate-400 font-mono">
            {selected.type} · {selected.mentions} Erwähnungen
            {selected.community_id && <> · {selected.community_id}</>}
          </div>
          <p className="text-sm text-slate-300 whitespace-pre-wrap leading-relaxed">{selected.description}</p>
          {selected.community_id && communityById[selected.community_id] && (
            <div className="mt-3 bg-slate-800/50 border border-slate-700/50 rounded p-2.5 text-xs">
              <div className="font-semibold text-cyan-300 mb-1">Community {selected.community_id}</div>
              <div className="text-slate-500 mb-1">Level {communityById[selected.community_id].level} · {communityById[selected.community_id].size} Mitglieder</div>
              <div className="text-slate-300 leading-relaxed">{communityById[selected.community_id].summary}</div>
            </div>
          )}
        </div>
      )}
    </aside>
  );
}


// ─── HTML tooltip ──────────────────────────────────────────────────────────
function NodeTooltip({ node, community, colour }: { node: FGNode; community: GraphCommunity | null; colour: string }) {
  if (node.x == null || node.y == null) return null;
  return (
    <div className="absolute z-20 pointer-events-none bottom-3 left-1/2 -translate-x-1/2
                    bg-slate-900/95 backdrop-blur-md border-2 rounded-lg shadow-2xl p-3 max-w-md"
         style={{ borderColor: colour, boxShadow: `0 0 20px ${colour}40` }}>
      <div className="flex items-center gap-2 mb-1">
        <span className="w-3 h-3 rounded-full" style={{ background: colour, boxShadow: `0 0 8px ${colour}` }} />
        <span className="font-bold text-slate-100">{node.name}</span>
        <span className="text-xs text-slate-500 font-mono ml-auto">{node.type}</span>
      </div>
      <div className="text-xs text-slate-400 mb-1.5">
        {node.mentions} Erwähnungen
        {community && <> · Community {community.id} ({community.size} Mitglieder)</>}
      </div>
      {node.description && (
        <p className="text-xs text-slate-300 leading-relaxed line-clamp-4">{node.description}</p>
      )}
    </div>
  );
}


// ─── Animated star background ──────────────────────────────────────────────
function StarField({ w, h }: { w: number; h: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    canvas.width = w; canvas.height = h;
    const stars = Array.from({ length: 120 }, () => ({
      x: Math.random() * w,
      y: Math.random() * h,
      r: Math.random() * 1.2 + 0.2,
      phase: Math.random() * Math.PI * 2,
      speed: 0.01 + Math.random() * 0.02,
    }));
    let raf = 0;
    let t = 0;
    const draw = () => {
      ctx.clearRect(0, 0, w, h);
      for (const s of stars) {
        const a = 0.3 + 0.5 * Math.abs(Math.sin(s.phase + t * s.speed));
        ctx.fillStyle = `rgba(180,220,255,${a})`;
        ctx.beginPath(); ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2); ctx.fill();
      }
      t++;
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [w, h]);
  return <canvas ref={canvasRef} className="absolute inset-0 pointer-events-none" style={{ width: w, height: h }} />;
}


// ─── SPARQL console (right panel) ──────────────────────────────────────────
const EXAMPLE_QUERIES: { label: string; sparql: string }[] = [
  {
    label: "Alle als CEO/Founder/Designer typisierte Personen",
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
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX apple: <http://uc5.butscher.cloud/apple#>
SELECT DISTINCT ?name WHERE {
  ?p rdf:type/rdfs:subClassOf* apple:Smartphone ; rdfs:label ?name .
}`,
  },
  {
    label: "Verteilung der Entitätstypen",
    sparql: `PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX apple: <http://uc5.butscher.cloud/apple#>
SELECT ?type (COUNT(?s) AS ?anzahl) WHERE {
  ?s a ?type .
  FILTER(STRSTARTS(STR(?type), "http://uc5.butscher.cloud/apple#"))
} GROUP BY ?type ORDER BY DESC(?anzahl)`,
  },
];

function SparqlConsole({ onResults, nodeIds }: {
  onResults: (matchedNodeIds: string[]) => void;
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
    setTranslating(true); setError(null);
    try {
      const r = await api.sparqlTranslate(nlQuery.trim());
      if (r.ok && r.sparql) setSparql(r.sparql);
      else setError(r.error || "Übersetzung fehlgeschlagen");
    } catch (e) { setError(String(e)); }
    finally { setTranslating(false); }
  };

  const execute = async () => {
    if (!sparql.trim()) return;
    setExecuting(true); setError(null); setResult(null);
    try {
      const r = await api.sparqlExecute(sparql.trim());
      if (!r.ok) { setError(r.error || "Fehler"); return; }
      setResult(r.result);
      // Highlight matching nodes on the graph by entity-URI
      const matched: string[] = [];
      const bindings = r.result?.results?.bindings || [];
      for (const b of bindings) {
        for (const v of Object.values(b) as any[]) {
          if (v?.type === "uri" && v.value.startsWith("http://uc5.butscher.cloud/apple#")) {
            const uri = v.value;
            // Find graph nodes whose id matches this URI. Our graph nodes' ids
            // come from UE3 entity_key (TYPE:normalised_name); the UE4 URIs
            // are PascalCase derivatives. Approximate match by name suffix.
            const lastPart = uri.split("#")[1].toLowerCase();
            for (const id of nodeIds) {
              const idNorm = id.split(":")[1]?.replace(/\s+/g, "").toLowerCase();
              if (idNorm && (idNorm === lastPart || lastPart.includes(idNorm) || idNorm.includes(lastPart))) {
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

  return (
    <aside className="w-[26rem] shrink-0 bg-slate-900/80 backdrop-blur-xl border-l border-cyan-500/20 flex flex-col">
      <div className="px-4 py-3 border-b border-slate-800 bg-gradient-to-r from-cyan-950/40 to-slate-900/40">
        <div className="text-[10px] uppercase tracking-[0.3em] text-cyan-400">UE4 · Konsole</div>
        <div className="font-bold text-slate-100">SPARQL Query</div>
      </div>

      <div className="px-4 py-3 space-y-3 overflow-y-auto flex-1">
        {/* NL → SPARQL */}
        <div>
          <label className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-1.5">
            Frage in natürlicher Sprache
          </label>
          <div className="flex gap-2">
            <input
              value={nlQuery}
              onChange={e => setNlQuery(e.target.value)}
              onKeyDown={e => e.key === "Enter" && translate()}
              placeholder="z.B. Wer sind die CEOs?"
              className="flex-1 px-3 py-2 text-sm rounded bg-slate-950/70 border border-slate-700 placeholder-slate-500 text-slate-100 focus:outline-none focus:border-cyan-500 transition"
            />
            <button onClick={translate} disabled={translating || !nlQuery.trim()}
                    className="px-3 py-2 text-xs rounded bg-cyan-500/20 border border-cyan-500/50 text-cyan-200 hover:bg-cyan-500/30 disabled:opacity-50 transition font-mono whitespace-nowrap">
              {translating ? "…" : "→ SPARQL"}
            </button>
          </div>
        </div>

        {/* Examples */}
        <div>
          <details className="text-xs">
            <summary className="cursor-pointer text-slate-400 hover:text-cyan-300 transition">
              Beispielqueries (3)
            </summary>
            <div className="mt-2 space-y-1">
              {EXAMPLE_QUERIES.map((ex, i) => (
                <button key={i} onClick={() => setSparql(ex.sparql)}
                        className="block w-full text-left px-2 py-1.5 rounded bg-slate-800/60 hover:bg-slate-800 border border-slate-700/50 hover:border-cyan-500/50 text-slate-300 hover:text-cyan-200 transition">
                  {ex.label}
                </button>
              ))}
            </div>
          </details>
        </div>

        {/* SPARQL editor */}
        <div>
          <label className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-1.5">
            SPARQL
          </label>
          <textarea
            value={sparql}
            onChange={e => setSparql(e.target.value)}
            placeholder="SELECT ?s WHERE { ?s a apple:CEO } …"
            spellCheck={false}
            className="w-full h-56 px-3 py-2 text-xs rounded bg-slate-950/80 border border-slate-700 text-cyan-100 font-mono leading-relaxed focus:outline-none focus:border-cyan-500 resize-none"
          />
        </div>

        <div className="flex gap-2">
          <button onClick={execute} disabled={executing || !sparql.trim()}
                  className="flex-1 px-3 py-2 text-sm rounded bg-gradient-to-r from-cyan-500 to-blue-500 text-white font-bold hover:from-cyan-400 hover:to-blue-400 shadow-[0_0_15px_rgba(34,211,238,0.4)] disabled:opacity-50 transition">
            {executing ? "Läuft…" : "▶ Ausführen"}
          </button>
          <button onClick={() => { setSparql(""); setResult(null); setError(null); onResults([]); }}
                  className="px-3 py-2 text-xs rounded bg-slate-800 border border-slate-700 text-slate-300 hover:text-slate-100 transition">
            Reset
          </button>
        </div>

        {error && (
          <div className="text-xs text-rose-300 bg-rose-950/40 border border-rose-700/50 rounded p-2 font-mono break-all">{error}</div>
        )}

        {result && (
          <ResultTable result={result} />
        )}
      </div>
    </aside>
  );
}


function ResultTable({ result }: { result: any }) {
  const headVars = result?.head?.vars || [];
  const bindings = result?.results?.bindings || [];
  if (!Array.isArray(bindings)) {
    // ASK results
    if (typeof result?.boolean === "boolean") {
      return (
        <div className="bg-slate-950/80 border border-slate-700 rounded p-2 text-sm">
          <span className="text-slate-400 mr-2">ASK:</span>
          <span className={result.boolean ? "text-emerald-300 font-bold" : "text-rose-300 font-bold"}>
            {String(result.boolean)}
          </span>
        </div>
      );
    }
    return <div className="text-xs text-slate-400">(kein Tabellenergebnis)</div>;
  }
  return (
    <div className="space-y-1.5">
      <div className="text-[11px] text-slate-400">
        <span className="text-cyan-300 font-mono">{bindings.length}</span> Treffer
      </div>
      <div className="overflow-x-auto bg-slate-950/80 border border-slate-700 rounded">
        <table className="text-xs w-full">
          <thead>
            <tr className="bg-slate-900/80">
              {headVars.map((v: string) => (
                <th key={v} className="text-left px-2 py-1.5 text-cyan-400 font-mono font-normal border-b border-slate-700">{v}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {bindings.slice(0, 100).map((row: any, i: number) => (
              <tr key={i} className="hover:bg-slate-900/50 transition">
                {headVars.map((v: string) => {
                  const val = row[v];
                  if (!val) return <td key={v} className="px-2 py-1 text-slate-600 border-b border-slate-800/50">—</td>;
                  const display = val.type === "uri"
                    ? val.value.split(/[/#]/).pop()
                    : val.value;
                  return (
                    <td key={v}
                        title={val.value}
                        className={"px-2 py-1 truncate max-w-[14rem] border-b border-slate-800/50 " +
                          (val.type === "uri" ? "text-cyan-200 font-mono" : "text-slate-200")}>
                      {display}
                    </td>
                  );
                })}
              </tr>
            ))}
            {bindings.length > 100 && (
              <tr><td colSpan={headVars.length} className="text-center text-slate-500 py-1.5">… {bindings.length - 100} weitere</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
