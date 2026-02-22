# Attachments + Ontologie — Design

**Datum:** 2026-02-22
**Feature:** PDF/DOCX-Anhang-Verarbeitung + Mail-Domänen-Ontologie mit SPARQL-Integration

---

## Ziel

Zwei eng verzahnte Erweiterungen für PHIL:

1. **Anhang-Pipeline** — PDF- und DOCX-Anhänge werden beim Triage extrahiert, zusammengefasst, in ChromaDB indexiert und fließen in die Ontologie ein.
2. **Mail-Domänen-Ontologie** — aus Mail-Inhalt und Anhängen extrahiert Claude strukturierte Entitäten (Personen, Projekte, Termine, Aufgaben), die als RDF-Tripel in RDFLib persistiert werden. Phil nutzt SPARQL-Abfragen als zweite Kontext-Quelle im Chat.

---

## Architektur

```
Mail eingeht (Exchange)
    │
    ├─► Anhang vorhanden? ──► pdfplumber / python-docx
    │                              │
    │                         Text-Extraktion
    │                              │
    │                         Claude: Zusammenfassung
    │                              │
    ▼                              ▼
POST /api/analyze ◄─── Mail-Text + Anhang-Snippet (2.000 Zeichen)
    │
    ▼
Claude: Triage (Kategorie, Priorität, Zusammenfassung)
    │
    ├─► ChromaDB: index_mail()        ← wie bisher
    ├─► ChromaDB: index_attachment()  ← NEU, doc_type=attachment
    │
    ├─► Claude: Entity-Extraktion (JSON)
    │   {persons, projects, deadlines, action_items}
    │
    ▼
RDFLib OntologyStore: add_mail_triples()
    ├─► data/ontology.ttl (persistent)
    └─► phil:Mail ──mentionsPerson──► phil:Person
                  ──relatedToProject──► phil:Projekt
                  ──hasDeadline──────► phil:Termin
                  ──requiresAction───► phil:Aufgabe

Phil-Chat:
    ├─► ChromaDB semantic search  →  "=== MAILHISTORIE ==="
    ├─► SPARQL structured search  →  "=== WISSENSGRAPH ==="
    └─► Beide als Kontext an Claude claude-opus-4-6
```

---

## Ontologie-Schema

Datei: `data/ontology.ttl`
Prefix: `phil: <http://hdm-stuttgart.de/phil/ont/>`

### Klassen

| Klasse | Beschreibung |
|---|---|
| `phil:Mail` | Eine E-Mail |
| `phil:Person` | Absender oder erwähnte Person |
| `phil:Projekt` | Erwähntes Projekt / Vorhaben / Antrag |
| `phil:Termin` | Erwähntes Datum / Deadline |
| `phil:Aufgabe` | Geforderter Action Item |
| `phil:Anhang` | PDF- oder DOCX-Anhang |

### Properties

| Property | Domain | Range |
|---|---|---|
| `phil:sentBy` | Mail | Person |
| `phil:mentionsPerson` | Mail | Person |
| `phil:relatedTo` | Mail | Projekt |
| `phil:hasDeadline` | Mail | Termin |
| `phil:requiresAction` | Mail | Aufgabe |
| `phil:hasAttachment` | Mail | Anhang |
| `phil:name` | Person | xsd:string |
| `phil:email` | Person | xsd:string |
| `phil:date` | Termin | xsd:string |
| `phil:description` | Aufgabe/Projekt | xsd:string |

### Beispiel-Instanz

```turtle
phil:mail-42  a phil:Mail ;
    phil:sentBy           phil:person-mueller ;
    phil:relatedTo        phil:projekt-ki-modul ;
    phil:requiresAction   phil:task-gutachten-bis-freitag .

phil:person-mueller  a phil:Person ;
    phil:name   "Prof. Dr. Müller" ;
    phil:email  "mueller@hdm-stuttgart.de" .

phil:projekt-ki-modul  a phil:Projekt ;
    phil:description  "KI-Modul Sommersemester 2026" .

phil:task-gutachten-bis-freitag  a phil:Aufgabe ;
    phil:description  "Gutachten bis Freitag einreichen" .
```

