"""UE3 ingest: build a knowledge graph from the UE1 chunks.

Pipeline:

1. For every ue1.chunk, ask Gemini to extract entities (PERSON, ORGANIZATION,
   PRODUCT, EVENT, LOCATION, CONCEPT) and relations between them.
2. Resolve entities to canonical "{type}:{normalized_name}" keys so
   "Steve Jobs" and "Jobs" land on the same node.
3. Write Entity nodes, MENTIONS edges (chunk → entity) and RELATED_TO edges
   (entity → entity) into Neo4j.
4. Compute communities via networkx greedy modularity on the Entity graph.
5. For each community ask Gemini for a 2-sentence summary, embed it, store
   in ue3.community_summary. Also store per-entity descriptions with
   embeddings in ue3.entity_summary.
6. Write back MENTIONS-counted mention_count per entity so the UI can size
   nodes by importance.

This is the most LLM-heavy part of the project: ~130 extraction calls +
~5–15 community summary calls. Cost in the cents range, runtime 2–5 min.
"""
from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import networkx as nx
from sqlalchemy import text

from backend.config import get_settings
from backend.data import repo
from backend.data.neo4j_client import neo4j_session
from backend.data.pg import session_scope
from backend.llm.factory import get_chat_llm, get_embedding_llm

log = logging.getLogger(__name__)

VALID_TYPES = {"PERSON", "ORGANIZATION", "PRODUCT", "EVENT", "LOCATION", "CONCEPT"}

EXTRACTION_SYSTEM = (
    "Du bist ein präziser Named-Entity- und Relations-Extraktor für ein "
    "Knowledge-Graph-System. Du bekommst einen Textauszug aus dem deutschen "
    "Wikipedia-Artikel über Apple. Extrahiere ausschließlich Entitäten und "
    "Relationen, die im Text wörtlich oder klar erkennbar erwähnt werden. "
    "Keine Halluzinationen, kein Allgemeinwissen. "
    "Typen: PERSON, ORGANIZATION, PRODUCT, EVENT, LOCATION, CONCEPT. "
    "Antworte AUSSCHLIESSLICH mit gültigem JSON, ohne Codefence."
)

EXTRACTION_TEMPLATE = """Auszug:
\"\"\"
{chunk_text}
\"\"\"

JSON-Schema:
{{
  "entities": [
    {{"name": "Eigenname wie im Text", "type": "PERSON|ORGANIZATION|PRODUCT|EVENT|LOCATION|CONCEPT", "description": "1 Satz, ausschließlich basierend auf dem Auszug"}}
  ],
  "relations": [
    {{"source": "Name aus entities", "target": "Name aus entities", "type": "kurze Verb-Phrase, z.B. GRUENDET, ARBEITET_FUER, ERSCHIEN_AM", "evidence": "knappes Zitat aus dem Auszug"}}
  ]
}}

Antworte nur mit dem JSON-Objekt."""

COMMUNITY_SYSTEM = (
    "Du beschreibst die gemeinsame Thematik einer Gruppe verwandter Entitäten "
    "aus dem deutschen Wikipedia-Artikel über Apple. Antworte in höchstens "
    "zwei Sätzen, faktenorientiert."
)


@dataclass
class ExtractedEntity:
    name: str
    type: str
    description: str


@dataclass
class ExtractedRelation:
    source: str  # entity name from same chunk
    target: str
    type: str
    evidence: str


@dataclass
class ChunkExtraction:
    chunk_id: int
    entities: list[ExtractedEntity] = field(default_factory=list)
    relations: list[ExtractedRelation] = field(default_factory=list)


@dataclass
class UE3IngestStats:
    chunks_processed: int
    entities_unique: int
    relations_unique: int
    communities: int
    llm_calls: int
    duration_ms: float


# ── parsing ────────────────────────────────────────────────────────────────

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json_object(text_: str) -> dict | None:
    if not text_:
        return None
    cleaned = text_.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    m = _JSON_OBJECT_RE.search(cleaned)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def parse_extraction(raw: str, chunk_id: int) -> ChunkExtraction:
    """Robust parse of the LLM extraction response."""
    out = ChunkExtraction(chunk_id=chunk_id)
    obj = _extract_json_object(raw)
    if not obj:
        return out
    for e in (obj.get("entities") or []):
        name = str(e.get("name") or "").strip()
        typ = str(e.get("type") or "").strip().upper()
        desc = str(e.get("description") or "").strip()
        if not name or typ not in VALID_TYPES:
            continue
        out.entities.append(ExtractedEntity(name=name[:200], type=typ, description=desc[:400]))
    name_set = {e.name for e in out.entities}
    for r in (obj.get("relations") or []):
        src = str(r.get("source") or "").strip()
        tgt = str(r.get("target") or "").strip()
        typ = str(r.get("type") or "").strip().upper().replace(" ", "_")
        ev = str(r.get("evidence") or "").strip()
        if not src or not tgt or src == tgt or not typ:
            continue
        # Only keep relations where both endpoints were also extracted as
        # entities in the same chunk (otherwise we'd dangling-link).
        if src not in name_set or tgt not in name_set:
            continue
        out.relations.append(ExtractedRelation(source=src[:200], target=tgt[:200], type=typ[:60], evidence=ev[:400]))
    return out


