"""UE4 — Ontology-RAG retrieval against GraphDB.

Pipeline per query:
1. LLM gets the question + the Apple ontology summary and writes a SPARQL
   SELECT/CONSTRUCT query.
2. We execute it against GraphDB (which has OWL/RDFS reasoning enabled, so
   subclass and inverse inferences fire automatically).
3. Result bindings → "chunks" the answering LLM can use as facts. For each
   bound URI we optionally pull a couple of supporting UE1 chunks via name
   match so the final answer can cite the underlying Wikipedia text.

The SPARQL itself is shown in the trace — main didactic payoff of UE4.
"""
from __future__ import annotations

import json
import logging
import re
import time

from sqlalchemy import text

from backend.config import get_settings
from backend.data import graphdb_client
from backend.data.pg import session_scope
from backend.llm.factory import get_chat_llm
from backend.retrieval.base import Chunk, RetrievalResult, SourceRef

log = logging.getLogger(__name__)

# Compact ontology summary passed to the LLM in every query — full TTL is
# ~280 lines and too noisy in a prompt. This is the structural digest.
ONTOLOGY_SUMMARY = """\
PREFIX apple: <http://uc5.butscher.cloud/apple#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>

CLASSES (alle mit apple:-Präfix; Hierarchie via ⊑):
  Person ⊐ Employee ⊐ Executive ⊐ CEO
  Person ⊐ Founder
  Person ⊐ Designer
  Person ⊐ Engineer
  Organization ⊐ Company
  Organization ⊐ Shareholder
  Organization ⊐ Supplier
  Product ⊐ HardwareProduct ⊐ Computer ⊐ {Desktop, Notebook}
  Product ⊐ HardwareProduct ⊐ MobileDevice ⊐ {Smartphone, Tablet, Wearable}
  Product ⊐ SoftwareProduct ⊐ OperatingSystem
  Product ⊐ OnlineService
  Product ⊐ ProductFamily
  Event ⊐ Era
  Location, Concept

OBJECT PROPERTIES (Domain → Range):
  apple:foundedBy (Org → Person)        owl:inverseOf apple:founded
  apple:worksFor (Person → Org)         owl:inverseOf apple:hasEmployee
  apple:wasCEOOf (Person → Org)         owl:inverseOf apple:hasCEO
  apple:designedBy (Product → Person)
  apple:manufactures (Org → Product)    owl:inverseOf apple:manufacturedBy
  apple:partOfFamily (Product → ProductFamily, transitive)
  apple:successorOf (Product → Product) owl:inverseOf apple:predecessorOf
  apple:duringEra (Product → Era)
  apple:associatedWith (Symmetric, parent of most other relations)

DATA PROPERTIES:
  apple:foundedYear (Org → xsd:gYear)
  apple:releaseYear (Product → xsd:gYear)
  apple:role (Person → string)
  rdfs:label (multi-lingual labels)
  foaf:name (canonical name string)

KEY INSTANCES:
  apple:AppleInc  a apple:Company  (= dbpedia:Apple_Inc.)

REASONING enabled — Subklassen-Inferenz aktiv: rdf:type-Queries auf
apple:Manager bekommen automatisch alle apple:CEO-Instanzen mit. Auch
inverse Properties werden automatisch ergänzt.
"""

NL_TO_SPARQL_SYSTEM = (
    "Du bist ein SPARQL-1.1-Query-Generator für eine OWL-Ontologie über das "
    "Unternehmen Apple, die OWL-Horst-Reasoning aktiv hat (Subklassen-, "
    "Subproperty- und Inverse-Inferenz). Du bekommst die Ontologie-Struktur "
    "und eine deutsche Frage. Erzeuge eine SELECT-Query. "
    "Halte die Query knapp (max. 20 Zeilen). "
    "Antworte AUSSCHLIESSLICH mit dem SPARQL-Code, ohne Codefence, ohne "
    "Erklärung davor/danach."
)