---

## Attachment-Pipeline

### Extraktion

```python
# backend/attachment_extractor.py
def extract_text(data: bytes, mime_type: str) -> str:
    if mime_type == "application/pdf":
        return _extract_pdf(data)       # pdfplumber
    elif mime_type in DOCX_MIME_TYPES:
        return _extract_docx(data)      # python-docx
    return ""
```

### Integration in AnalyzeRequest

```python
class AttachmentIn(BaseModel):
    filename: str
    mime_type: str
    data_b64: str   # base64-encoded bytes

class AnalyzeRequest(BaseModel):
    email_text: str
    mail_id: str | None = None
    subject: str = ""
    sender: str = ""
    date: str = ""
    attachments: list[AttachmentIn] = []
```

### Verarbeitung

| Schritt | Beschreibung |
|---|---|
| Triage-Kontext | Erste 2.000 Zeichen Anhang-Text an Claude mitgeben |
| Zusammenfassung | Separater Claude-Call: 3-Satz-Zusammenfassung |
| ChromaDB | Eigener Eintrag, `doc_type=attachment`, `mail_id` als Metadatum |
| Ontologie | `phil:hasAttachment`-Tripel + Anhang-Instanz |

---

## Chat-Integration

Phil erhält zwei Kontext-Blöcke:

```
=== MAILHISTORIE (semantisch ähnliche frühere Mails) ===
  [2026-01-15] Von: mueller@hdm.de | Betreff: Gutachten ...

=== WISSENSGRAPH (strukturierte Verbindungen) ===
  Personen: Prof. Dr. Müller (5 Mails), Dr. Schmidt (2 Mails)
  Projekte: KI-Modul SS26, DFG-Antrag 2025
  Offene Aufgaben: Gutachten bis Freitag
```

### SPARQL-Templates (3 vorgefertigte Queries)

| Template | Auslöser |
|---|---|
| Personen-Suche | Eigenname erkannt (Claude NER) |
| Projekt-Suche | "Projekt", "Antrag", "Vorhaben" |
| Deadline-Suche | "Termin", "bis", "fällig", "Deadline" |

---

## Neue Dateien

```
backend/
├── attachment_extractor.py   # PDF/DOCX-Extraktion
├── ontology_store.py         # RDFLib wrapper
data/
└── ontology.ttl              # Persistenter RDF-Graph
```

## Geänderte Dateien

| Datei | Änderung |
|---|---|
| `backend/main.py` | AttachmentIn, entity-extraction, ontology_store singleton, 3 neue Endpoints |
| `backend/requirements.txt` | pdfplumber, python-docx, rdflib |
| `backend/knowledge_store.py` | `index_attachment()` Methode |
| `frontend/src/hooks/useDataLoader.ts` | Anhänge bei Fetch laden |
| `frontend/src/api/types.ts` | AttachmentIn, OntologyEntity |
| `frontend/src/api/client.ts` | `ontologySearch()` |
| `frontend/src/components/Phil/PhilPanel.tsx` | Wissensgraph-Panel |
| `frontend/src/components/Phil/PhilPanel.module.css` | Stile |

## Neue Endpoints

```
GET  /api/ontology/entities          → alle Entitäten
GET  /api/ontology/search?q=...      → SPARQL-Template-Suche
GET  /api/ontology/graph?mail_id=... → Triples einer Mail
```

## Neue Dependencies

```
pdfplumber>=0.11
python-docx>=1.1
rdflib>=7.0
```

---

## Tests

| Test | Datei |
|---|---|
| `test_extract_pdf` | `tests/test_attachment_extractor.py` |
| `test_extract_docx` | `tests/test_attachment_extractor.py` |
| `test_ontology_add_and_sparql_query` | `tests/test_ontology_store.py` |
| `test_ontology_entity_extraction_after_analyze` | `tests/test_api.py` |
| `test_ontology_search_requires_session` | `tests/test_api.py` |
| `test_chat_includes_graph_context` | `tests/test_api.py` |
