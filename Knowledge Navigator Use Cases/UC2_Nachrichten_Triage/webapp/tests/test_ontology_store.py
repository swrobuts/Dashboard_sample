# tests/test_ontology_store.py
import pytest
from backend.ontology_store import OntologyStore


@pytest.fixture
def store(tmp_path):
    return OntologyStore(ttl_path=tmp_path / "ontology.ttl")


def test_add_mail_and_query_entities(store):
    """add_mail_triples persists persons, projects, tasks, deadlines."""
    store.add_mail_triples(
        mail_id="mail-001",
        sender_name="Prof. Müller",
        sender_email="mueller@hdm.de",
        subject="KI-Modul Besprechung",
        entities={
            "persons": ["Dr. Schmidt"],
            "projects": ["KI-Modul SS26"],
            "deadlines": ["2026-03-15"],
            "action_items": ["Gutachten einreichen"],
        },
    )
    ents = store.get_all_entities()
    names = [e["name"] for e in ents["persons"]]
    assert "Prof. Müller" in names
    assert "Dr. Schmidt" in names
    assert any(p["description"] == "KI-Modul SS26" for p in ents["projects"])
    assert any(t["description"] == "Gutachten einreichen" for t in ents["tasks"])
    assert any(d["date"] == "2026-03-15" for d in ents["deadlines"])


def test_get_context_for_chat_contains_wissensgraph(store):
    store.add_mail_triples(
        mail_id="mail-x",
        sender_name="Alice",
        sender_email="alice@test.de",
        subject="Test",
        entities={"persons": [], "projects": ["ProjektX"], "deadlines": [], "action_items": []},
    )
    ctx = store.get_context_for_chat("ProjektX")
    assert "WISSENSGRAPH" in ctx
    assert "ProjektX" in ctx


def test_empty_store_returns_empty_context(store):
    assert store.get_context_for_chat("anything") == ""


def test_persist_and_reload(tmp_path):
    path = tmp_path / "onto.ttl"
    s1 = OntologyStore(ttl_path=path)
    s1.add_mail_triples(
        "m1", "Bob", "bob@x.de", "Subject",
        {"persons": [], "projects": ["ProjX"], "deadlines": [], "action_items": []},
    )
    s2 = OntologyStore(ttl_path=path)   # fresh instance from disk
    ents = s2.get_all_entities()
    assert any(p["description"] == "ProjX" for p in ents["projects"])