NL_TO_SPARQL_TEMPLATE = """{ontology}

DATEN-REALITÄTSCHECK (wichtig für die Query-Strategie):
- Die meisten Beziehungen wurden ungenau extrahiert und liegen als
  ``apple:associatedWith`` (Catch-all) vor — spezifische Properties wie
  apple:wasCEOOf/foundedBy/manufactures sind nur sehr selten gesetzt.
- ROLLEN sind dagegen sauber als Klassen-Typen modelliert: eine Person mit
  CEO-Rolle hat ``rdf:type apple:CEO``. Eine Person mit Founder-Rolle hat
  ``rdf:type apple:Founder``. Subklassen-Inferenz ist aktiv — eine Query
  auf apple:Executive liefert auch apple:CEO automatisch.
- Die Firma "Apple" existiert als ``apple:Apple`` UND als ``apple:AppleInc``
  (owl:sameAs verlinkt). Beide funktionieren — nutze den, der für deine
  Anfrage weniger restriktiv ist.

QUERY-STRATEGIE-REGELN (in dieser Reihenfolge probieren):
1. FÜR „WER war/ist X-Rolle" (CEO, Founder, Designer, etc.):
     ?p rdf:type/rdfs:subClassOf* apple:CEO ;
        rdfs:label ?label .
   NICHT ?p apple:wasCEOOf — die Property ist im Daten kaum vorhanden.

2. FÜR „WAS gehört zu Apple" (Produkte, Personen, Orte):
     { ?x apple:associatedWith apple:Apple } UNION
     { apple:Apple apple:associatedWith ?x }
     ?x rdf:type ?t ; rdfs:label ?label .
     FILTER (?t = apple:Product || ?t = apple:Person || ...)

3. FÜR Typ-Fragen ("welche Produkte/Personen sind erwähnt"):
     ?x rdf:type/rdfs:subClassOf* apple:Product ;
        rdfs:label ?label .

4. IMMER:
   - rdfs:label für lesbare Namen
   - LIMIT 30 am Ende
   - PREFIX-Block am Anfang nicht vergessen (apple, rdf, rdfs, foaf, owl)

Frage: {query}

SPARQL:"""