# ── entity resolution ─────────────────────────────────────────────────────

_PUNCT_RE = re.compile(r"[^\w\s-]", re.UNICODE)


def normalize_entity_name(name: str) -> str:
    """Lowercase, strip diacritics, drop punctuation, collapse whitespace."""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = _PUNCT_RE.sub("", s.lower())
    return " ".join(s.split())


def entity_key(name: str, type_: str) -> str:
    return f"{type_}:{normalize_entity_name(name)}"


# ── extraction loop ───────────────────────────────────────────────────────

def _load_chunks() -> list[tuple[int, str, str | None]]:
    """Pull (chunk_id, text, section_path) for every ue1 chunk."""
    with session_scope() as session:
        rows = session.execute(
            text(
                "SELECT c.id, c.text, s.path "
                "FROM ue1.chunk c LEFT JOIN clean.section s ON s.id = c.section_id "
                "ORDER BY c.id"
            )
        ).all()
    return [(int(r[0]), r[1], r[2]) for r in rows]


def _extract_one(chat, chunk_text: str, chunk_id: int) -> tuple[ChunkExtraction, int]:
    """Run the extraction LLM call for one chunk. Returns (extraction, calls)."""
    try:
        raw, _usage = chat.generate(EXTRACTION_SYSTEM, EXTRACTION_TEMPLATE.format(chunk_text=chunk_text))
    except Exception as exc:  # noqa: BLE001
        log.warning("Extraction failed for chunk %d: %s", chunk_id, exc)
        return ChunkExtraction(chunk_id=chunk_id), 1
    return parse_extraction(raw, chunk_id), 1


# ── Neo4j writeback ───────────────────────────────────────────────────────

def _wipe_neo4j() -> None:
    with neo4j_session() as session:
        session.run("MATCH (n) WHERE NOT n:Migration DETACH DELETE n").consume()


def _write_to_neo4j(
    chunk_rows: list[tuple[int, str, str | None]],
    extractions: list[ChunkExtraction],
    entity_descriptions: dict[str, dict],
) -> None:
    """Write Chunk, Entity, MENTIONS and RELATED_TO into Neo4j in batches."""
    with neo4j_session() as session:
        # Chunks
        session.run(
            "UNWIND $rows AS r "
            "MERGE (c:Chunk {id: r.id}) "
            "SET c.text = r.text, c.section_path = r.section_path",
            rows=[{"id": cid, "text": txt or "", "section_path": sp or ""}
                  for cid, txt, sp in chunk_rows],
        ).consume()

        # Entities
        entity_rows = [
            {
                "key": k,
                "name": v["name"],
                "type": v["type"],
                "description": v["description"],
            }
            for k, v in entity_descriptions.items()
        ]
        session.run(
            "UNWIND $rows AS r "
            "MERGE (e:Entity {id: r.key}) "
            "SET e.name = r.name, e.type = r.type, e.description = r.description",
            rows=entity_rows,
        ).consume()

        # MENTIONS edges
        mentions_rows = []
        for ext in extractions:
            for e in ext.entities:
                mentions_rows.append({"cid": ext.chunk_id, "ekey": entity_key(e.name, e.type)})
        if mentions_rows:
            session.run(
                "UNWIND $rows AS r "
                "MATCH (c:Chunk {id: r.cid}) "
                "MATCH (e:Entity {id: r.ekey}) "
                "MERGE (c)-[:MENTIONS]->(e)",
                rows=mentions_rows,
            ).consume()

        # RELATED_TO edges (undirected semantically, stored directed src→tgt;
        # at query time we read both directions).
        rel_rows = []
        for ext in extractions:
            name_to_type = {e.name: e.type for e in ext.entities}
            for r in ext.relations:
                src_type = name_to_type.get(r.source)
                tgt_type = name_to_type.get(r.target)
                if not src_type or not tgt_type:
                    continue
                rel_rows.append({
                    "src": entity_key(r.source, src_type),
                    "tgt": entity_key(r.target, tgt_type),
                    "type": r.type,
                    "ev": r.evidence,
                })
        if rel_rows:
            session.run(
                "UNWIND $rows AS r "
                "MATCH (a:Entity {id: r.src}) "
                "MATCH (b:Entity {id: r.tgt}) "
                "MERGE (a)-[rel:RELATED_TO {type: r.type}]->(b) "
                "ON CREATE SET rel.weight = 1, rel.evidence = r.ev "
                "ON MATCH SET rel.weight = rel.weight + 1",
                rows=rel_rows,
            ).consume()


