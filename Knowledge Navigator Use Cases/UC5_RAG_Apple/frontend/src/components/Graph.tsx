import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D, { type ForceGraphMethods } from "react-force-graph-2d";
import { api, type GraphCommunity, type GraphEdge, type GraphNode, type GraphPayload } from "../api";

// Stable colour per entity type; communities are coloured below by hashing.
const TYPE_COLORS: Record<string, string> = {
  PERSON: "#2563eb",          // blue
  ORGANIZATION: "#059669",    // emerald
  PRODUCT: "#dc2626",         // red
  EVENT: "#9333ea",           // purple
  LOCATION: "#d97706",        // amber
  CONCEPT: "#0891b2",         // cyan
};

const TYPE_OPTIONS = ["PERSON", "ORGANIZATION", "PRODUCT", "EVENT", "LOCATION", "CONCEPT"];

interface FGNode extends GraphNode {
  // Force-graph mutates these to physics state, hence optional.
  x?: number; y?: number;
}

interface FGLink extends GraphEdge {
  source: string | FGNode;
  target: string | FGNode;
}


export function Graph() {
  const [data, setData] = useState<GraphPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<FGNode | null>(null);
  const [minMentions, setMinMentions] = useState(1);
  const [typesEnabled, setTypesEnabled] = useState<Set<string>>(new Set(TYPE_OPTIONS));
  const [colourBy, setColourBy] = useState<"type" | "community">("type");
  const graphRef = useRef<ForceGraphMethods<FGNode, FGLink> | undefined>(undefined);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ w: 800, h: 600 });

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const types = TYPE_OPTIONS.every(t => typesEnabled.has(t))
        ? undefined
        : Array.from(typesEnabled).join(",");
      const r = await api.graph({ min_mentions: minMentions, types });
      setData(r);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);   // eslint-disable-line react-hooks/exhaustive-deps

  // Resize the canvas to fit container.
  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver(([entry]) => {
      setSize({ w: entry.contentRect.width, h: entry.contentRect.height });
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  const graphData = useMemo(() => {
    if (!data) return { nodes: [], links: [] };
    const keep = new Set<string>(data.nodes.map(n => n.id));
    const links: FGLink[] = data.edges
      .filter(e => keep.has(e.source) && keep.has(e.target))
      .map(e => ({ ...e }));
    return { nodes: data.nodes.slice() as FGNode[], links };
  }, [data]);

  const communityColour = useMemo(() => {
    const m = new Map<string, string>();
    const palette = [
      "#2563eb", "#059669", "#dc2626", "#9333ea", "#d97706",
      "#0891b2", "#db2777", "#65a30d", "#7c3aed", "#0d9488",
      "#ea580c", "#4f46e5", "#16a34a", "#be185d", "#ca8a04",
    ];
    let i = 0;
    for (const c of data?.communities || []) {
      m.set(c.id, palette[i % palette.length]);
      i++;
    }
    return m;
  }, [data]);

  const colourOf = (n: FGNode): string => {
    if (colourBy === "community") {
      if (n.community_id) return communityColour.get(n.community_id) || "#94a3b8";
      return "#94a3b8";
    }
    return TYPE_COLORS[n.type] || "#94a3b8";
  };

  const toggleType = (t: string) => {
    setTypesEnabled(cur => {
      const next = new Set(cur);
      if (next.has(t)) next.delete(t); else next.add(t);
      return next;
    });
  };

  return (
    <div className="flex-1 flex min-h-0">
      <aside className="w-72 shrink-0 border-r border-slate-200 bg-white p-4 overflow-y-auto space-y-4">
        <div>
          <h3 className="font-semibold mb-2">Knowledge Graph</h3>
          {data ? (
            <div className="text-xs text-slate-500">
              {data.nodes.length} Entitäten · {graphData.links.length} Relationen · {data.communities.length} Communities
            </div>
          ) : (
            <div className="text-xs text-slate-400">Lädt…</div>
          )}
        </div>

        <div>
          <label className="text-xs font-medium text-slate-700 block mb-1">
            Min. Erwähnungen: {minMentions}
          </label>
          <input type="range" min={1} max={10} value={minMentions}
                 onChange={e => setMinMentions(Number(e.target.value))}
                 className="w-full" />
        </div>

        <div>
          <div className="text-xs font-medium text-slate-700 mb-2">Entitätstypen</div>
          <div className="space-y-1">
            {TYPE_OPTIONS.map(t => (
              <label key={t} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={typesEnabled.has(t)} onChange={() => toggleType(t)} />
                <span className="w-3 h-3 inline-block rounded-sm border border-slate-300" style={{ background: TYPE_COLORS[t] }} />
                <span>{t}</span>
              </label>
            ))}
          </div>
        </div>

        <div>
          <div className="text-xs font-medium text-slate-700 mb-2">Farben nach</div>
          <select value={colourBy} onChange={e => setColourBy(e.target.value as "type" | "community")}
                  className="w-full border border-slate-300 rounded px-2 py-1 text-sm bg-white">
            <option value="type">Entitätstyp</option>
            <option value="community">Community</option>
          </select>
        </div>

        <button onClick={load}
                disabled={loading}
                className="w-full px-3 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 disabled:bg-slate-300">
          {loading ? "Lädt…" : "Aktualisieren"}
        </button>

        {error && (
          <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded p-2">{error}</div>
        )}

        {selected && (
          <div className="mt-4 border-t border-slate-200 pt-3">
            <div className="text-xs uppercase tracking-wider text-slate-500">Knoten</div>
            <div className="font-bold mt-1">{selected.name}</div>
            <div className="text-xs text-slate-500 mb-2">
              <span className="inline-block w-2 h-2 rounded-full mr-1 align-middle" style={{ background: colourOf(selected) }} />
              {selected.type} · {selected.mentions} Erwähnungen
              {selected.community_id && <> · Community {selected.community_id}</>}
            </div>
            <p className="text-sm text-slate-700 whitespace-pre-wrap">{selected.description}</p>
            {selected.community_id && (
              <CommunityCard
                community={(data?.communities || []).find(c => c.id === selected.community_id) || null}
              />
            )}
          </div>
        )}
      </aside>

      <div ref={containerRef} className="flex-1 bg-slate-50 relative">
        <ForceGraph2D<FGNode, FGLink>
          ref={graphRef}
          width={size.w}
          height={size.h}
          graphData={graphData}
          nodeId="id"
          nodeLabel={(n: FGNode) => `${n.name} (${n.type})`}
          nodeRelSize={4}
          nodeVal={(n: FGNode) => Math.max(1, Math.log2(n.mentions + 1))}
          nodeColor={(n: FGNode) => colourOf(n)}
          linkColor={() => "rgba(100, 116, 139, 0.35)"}
          linkWidth={(l: FGLink) => Math.min(3, 0.5 + Math.log2((l.weight || 1) + 1))}
          linkDirectionalParticles={2}
          linkDirectionalParticleWidth={1.5}
          linkDirectionalParticleColor={() => "rgba(59, 130, 246, 0.6)"}
          onNodeClick={(n) => setSelected(n)}
          onBackgroundClick={() => setSelected(null)}
          cooldownTicks={120}
        />
      </div>
    </div>
  );
}


function CommunityCard({ community }: { community: GraphCommunity | null }) {
  if (!community) return null;
  return (
    <div className="mt-3 bg-slate-50 border border-slate-200 rounded p-2 text-xs">
      <div className="font-semibold mb-1">Community {community.id}</div>
      <div className="text-slate-500 mb-1">Level {community.level} · {community.size} Mitglieder</div>
      <div className="text-slate-700">{community.summary}</div>
    </div>
  );
}