class OntologyRAG:
    name = "ue4"

    def __init__(self, llm_provider: str = "gemini") -> None:
        self._chat = get_chat_llm(llm_provider)
        self._llm_provider = llm_provider

    def retrieve(self, query: str, k: int | None = None) -> RetrievalResult:
        settings = get_settings()
        k = k or settings.ue4_top_k_results

        # ── Phase 1: NL → SPARQL ──
        t0 = time.perf_counter()
        sparql = self._generate_sparql(query)
        sparql_gen_ms = (time.perf_counter() - t0) * 1000

        # ── Phase 2: execute against GraphDB ──
        bindings: list[dict] = []
        sparql_err: str | None = None
        t0 = time.perf_counter()
        try:
            result = graphdb_client.select(sparql)
            for b in (result.get("results", {}).get("bindings", []))[:k]:
                row = {k_: v["value"] for k_, v in b.items()}
                bindings.append(row)
        except Exception as exc:  # noqa: BLE001
            sparql_err = str(exc)[:200]
            log.warning("SPARQL execution failed: %s", sparql_err)
        sparql_exec_ms = (time.perf_counter() - t0) * 1000

        # ── Phase 3: turn bindings into chunks + supplementary text chunks ──
        chunks, sources = self._bindings_to_chunks(bindings)

        trace = {
            "strategy": self.name,
            "llm_provider": self._llm_provider,
            "k": k,
            "sparql": sparql,
            "sparql_err": sparql_err,
            "binding_count": len(bindings),
            "first_bindings": bindings[:5],
            "sparql_gen_ms": round(sparql_gen_ms, 1),
            "sparql_exec_ms": round(sparql_exec_ms, 1),
            "chunk_count": len(chunks),
        }
        return RetrievalResult(chunks=chunks, sources=sources, trace=trace)

    # ── internals ──────────────────────────────────────────────────────────

    def _generate_sparql(self, query: str) -> str:
        prompt = NL_TO_SPARQL_TEMPLATE.format(
            ontology=ONTOLOGY_SUMMARY, query=query,
        )
        try:
            raw, _u = self._chat.generate(NL_TO_SPARQL_SYSTEM, prompt)
        except Exception as exc:  # noqa: BLE001
            log.warning("SPARQL generation LLM failed: %s", exc)
            return ""
        sparql = _strip_codefence(raw or "")
        # Defensive: many models forget to repeat the PREFIX block even when
        # we put it in the ontology summary. Auto-prepend any prefix we
        # actually use that's missing from the query.
        return _ensure_prefixes(sparql)

    def _bindings_to_chunks(
        self, bindings: list[dict],
    ) -> tuple[list[Chunk], list[SourceRef]]:
        """Format SPARQL bindings as readable chunks. Also pull 1-2 UE1
        chunks per distinct entity name found in the bindings, so the final
        answering LLM has both the structured tripel-fact AND supporting
        natural-language context."""
        if not bindings:
            return [], []

        # Build a primary "facts" chunk listing the bindings — that's the
        # core evidence the answering LLM uses.
        lines = ["Strukturierte Fakten aus dem Knowledge Graph:"]
        for i, b in enumerate(bindings, start=1):
            parts = [f"{k}={v}" for k, v in b.items()]
            lines.append(f"  {i}. {' | '.join(parts)}")
        facts_chunk = Chunk(
            text="\n".join(lines),
            section_path="UE4 SPARQL-Ergebnis",
            chunk_id=None,
        )
        chunks: list[Chunk] = [facts_chunk]

        # Collect candidate names (any binding value that's not a URI and
        # has reasonable length).
        names: list[str] = []
        for b in bindings:
            for v in b.values():
                if not isinstance(v, str):
                    continue
                if v.startswith("http"):
                    continue
                v = v.strip()
                if 2 <= len(v) <= 80 and v not in names:
                    names.append(v)
                if len(names) >= 10:
                    break
            if len(names) >= 10:
                break

        # Pull supplementary UE1 chunks for those names.
        settings = get_settings()
        cap = settings.ue4_max_chunks_per_entity * 4  # global cap on extras
        if names:
            params: dict[str, object] = {"cap": cap}
            ilike_conds = []
            for i, n in enumerate(names):
                params[f"n{i}"] = f"%{n}%"
                ilike_conds.append(f"c.text ILIKE :n{i}")
            with session_scope() as session:
                rows = session.execute(
                    text(
                        f"SELECT c.id, s.path AS section, c.text "
                        f"FROM ue1.chunk c LEFT JOIN clean.section s ON s.id = c.section_id "
                        f"WHERE {' OR '.join(ilike_conds)} "
                        f"ORDER BY c.id LIMIT :cap"
                    ),
                    params,
                ).mappings().all()
            for r in rows:
                chunks.append(Chunk(
                    text=r["text"], section_path=r["section"], chunk_id=int(r["id"]),
                ))

        sources = [
            SourceRef(
                chunk_id=c.chunk_id, section_path=c.section_path,
                text=c.text, distance=None,
            )
            for c in chunks
        ]
        return chunks, sources


def _strip_codefence(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()


# Standard prefixes our ontology uses. Auto-prepended to LLM-generated SPARQL
# if missing — Gemini sometimes forgets them despite the instruction.
_KNOWN_PREFIXES = {
    "apple":  "http://uc5.butscher.cloud/apple#",
    "rdf":    "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs":   "http://www.w3.org/2000/01/rdf-schema#",
    "owl":    "http://www.w3.org/2002/07/owl#",
    "foaf":   "http://xmlns.com/foaf/0.1/",
    "schema": "http://schema.org/",
    "xsd":    "http://www.w3.org/2001/XMLSchema#",
    "dbo":    "http://dbpedia.org/ontology/",
    "dbr":    "http://dbpedia.org/resource/",
}


def _ensure_prefixes(sparql: str) -> str:
    """Prepend PREFIX declarations for any of the known prefixes that
    appear in the query body but aren't already declared at the top.
    Without this, even a perfect SELECT trips GraphDB with HTTP 400."""
    if not sparql:
        return sparql
    head_lower = sparql.lower()
    missing: list[str] = []
    for prefix, uri in _KNOWN_PREFIXES.items():
        used = re.search(rf"(?<![A-Za-z0-9_]){prefix}:", sparql)
        if not used:
            continue
        declared = re.search(
            rf"prefix\s+{prefix}\s*:",
            head_lower,
        )
        if not declared:
            missing.append(f"PREFIX {prefix}: <{uri}>")
    if not missing:
        return sparql
    return "\n".join(missing) + "\n" + sparql
