# tests/test_exchange.py
"""
Tests für exchange_helpers.py — Exchange-Aufrufe werden komplett gemockt.
Kein echter Exchange-Server nötig!
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# Import schlägt noch fehl — Modul existiert noch nicht
from exchange_helpers import (
    INSTITUTIONS,
    build_email_text,
    connect_to_exchange,
    fetch_emails,
)


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _make_mock_item(
    subject="Betreff",
    sender="sender@thws.de",
    text_body="Body-Text",
    is_read=False,
):
    """Erstellt ein Mock-E-Mail-Item wie es exchangelib liefert."""
    item = MagicMock()
    item.subject = subject
    item.sender = sender
    item.text_body = text_body
    item.body = None
    item.is_read = is_read
    item.datetime_received = datetime(2026, 2, 21, 9, 0, tzinfo=timezone.utc)
    return item


def _make_mock_account(items):
    """Erstellt einen Mock-Account mit vorkonfigurierten Inbox-Items."""
    account = MagicMock()
    for method in ("filter", "all"):
        chain = getattr(account.inbox, method).return_value
        chain.order_by.return_value.__getitem__ = MagicMock(return_value=items)
    return account


# ── Tests: connect_to_exchange ────────────────────────────────────────────────

class TestConnectToExchange:

    def test_raises_for_unknown_institution(self):
        with pytest.raises(ValueError, match="Unbekannte Institution"):
            connect_to_exchange("user", "pass", "OXFORD")

    @patch("exchange_helpers.Account")
    @patch("exchange_helpers.Credentials")
    def test_thws_domain_appended(self, mock_creds, mock_account):
        """Nur Benutzername ohne @ → Domain aus INSTITUTIONS wird angehängt."""
        connect_to_exchange("butscher", "geheim", "THWS")
        mock_creds.assert_called_once_with(
            username="butscher@thws.de", password="geheim"
        )

    @patch("exchange_helpers.Account")
    @patch("exchange_helpers.Credentials")
    def test_full_email_passed_through(self, mock_creds, mock_account):
        """Vollständige E-Mail mit @ wird direkt verwendet (DHBW-Sonderdomains)."""
        connect_to_exchange("name@dhbw-xyz.de", "pw", "DHBW")
        mock_creds.assert_called_once_with(
            username="name@dhbw-xyz.de", password="pw"
        )

    @patch("exchange_helpers.Account")
    @patch("exchange_helpers.Credentials")
    def test_autodiscover_is_enabled(self, mock_creds, mock_account):
        connect_to_exchange("butscher", "pw", "THWS")
        _, kwargs = mock_account.call_args
        assert kwargs.get("autodiscover") is True

    @patch("exchange_helpers.Account")
    @patch("exchange_helpers.Credentials")
    def test_returns_account_object(self, mock_creds, mock_account):
        mock_account.return_value = MagicMock()
        result = connect_to_exchange("butscher", "pw", "THWS")
        assert result is mock_account.return_value


# ── Tests: fetch_emails ───────────────────────────────────────────────────────

class TestFetchEmails:

    def test_returns_list(self):
        account = _make_mock_account([_make_mock_item()])
        result = fetch_emails(account, max_count=1)
        assert isinstance(result, list)

    def test_required_keys_present(self):
        account = _make_mock_account([_make_mock_item()])
        result = fetch_emails(account, max_count=1)
        for key in ("subject", "sender", "body", "datetime_received", "is_read"):
            assert key in result[0], f"Schlüssel '{key}' fehlt im Ergebnis-Dict"

    def test_unread_only_calls_filter(self):
        account = _make_mock_account([])
        fetch_emails(account, unread_only=True)
        account.inbox.filter.assert_called_once_with(is_read=False)

    def test_all_mails_calls_all(self):
        account = _make_mock_account([])
        fetch_emails(account, unread_only=False)
        account.inbox.all.assert_called_once()

    def test_long_body_truncated(self):
        long_body = "x" * 5_000
        account = _make_mock_account([_make_mock_item(text_body=long_body)])
        result = fetch_emails(account, max_count=1)
        assert len(result[0]["body"]) < 4_000
        assert "abgeschnitten" in result[0]["body"]

    def test_empty_inbox_returns_empty_list(self):
        account = _make_mock_account([])
        result = fetch_emails(account, max_count=10)
        assert result == []


# ── Tests: build_email_text ───────────────────────────────────────────────────

class TestBuildEmailText:

    BASE = {
        "sender": "dekan@thws.de",
        "subject": "DRINGEND",
        "body": "Bitte sofort antworten",
        "datetime_received": datetime(2026, 2, 21, 9, 0, tzinfo=timezone.utc),
    }

    def test_contains_sender(self):
        assert "dekan@thws.de" in build_email_text(self.BASE)

    def test_contains_subject(self):
        assert "DRINGEND" in build_email_text(self.BASE)

    def test_contains_body(self):
        assert "Bitte sofort antworten" in build_email_text(self.BASE)

    def test_contains_formatted_date(self):
        text = build_email_text(self.BASE)
        assert "21.02.2026" in text

    def test_none_datetime_shows_unbekannt(self):
        email = {**self.BASE, "datetime_received": None}
        assert "unbekannt" in build_email_text(email)
