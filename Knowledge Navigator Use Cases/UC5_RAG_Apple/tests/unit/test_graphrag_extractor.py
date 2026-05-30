"""Pure tests of the entity-extraction parser and entity-resolution helpers.
Runs without Neo4j or LLM."""
from backend.ingest.ue3_graphrag import (
    entity_key,
    normalize_entity_name,
    parse_extraction,
)


def test_normalize_strips_diacritics_and_punct():
    assert normalize_entity_name("Steve Jobs") == "steve jobs"
    assert normalize_entity_name("Apple Inc.") == "apple inc"
    assert normalize_entity_name("Sculley-Ära") == "sculley-ara"
    assert normalize_entity_name("  Macintosh  ") == "macintosh"


def test_entity_key_format():
    assert entity_key("Steve Jobs", "PERSON") == "PERSON:steve jobs"
    assert entity_key("Apple Inc.", "ORGANIZATION") == "ORGANIZATION:apple inc"


def test_parse_extraction_handles_clean_json():
    raw = """{
      "entities": [
        {"name": "Steve Jobs", "type": "PERSON", "description": "Mitgründer von Apple"},
        {"name": "Apple Inc.", "type": "ORGANIZATION", "description": "US-Unternehmen"}
      ],
      "relations": [
        {"source": "Steve Jobs", "target": "Apple Inc.", "type": "FOUNDED", "evidence": "..."}
      ]
    }"""
    ext = parse_extraction(raw, chunk_id=1)
    assert ext.chunk_id == 1
    assert len(ext.entities) == 2
    names = [e.name for e in ext.entities]
    assert "Steve Jobs" in names and "Apple Inc." in names
    assert len(ext.relations) == 1
    assert ext.relations[0].type == "FOUNDED"


def test_parse_extraction_strips_code_fence_and_prose():
    raw = """Hier das Ergebnis:
    ```json
    {"entities": [{"name": "iPhone", "type": "PRODUCT", "description": "Smartphone"}], "relations": []}
    ```"""
    ext = parse_extraction(raw, chunk_id=2)
    assert len(ext.entities) == 1
    assert ext.entities[0].type == "PRODUCT"


def test_parse_extraction_drops_invalid_types():
    raw = '{"entities": [{"name": "X", "type": "VEHICLE", "description": "y"}], "relations": []}'
    assert parse_extraction(raw, 1).entities == []


def test_parse_extraction_drops_dangling_relations():
    # Relation references an entity that wasn't extracted in the same chunk
    raw = """{
      "entities": [{"name": "Apple", "type": "ORGANIZATION", "description": "d"}],
      "relations": [{"source": "Apple", "target": "Microsoft", "type": "RIVAL", "evidence": "x"}]
    }"""
    ext = parse_extraction(raw, 1)
    assert ext.relations == []  # Microsoft not in entities → relation dropped


def test_parse_extraction_drops_self_relations():
    raw = """{
      "entities": [{"name": "Apple", "type": "ORGANIZATION", "description": "d"}],
      "relations": [{"source": "Apple", "target": "Apple", "type": "IS", "evidence": "x"}]
    }"""
    assert parse_extraction(raw, 1).relations == []


def test_parse_extraction_handles_garbage_response():
    assert parse_extraction("not JSON at all", 1).entities == []
    assert parse_extraction("", 1).entities == []
