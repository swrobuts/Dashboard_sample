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
  __radius?: number;
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
  const [minMentions, setMinMentions] = useState(1);
  const [search, setSearch] = useState("");
  const [typesEnabled, setTypesEnabled] = useState<Set<string>>(new Set(TYPE_OPTIONS));
  const [colourBy, setColourBy] = useState<ColourBy>("type");
  const [highlightedIds, setHighlightedIds] = useState<Set<string>>(new Set());
  const [sparqlOpen, setSparqlOpen] = useState(true);
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
    return { nodes, links };
  }, [data, search]);

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
        load={load}
        selected={selected}
        communityById={Object.fromEntries((data?.communities || []).map(c => [c.id, c]))}
        colourOf={colourOf}
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
            d3AlphaDecay={0.02}
            d3VelocityDecay={0.3}
            cooldownTicks={400}
            warmupTicks={60}
            enableNodeDrag
            enableZoomInteraction
            onNodeHover={(n) => setHovered(n)}
            onNodeClick={(n) => {
              setSelected(n);
              if (n.x != null && n.y != null) graphRef.current?.centerAt(n.x, n.y, 500);
            }}
            onBackgroundClick={() => setSelected(null)}
            // Restrained node rendering: filled disk sized by mentions,
            // accent ring only for hover/selection/SPARQL-highlight.
            nodeCanvasObjectMode={() => "replace"}
            nodeCanvasObject={(n, ctx, scale) => {
              const colour = colourOf(n);
              const baseR = 2 + Math.sqrt(n.mentions + 1) * 1.4;
              const isHovered = hovered?.id === n.id;
              const isSelected = selected?.id === n.id;
              const isHighlight = highlightedIds.has(n.id);
              const dim = isDimmed(n.id);
              const r = isHovered ? baseR * 1.25 : baseR;
              n.__radius = r;
              ctx.save();
              if (dim) ctx.globalAlpha = 0.18;
              // Single filled disk — no halo, no glow
              ctx.beginPath();
              ctx.arc(n.x!, n.y!, r, 0, Math.PI * 2);
              ctx.fillStyle = colour;
              ctx.fill();
              // 1-pixel accent ring for state — that's it
              if (isHovered || isSelected || isHighlight) {
                ctx.beginPath();
                ctx.arc(n.x!, n.y!, r + 2.5 / scale, 0, Math.PI * 2);
                ctx.strokeStyle = ACCENT;
                ctx.lineWidth = 1.2 / scale;
                ctx.stroke();
              }
              // Labels: always for the most-mentioned, on demand for the rest
              const showLabel = isHovered || isSelected || alwaysLabeled.has(n.id) || scale > 1.8;
              if (showLabel) {
                const fontSize = (isHovered ? 12 : 10) / scale;
                ctx.font = `${fontSize}px Inter, ui-sans-serif`;
                ctx.textAlign = "center";
                ctx.textBaseline = "top";
                const label = n.name.length > 32 ? n.name.slice(0, 30) + "…" : n.name;
                // Tight crisp halo on the label, in paper colour, so it reads
                // over edges without competing visually with the data.
                ctx.lineWidth = 3 / scale;
                ctx.strokeStyle = PAPER;
                ctx.strokeText(label, n.x!, n.y! + r + 3 / scale);
                ctx.fillStyle = TEXT_INK;
                ctx.fillText(label, n.x!, n.y! + r + 3 / scale);
              }
              ctx.restore();
            }}
            // Edges: 1px hairline. Hover-related darker. No particles.
            linkCanvasObjectMode={() => "replace"}
            linkCanvasObject={(l, ctx, scale) => {
              const src = l.source as FGNode;
              const tgt = l.target as FGNode;
              if (!src.x || !src.y || !tgt.x || !tgt.y) return;
              const involved = hovered != null && (src.id === hovered.id || tgt.id === hovered.id);
              const highlight = highlightedIds.size > 0 && (highlightedIds.has(src.id) && highlightedIds.has(tgt.id));
              const dim = (neighbourIds && !involved && !(neighbourIds.has(src.id) && neighbourIds.has(tgt.id)))
                       || (highlightedIds.size > 0 && !highlight && !(highlightedIds.has(src.id) || highlightedIds.has(tgt.id)));
              ctx.save();
              if (dim) ctx.globalAlpha = 0.16;
              ctx.strokeStyle = highlight ? ACCENT : (involved ? "#525252" : "#cfcbc3");
              ctx.lineWidth = (involved || highlight) ? 1 / scale : 0.5 / scale;
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
  load: () => void;
  selected: FGNode | null;
  communityById: Record<string, GraphCommunity>;
  colourOf: (n: FGNode) => string;
}) {
  const {
    data, loading, error, minMentions, setMinMentions, typesEnabled,
    toggleType, colourBy, setColourBy, load, selected, communityById, colourOf,
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

      {error && (
        <div className="mx-5 mb-4 text-[11px] p-2.5"
             style={{ border: `1px solid ${ACCENT}`, color: ACCENT }}>{error}</div>
      )}

      {selected && (
        <div className="px-5 py-5" style={{ borderTop: `1px solid ${RULE}` }}>
          <div className="text-[10px] uppercase tracking-[0.25em] mb-2" style={{ color: TEXT_MUTED }}>
            Ausgewählt
          </div>
          <div className="flex items-center gap-2 mb-1">
            <span className="w-2 h-2 rounded-full" style={{ background: colourOf(selected) }} />
            <span className="font-medium text-[15px]">{selected.name}</span>
          </div>
          <div className="text-[11px] font-mono" style={{ color: TEXT_MUTED }}>
            {selected.type} · {selected.mentions} Erwähnungen
            {selected.community_id && <> · {selected.community_id}</>}
          </div>
          <p className="text-[13px] mt-3 leading-relaxed whitespace-pre-wrap">{selected.description}</p>
          {selected.community_id && communityById[selected.community_id] && (
            <div className="mt-4 pt-4" style={{ borderTop: `1px solid ${RULE}` }}>
              <div className="text-[10px] uppercase tracking-[0.25em]" style={{ color: TEXT_MUTED }}>
                Community {selected.community_id}
              </div>
              <div className="text-[11px] mt-1 mb-2 font-mono" style={{ color: TEXT_MUTED }}>
                Level {communityById[selected.community_id].level} · {communityById[selected.community_id].size} Mitglieder
              </div>
              <p className="text-[12px] leading-relaxed">{communityById[selected.community_id].summary}</p>
            </div>
          )}
        </div>
      )}
    </aside>
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

        {result && <ResultTable result={result} />}
      </div>
    </aside>
  );
}


function ResultTable({ result }: { result: any }) {
  const headVars: string[] = result?.head?.vars || [];
  const bindings: any[] = result?.results?.bindings || [];
  if (!Array.isArray(bindings)) {
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
