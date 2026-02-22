# backend/ontology_store.py
from __future__ import annotations
import logging
import re
from pathlib import Path

from rdflib import Graph, Literal, Namespace
from rdflib.namespace import RDF

PHIL = Namespace("http://hdm-stuttgart.de/phil/ont/")
_DEFAULT_TTL = Path("./data/ontology.ttl")


def _slug(text: str) -> str:
    """Sanitise text to a URI-safe slug (max 64 chars)."""
    return re.sub(r"[^a-zA-Z0-9_-]", "-", text.strip().lower())[:64]


class OntologyStore:
    def __init__(self, ttl_path: str | Path = _DEFAULT_TTL):
        self._path = Path(ttl_path)
        self._g = Graph()
        self._g.bind("phil", PHIL)
        if self._path.exists():
            self._g.parse(str(self._path), format="turtle")

    # ── Public API ─────────────────────────────────────────────────────────

    def add_mail_triples(
        self,
        mail_id: str,
        sender_name: str,
        sender_email: str,
        subject: str,
        entities: dict,
    ) -> None:
        """
        Persist mail + extracted entities as RDF triples.

        entities = {
          "persons": [...],
          "projects": [...],
          "deadlines": [...],    # strings (dates or descriptions)
          "action_items": [...],
        }
        """
        g = self._g
        mail_uri = PHIL[f"mail-{_slug(mail_id)}"]
        g.add((mail_uri, RDF.type, PHIL.Mail))
        g.add((mail_uri, PHIL.subject, Literal(subject)))

        # Sender
        sender_uri = PHIL[f"person-{_slug(sender_email or sender_name)}"]
        g.add((sender_uri, RDF.type, PHIL.Person))
        g.add((sender_uri, PHIL.name, Literal(sender_name)))
        if sender_email:
            g.add((sender_uri, PHIL.email, Literal(sender_email)))
        g.add((mail_uri, PHIL.sentBy, sender_uri))

        for name in entities.get("persons", []):
            p_uri = PHIL[f"person-{_slug(name)}"]
            g.add((p_uri, RDF.type, PHIL.Person))
            g.add((p_uri, PHIL.name, Literal(name)))
            g.add((mail_uri, PHIL.mentionsPerson, p_uri))

        for proj in entities.get("projects", []):
            proj_uri = PHIL[f"projekt-{_slug(proj)}"]
            g.add((proj_uri, RDF.type, PHIL.Projekt))
            g.add((proj_uri, PHIL.description, Literal(proj)))
            g.add((mail_uri, PHIL.relatedTo, proj_uri))

        for dl in entities.get("deadlines", []):
            dl_uri = PHIL[f"termin-{_slug(dl)}"]
            g.add((dl_uri, RDF.type, PHIL.Termin))
            g.add((dl_uri, PHIL.date, Literal(dl)))
            g.add((mail_uri, PHIL.hasDeadline, dl_uri))

        for action in entities.get("action_items", []):
            act_uri = PHIL[f"aufgabe-{_slug(action)}"]
            g.add((act_uri, RDF.type, PHIL.Aufgabe))
            g.add((act_uri, PHIL.description, Literal(action)))
            g.add((mail_uri, PHIL.requiresAction, act_uri))

        self._save()

    def get_all_entities(self) -> dict:
        """Return all entities for the /api/ontology/entities endpoint."""
        return {
            "persons": [{"name": n, "mail_count": c} for n, c in self._query_persons()],
            "projects": [{"description": p} for p in self._query_projects()],
            "tasks": [{"description": t} for t in self._query_tasks()],
            "deadlines": [{"date": d} for d in self._query_deadlines()],
        }

    def get_context_for_chat(self, query: str) -> str:
        """Build =WISSENSGRAPH= context block for Phil's chat prompt."""
        persons = self._query_persons()
        projects = self._query_projects()
        tasks = self._query_tasks()
        if not persons and not projects and not tasks:
            return ""
        lines = ["\n=== WISSENSGRAPH (strukturierte Verbindungen) ==="]
        if persons:
            lines.append(
                "  Personen: " + ", ".join(f"{n} ({c} Mails)" for n, c in persons[:5])
            )
        if projects:
            lines.append("  Projekte: " + ", ".join(projects[:5]))
        if tasks:
            lines.append("  Offene Aufgaben: " + "; ".join(tasks[:3]))
        return "\n".join(lines)

    def get_triples_for_mail(self, mail_id: str) -> list[dict]:
        """Return all triples where subject is the given mail URI."""
        mail_uri = PHIL[f"mail-{_slug(mail_id)}"]
        return [
            {"s": str(s), "p": str(p), "o": str(o)}
            for s, p, o in self._g.triples((mail_uri, None, None))
        ]

    # ── SPARQL helpers ─────────────────────────────────────────────────────

    def _query_persons(self) -> list[tuple[str, int]]:
        q = """
        PREFIX phil: <http://hdm-stuttgart.de/phil/ont/>
        SELECT ?name (COUNT(?mail) AS ?cnt)
        WHERE {
            ?mail a phil:Mail .
            { ?mail phil:mentionsPerson ?p } UNION { ?mail phil:sentBy ?p }
            ?p phil:name ?name .
        }
        GROUP BY ?name
        ORDER BY DESC(?cnt)
        """
        try:
            return [(str(row.name), int(row.cnt)) for row in self._g.query(q)]
        except Exception as exc:
            logging.warning(f"[Ontology] SPARQL persons: {exc}")
            return []

    def _query_projects(self) -> list[str]:
        q = """
        PREFIX phil: <http://hdm-stuttgart.de/phil/ont/>
        SELECT DISTINCT ?desc WHERE { ?p a phil:Projekt ; phil:description ?desc . }
        """
        try:
            return [str(row.desc) for row in self._g.query(q)]
        except Exception as exc:
            logging.warning(f"[Ontology] SPARQL projects: {exc}")
            return []

    def _query_tasks(self) -> list[str]:
        q = """
        PREFIX phil: <http://hdm-stuttgart.de/phil/ont/>
        SELECT DISTINCT ?desc WHERE { ?a a phil:Aufgabe ; phil:description ?desc . }
        """
        try:
            return [str(row.desc) for row in self._g.query(q)]
        except Exception as exc:
            logging.warning(f"[Ontology] SPARQL tasks: {exc}")
            return []

    def _query_deadlines(self) -> list[str]:
        q = """
        PREFIX phil: <http://hdm-stuttgart.de/phil/ont/>
        SELECT DISTINCT ?date WHERE { ?t a phil:Termin ; phil:date ?date . }
        ORDER BY ?date
        """
        try:
            return [str(row.date) for row in self._g.query(q)]
        except Exception as exc:
            logging.warning(f"[Ontology] SPARQL deadlines: {exc}")
            return []

    # ── Persistence ────────────────────────────────────────────────────────

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._g.serialize(str(self._path), format="turtle")