# ── community detection (NetworkX greedy modularity) ──────────────────────

def _build_networkx_graph(entity_descriptions: dict[str, dict],
                          relations: list[tuple[str, str, int]]) -> nx.Graph:
    g = nx.Graph()
    for k in entity_descriptions:
        g.add_node(k)
    for src, tgt, w in relations:
        if src == tgt:
            continue
        if g.has_edge(src, tgt):
            g[src][tgt]["weight"] = g[src][tgt].get("weight", 1) + w
        else:
            g.add_edge(src, tgt, weight=w)
    return g


def _detect_communities(g: nx.Graph) -> list[set[str]]:
    if g.number_of_nodes() == 0:
        return []
    # greedy_modularity_communities handles disconnected graphs by treating
    # each component independently; small components become their own
    # community. weight='weight' uses the RELATED_TO co-occurrence count.
    try:
        comms = list(nx.community.greedy_modularity_communities(g, weight="weight"))
    except Exception as exc:  # noqa: BLE001
        log.warning("Community detection failed (%s) — falling back to connected components", exc)
        comms = [set(c) for c in nx.connected_components(g)]
    return [set(c) for c in comms]


def _community_summary(chat, member_descriptions: list[tuple[str, str, str]]) -> str:
    """Ask Gemini to summarise a community. ``member_descriptions`` items are
    (name, type, description)."""
    if not member_descriptions:
        return ""
    lines = [f"- {n} ({t}): {d}" for n, t, d in member_descriptions[:20]]
    prompt = (
        "Entitäten in dieser Gruppe:\n" + "\n".join(lines) + "\n\n"
        "Welche gemeinsame Thematik verbindet diese Entitäten im Apple-Kontext? "
        "Maximal zwei Sätze."
    )
    try:
        answer, _ = chat.generate(COMMUNITY_SYSTEM, prompt)
    except Exception as exc:  # noqa: BLE001
        log.warning("Community summary LLM failed: %s", exc)
        return ", ".join(n for n, _, _ in member_descriptions[:8])
    return (answer or "").strip()[:1000]


# ── main ingest ───────────────────────────────────────────────────────────

