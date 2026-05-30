"""GraphDB REST client for UE4 (Ontology-RAG).

Uses the standard SPARQL 1.1 endpoints exposed by GraphDB at
``/repositories/{repo}`` (read) and ``/repositories/{repo}/statements``
(write). Also wraps the repository management endpoints so the ingest
pipeline can create the repo on first run if it doesn't exist yet.

GraphDB Community can run without auth (default) or with RBAC enabled —
both modes are supported via the optional GRAPHDB_USER/PASSWORD env vars.
"""
from __future__ import annotations

import logging
from pathlib import Path

import httpx

from backend.config import get_settings

log = logging.getLogger(__name__)

# Where TTL files live in the repo (alongside Postgres/Neo4j migrations).
GRAPHDB_ASSETS_DIR = Path(__file__).resolve().parents[2] / "data" / "migrations" / "graphdb"


def _auth() -> tuple[str, str] | None:
    s = get_settings()
    if s.graphdb_user and s.graphdb_password:
        return (s.graphdb_user, s.graphdb_password)
    return None


def _base_url() -> str:
    return get_settings().graphdb_url.rstrip("/")


def _repo_url() -> str:
    s = get_settings()
    return f"{_base_url()}/repositories/{s.graphdb_repo}"


def _statements_url() -> str:
    return f"{_repo_url()}/statements"


# ── Health ─────────────────────────────────────────────────────────────────

def ping() -> bool:
    """True if the configured repository answers a trivial SPARQL ASK."""
    try:
        with httpx.Client(timeout=5.0, auth=_auth()) as c:
            r = c.get(
                _repo_url(),
                params={"query": "ASK { ?s ?p ?o }"},
                headers={"Accept": "application/sparql-results+json"},
            )
            return r.status_code == 200
    except Exception:  # noqa: BLE001
        return False


def list_repositories() -> list[str]:
    """Return repository IDs known to the GraphDB instance."""
    with httpx.Client(timeout=10.0, auth=_auth()) as c:
        r = c.get(f"{_base_url()}/rest/repositories",
                  headers={"Accept": "application/json"})
    r.raise_for_status()
    return [item["id"] for item in r.json()]


def repository_exists() -> bool:
    try:
        return get_settings().graphdb_repo in list_repositories()
    except Exception:  # noqa: BLE001
        return False


def ensure_repository(reasoning: str = "owl-horst-optimized") -> str:
    """Create the configured repository if absent. Returns a status string.

    ``reasoning`` picks the ruleset; ``owl-horst-optimized`` is a good
    balance (subclass + subproperty + inverse + transitive properties)
    without the full owl-max overhead. Other options: ``rdfsplus-optimized``,
    ``owl-max-optimized``, ``empty`` (no reasoning)."""
    s = get_settings()
    if repository_exists():
        return f"repo {s.graphdb_repo!r} already exists"
    # GraphDB Workbench creates repos via a multipart form with a config TTL.
    # We post a minimal SAIL config inline.
    config_ttl = _build_repo_config(s.graphdb_repo, reasoning)
    with httpx.Client(timeout=30.0, auth=_auth()) as c:
        r = c.post(
            f"{_base_url()}/rest/repositories",
            headers={"Content-Type": "application/x-turtle"},
            content=config_ttl,
        )
        if r.status_code == 400 and "already exist" in r.text.lower():
            return f"repo {s.graphdb_repo!r} already exists (race)"
        r.raise_for_status()
    return f"created repo {s.graphdb_repo!r} with reasoning={reasoning}"


def _build_repo_config(repo_id: str, ruleset: str) -> str:
    """Minimal SAIL-config TTL for an in-memory GraphDB repository with
    reasoning. For a teaching demo this is plenty; production would mount
    a persistent file storage."""
    return f"""@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix rep: <http://www.openrdf.org/config/repository#> .
@prefix sail: <http://www.openrdf.org/config/repository/sail#> .
@prefix sr: <http://www.openrdf.org/config/repository/sail#> .
@prefix sb: <http://www.openrdf.org/config/sail/base#> .
@prefix owlim: <http://www.ontotext.com/trree/owlim#> .

[] a rep:Repository ;
    rep:repositoryID "{repo_id}" ;
    rdfs:label "UC5 RAG Apple — Ontology-RAG repository" ;
    rep:repositoryImpl [
        rep:repositoryType "graphdb:SailRepository" ;
        sr:sailImpl [
            sail:sailType "graphdb:Sail" ;
            owlim:ruleset "{ruleset}" ;
            owlim:base-URL "http://uc5.butscher.cloud/apple#" ;
            owlim:defaultNS "" ;
            owlim:entity-index-size "10000000" ;
            owlim:enable-context-index "false" ;
            owlim:cache-memory "128m" ;
            owlim:query-timeout "30" ;
            owlim:query-limit-results "10000" ;
            owlim:throw-QueryEvaluationException-on-timeout "false"
        ]
    ] .
"""


# ── SPARQL ─────────────────────────────────────────────────────────────────

def select(sparql_query: str) -> dict:
    """Run a SPARQL SELECT/ASK/DESCRIBE/CONSTRUCT; return parsed JSON."""
    with httpx.Client(timeout=30.0, auth=_auth()) as c:
        r = c.post(
            _repo_url(),
            data={"query": sparql_query},
            headers={"Accept": "application/sparql-results+json"},
        )
    r.raise_for_status()
    return r.json()


def update(sparql_update: str) -> None:
    """Run a SPARQL 1.1 UPDATE (INSERT/DELETE/CLEAR/LOAD)."""
    with httpx.Client(timeout=60.0, auth=_auth()) as c:
        r = c.post(
            _statements_url(),
            data={"update": sparql_update},
            headers={"Accept": "application/json"},
        )
    r.raise_for_status()


def clear_all() -> None:
    """Wipe all triples in the repo (the ontology TTL must be re-uploaded)."""
    update("CLEAR ALL")


def upload_ttl(ttl_text: str, *, named_graph: str | None = None) -> None:
    """POST raw Turtle into the repository. Optional named-graph URI."""
    params = {}
    if named_graph:
        params["context"] = f"<{named_graph}>"
    with httpx.Client(timeout=60.0, auth=_auth()) as c:
        r = c.post(
            _statements_url(),
            params=params,
            content=ttl_text.encode("utf-8"),
            headers={"Content-Type": "text/turtle"},
        )
    r.raise_for_status()


def upload_ontology_file(path: Path) -> None:
    """Convenience: upload a .ttl file by path."""
    upload_ttl(path.read_text(encoding="utf-8"))


def count_triples() -> int:
    res = select("SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }")
    try:
        return int(res["results"]["bindings"][0]["n"]["value"])
    except (KeyError, IndexError, ValueError):
        return 0


# ── Migrations ─────────────────────────────────────────────────────────────

def apply_graphdb_setup() -> dict:
    """Create the repo if needed and upload every .ttl under
    data/migrations/graphdb/. Idempotent — re-runs simply re-upload (GraphDB
    deduplicates triples)."""
    info: dict = {}
    info["repo_status"] = ensure_repository()
    files = sorted(GRAPHDB_ASSETS_DIR.glob("*.ttl"))
    uploaded: list[str] = []
    for f in files:
        upload_ontology_file(f)
        uploaded.append(f.name)
        log.info("Uploaded GraphDB ontology %s", f.name)
    info["uploaded"] = uploaded
    info["triple_count"] = count_triples()
    return info


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    print(apply_graphdb_setup())
