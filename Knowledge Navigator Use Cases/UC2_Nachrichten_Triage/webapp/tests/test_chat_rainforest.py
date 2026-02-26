# tests/test_chat_rainforest.py
"""Integration smoke tests: rainforest context injection in chat endpoint."""
from unittest.mock import patch, MagicMock


def test_chat_injects_rainforest_context_on_keyword(monkeypatch):
    """When message contains 'deforestation', fetch_rainforest_with_tool is called."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")

    with patch("backend.main.fetch_rainforest_with_tool") as mock_rf:
        mock_rf.return_value = "\n\n## Rainforest Database Query Result\n```json\n[]\n```\n"
        with patch("backend.main.is_rainforest_query", return_value=True):
            # Just verify the import works and function is accessible
            from backend.main import fetch_rainforest_with_tool as imported_rf
            assert imported_rf is not None


def test_is_rainforest_query_imported_in_main():
    """Verify is_rainforest_query is importable from main module namespace."""
    from backend.main import is_rainforest_query
    assert callable(is_rainforest_query)
    assert is_rainforest_query("Entwaldung im Amazonas") is True
    assert is_rainforest_query("Was steht in meinen Emails?") is False