def run_ue3_ingest(force: bool = False) -> UE3IngestStats:
    settings = get_settings()
    t0 = time.perf_counter()

    chunk_rows = _load_chunks()
    if not chunk_rows:
        raise RuntimeError("UE3 ingest: no UE1 chunks found — run UE1 ingest first.")

    if not force:
        with session_scope() as session:
            if repo.ue3_entity_count(session) > 0:
                log.info("UE3 ingest: already populated — skipping (use force to rebuild)")
                return UE3IngestStats(
                    chunks_processed=0,
                    entities_unique=repo.ue3_entity_count(session),
                    relations_unique=0,
                    communities=repo.ue3_community_count(session),
                    llm_calls=0,
                    duration_ms=(time.perf_counter() - t0) * 1000,
                )

    chat = get_chat_llm("gemini")
    embedder = get_embedding_llm()

    log.info("UE3 ingest: extracting entities from %d chunks", len(chunk_rows))
    extractions: list[ChunkExtraction] = []
    llm_calls = 0
    for cid, txt, _path in chunk_rows:
        if not (txt or "").strip():
            extractions.append(ChunkExtraction(chunk_id=cid))
            continue
        ext, calls = _extract_one(chat, txt, cid)
        llm_calls += calls
        extractions.append(ext)
        if len(extractions) % 25 == 0:
            log.info("  extracted %d/%d chunks (%d LLM calls so far)",
                     len(extractions), len(chunk_rows), llm_calls)

    # ── Resolve entities to canonical keys; aggregate descriptions ──
    entity_descriptions: dict[str, dict] = {}
    mention_counter: Counter[str] = Counter()
    for ext in extractions:
        for e in ext.entities:
            k = entity_key(e.name, e.type)
            mention_counter[k] += 1
            existing = entity_descriptions.get(k)
            if existing is None:
                entity_descriptions[k] = {
                    "name": e.name,
                    "type": e.type,
                    "description": e.description,
                }
            elif len(e.description) > len(existing["description"]):
                existing["description"] = e.description

    # Co-occurrence relation list (sum weights across chunks)
    rel_weights: defaultdict[tuple[str, str], int] = defaultdict(int)
    for ext in extractions:
        name_to_type = {e.name: e.type for e in ext.entities}
        for r in ext.relations:
            st = name_to_type.get(r.source)
            tt = name_to_type.get(r.target)
            if not st or not tt:
                continue
            a, b = entity_key(r.source, st), entity_key(r.target, tt)
            if a == b:
                continue
            pair = (a, b) if a < b else (b, a)
            rel_weights[pair] += 1
    relations_unique = list((a, b, w) for (a, b), w in rel_weights.items())
    log.info("UE3 ingest: %d unique entities, %d unique relations",
             len(entity_descriptions), len(relations_unique))

    # ── Write Neo4j (wipe first when forcing) ──
    if force:
        _wipe_neo4j()
    _write_to_neo4j(chunk_rows, extractions, entity_descriptions)

    # ── Community detection ──
    g = _build_networkx_graph(entity_descriptions, relations_unique)
    communities = _detect_communities(g)
    log.info("UE3 ingest: %d communities detected", len(communities))

    # ── Per-entity embeddings ──
    BATCH = 100
    entity_keys = list(entity_descriptions.keys())
    entity_embed_texts = [
        f"{entity_descriptions[k]['type']}: {entity_descriptions[k]['name']}. "
        f"{entity_descriptions[k]['description']}"
        for k in entity_keys
    ]
    entity_embeddings: list[list[float]] = []
    for i in range(0, len(entity_embed_texts), BATCH):
        entity_embeddings.extend(embedder.embed(entity_embed_texts[i:i + BATCH]))

    # ── Per-community LLM summaries + embeddings ──
    community_summaries: list[tuple[str, int, list[str], str]] = []
    for idx, members in enumerate(communities):
        sorted_members = sorted(members, key=lambda k: -mention_counter[k])
        member_descs = [
            (entity_descriptions[k]["name"],
             entity_descriptions[k]["type"],
             entity_descriptions[k]["description"])
            for k in sorted_members
        ]
        summary = _community_summary(chat, member_descs)
        llm_calls += 1
        community_summaries.append((f"c{idx:03d}", 0, sorted_members, summary))

    community_embeddings: list[list[float]] = []
    sum_texts = [s[3] or "(leer)" for s in community_summaries]
    for i in range(0, len(sum_texts), BATCH):
        community_embeddings.extend(embedder.embed(sum_texts[i:i + BATCH]))

    # ── Write back ue3.entity_summary + ue3.community_summary ──
    with session_scope() as session:
        repo.delete_ue3_summaries(session)
    with session_scope() as session:
        for k, emb in zip(entity_keys, entity_embeddings):
            d = entity_descriptions[k]
            repo.upsert_entity_summary(
                session,
                entity_key=k, name=d["name"], type_=d["type"],
                description=d["description"],
                mention_count=mention_counter[k],
                embedding=emb,
            )
        for (cid, lvl, members, summary), emb in zip(community_summaries, community_embeddings):
            repo.upsert_community_summary(
                session,
                community_id=cid, level=lvl,
                size=len(members), summary=summary,
                entity_keys=members, embedding=emb,
            )

    # ── Stamp community membership back into Neo4j ──
    with neo4j_session() as session:
        for cid, lvl, members, summary in community_summaries:
            session.run(
                "MERGE (com:Community {id: $id}) "
                "SET com.level = $lvl, com.size = $sz, com.summary = $sum",
                id=cid, lvl=lvl, sz=len(members), sum=summary,
            ).consume()
            if members:
                session.run(
                    "MATCH (com:Community {id: $id}) "
                    "WITH com UNWIND $keys AS k "
                    "MATCH (e:Entity {id: k}) "
                    "MERGE (e)-[:IN_COMMUNITY]->(com)",
                    id=cid, keys=list(members),
                ).consume()

    duration_ms = (time.perf_counter() - t0) * 1000
    log.info("UE3 ingest: done in %.1f ms with %d LLM calls", duration_ms, llm_calls)
    return UE3IngestStats(
        chunks_processed=len(chunk_rows),
        entities_unique=len(entity_descriptions),
        relations_unique=len(relations_unique),
        communities=len(communities),
        llm_calls=llm_calls,
        duration_ms=duration_ms,
    )
