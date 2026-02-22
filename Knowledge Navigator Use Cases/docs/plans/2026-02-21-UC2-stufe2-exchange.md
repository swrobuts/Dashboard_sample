# UC2 Stufe 2: Exchange Live-Anbindung — Implementierungsplan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Exchange-Postfach (THWS / DHBW) live im Notebook anbinden: ipywidgets-Credential-Dialog → exchangelib-Verbindung → ungelesene Mails laden → KI-Triage mit bestehendem Claude-Call.

**Architecture:** Neue `exchange_helpers.py` enthält alle Exchange-Funktionen (importierbar + testbar ohne Notebook). Das Notebook importiert daraus und zeigt einen ipywidgets-Credential-Dialog. Credentials leben ausschließlich im RAM der Session — kein Schreiben in Dateien oder Git.

**Tech Stack:** exchangelib ≥ 5.1.0, ipywidgets.Password, pytest + unittest.mock, Python 3.12

---

### Task 1: requirements.txt aktualisieren + exchangelib installieren

**Files:**
- Modify: `UC2_Nachrichten_Triage/requirements.txt`

**Step 1: requirements.txt öffnen und exchangelib eintragen**

Neuer Inhalt der Datei (kompletter Ersatz):

```
anthropic>=0.40.0
python-dotenv>=1.0.0
ipywidgets>=8.0.0
exchangelib>=5.1.0
pytest>=8.0.0
pytest-mock>=3.12.0
```

**Step 2: exchangelib installieren**

Run: `pip install "exchangelib>=5.1.0"`
Expected: `Successfully installed exchangelib-x.x.x` (oder "already satisfied")

**Step 3: Commit**

```bash
cd "UC2_Nachrichten_Triage"
git add requirements.txt
git commit -m "feat(UC2): add exchangelib to requirements for Stufe 2"
```

---

### Task 2: exchange_helpers.py + Tests (TDD)

**Files:**
- Create: `UC2_Nachrichten_Triage/exchange_helpers.py`
- Create: `UC2_Nachrichten_Triage/tests/test_exchange.py`

#### Schritt A: Failing Tests zuerst schreiben

Erstelle `UC2_Nachrichten_Triage/tests/test_exchange.py` mit diesem Inhalt:

```python
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
    # .filter().order_by()[:n] und .all().order_by()[:n]
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
```

**Step B: Test fehlschlägt verifizieren**

Run: `cd "UC2_Nachrichten_Triage" && pytest tests/test_exchange.py -v`
Expected: `ModuleNotFoundError: No module named 'exchange_helpers'`

#### Schritt C: exchange_helpers.py implementieren

Erstelle `UC2_Nachrichten_Triage/exchange_helpers.py`:

```python
"""
exchange_helpers.py — Exchange-Anbindung für UC2: Nachrichten-Triage Stufe 2.

Verbindet sich mit Exchange-Postfächern von THWS und DHBW via EWS
(Exchange Web Services / Autodiscover).

Sicherheitsprinzip:
    Credentials werden NIEMALS gespeichert — nur im RAM der laufenden Session.
    Diese Datei enthält keine Passwörter, Keys oder sensible Daten.
"""

from exchangelib import Account, Credentials, DELEGATE

# ── Institution-Konfiguration ─────────────────────────────────────────────────
# Neue Institutionen hier eintragen: Schlüssel = Anzeigename, domain = E-Mail-Domain

INSTITUTIONS: dict[str, dict] = {
    "THWS": {
        "domain": "thws.de",
        "display": "THWS Würzburg-Schweinfurt",
        "username_hint": "vorname.nachname  (→ @thws.de)",
    },
    "DHBW": {
        "domain": "dhbw.de",
        "display": "DHBW",
        "username_hint": "vollständige E-Mail  (z.B. name@dhbw-xyz.de)",
    },
}


def connect_to_exchange(username: str, password: str, institution: str) -> Account:
    """
    Baut eine Verbindung zum Exchange-Server über Autodiscover auf.

    Unterstützt zwei Eingabeformate für den Benutzernamen:
        - Nur Name:        "robert.butscher"   → wird zu "robert.butscher@thws.de"
        - Volle E-Mail:    "name@dhbw-xyz.de"  → wird unverändert übernommen

    Args:
        username:    Benutzername oder vollständige E-Mail-Adresse
        password:    Passwort — bleibt im RAM, wird nie gespeichert
        institution: Schlüssel aus INSTITUTIONS ("THWS" oder "DHBW")

    Returns:
        exchangelib.Account — authentifiziert, bereit für Postfach-Zugriff

    Raises:
        ValueError:  Unbekannte Institution
        Exception:   Verbindungs- oder Authentifizierungsfehler von exchangelib
    """
    if institution not in INSTITUTIONS:
        raise ValueError(
            f"Unbekannte Institution '{institution}'. "
            f"Erlaubt: {sorted(INSTITUTIONS.keys())}"
        )

    # Volle E-Mail direkt verwenden, sonst Domain anhängen
    if "@" in username:
        primary_smtp = username
    else:
        domain = INSTITUTIONS[institution]["domain"]
        primary_smtp = f"{username}@{domain}"

    credentials = Credentials(username=primary_smtp, password=password)

    account = Account(
        primary_smtp_address=primary_smtp,
        credentials=credentials,
        autodiscover=True,
        access_type=DELEGATE,
    )
    return account


def fetch_emails(
    account: Account,
    max_count: int = 20,
    unread_only: bool = True,
) -> list[dict]:
    """
    Lädt E-Mails aus dem Posteingang, sortiert nach Empfangsdatum (neueste zuerst).

    Args:
        account:     Authentifiziertes Account-Objekt (von connect_to_exchange)
        max_count:   Maximale Anzahl E-Mails (Standard: 20)
        unread_only: Nur ungelesene Mails (Standard: True)

    Returns:
        Liste von Dicts: [{subject, sender, body, datetime_received, is_read}, ...]
    """
    inbox = account.inbox

    if unread_only:
        items = inbox.filter(is_read=False)
    else:
        items = inbox.all()

    items = items.order_by("-datetime_received")[:max_count]

    emails = []
    for item in items:
        sender_str = str(item.sender) if item.sender else "Unbekannt"
        body = item.text_body or item.body or ""

        # Sehr lange E-Mails kürzen — Claude hat ein Token-Limit
        if len(body) > 3_000:
            body = body[:3_000] + "\n[... E-Mail-Inhalt abgeschnitten ...]"

        emails.append({
            "subject": item.subject or "(kein Betreff)",
            "sender": sender_str,
            "body": body,
            "datetime_received": item.datetime_received,
            "is_read": item.is_read,
        })

    return emails


def build_email_text(email_dict: dict) -> str:
    """
    Formatiert ein E-Mail-Dict als Plaintext für analyze_email().

    Args:
        email_dict: Dict aus fetch_emails() mit subject, sender, body, datetime_received

    Returns:
        Formatierter String mit Von:, Betreff:, Datum: und Body
    """
    dt = email_dict.get("datetime_received")
    dt_str = dt.strftime("%d.%m.%Y %H:%M") if dt else "unbekannt"

    return (
        f"Von: {email_dict['sender']}\n"
        f"Betreff: {email_dict['subject']}\n"
        f"Datum: {dt_str}\n\n"
        f"{email_dict['body']}"
    )
```

**Step D: Tests laufen lassen**

Run: `cd "UC2_Nachrichten_Triage" && pytest tests/test_exchange.py -v`
Expected: Alle Tests grün (PASSED)

**Step E: Commit**

```bash
git add UC2_Nachrichten_Triage/exchange_helpers.py UC2_Nachrichten_Triage/tests/test_exchange.py
git commit -m "feat(UC2): add exchange_helpers.py with connect/fetch/build + tests"
```

---

### Task 3: Stufe 2 Zellen ins Notebook einfügen

**Files:**
- Modify: `UC2_Nachrichten_Triage/nachrichten_triage.ipynb`

Das Notebook hat folgende Zellen (IDs):
- cell-01: Markdown-Header
- cell-02: Setup/Imports
- cell-03: CO-STAR Prompt
- cell-04: analyze_email + format_result_html
- cell-05: Einzelne-Mail UI (ipywidgets)
- cell-06: Batch-Demo (4 Sample-Mails)
- cell-07: Markdown "Erweiterungen" (Platzhalter)

**Ziel:** Nach cell-07 vier neue Zellen hinzufügen. cell-07 wird dabei aktualisiert.

#### Schritt A: cell-07 Inhalt ersetzen (Stufe 2 Intro)

Ersetze cell-07 durch diesen Markdown-Inhalt:

```markdown
---

## 📡 Stufe 2: Live-Anbindung an Exchange (THWS / DHBW)

Statt E-Mails manuell einzufügen, verbindet sich das Notebook direkt mit dem Exchange-Postfach und analysiert automatisch alle ungelesenen Nachrichten.

**Lernziele Stufe 2:**
- `exchangelib`: E-Mails über EWS (Exchange Web Services) laden
- Sicherer Credential-Dialog mit `ipywidgets`
- **Sicherheitsprinzip:** Credentials nur im RAM — nie auf Disk oder in Git

> ⚠ Zugangsdaten werden **niemals** gespeichert, geloggt oder übertragen.
> Kernel-Neustart löscht alle Credentials automatisch.
```

Verwende NotebookEdit mit `edit_mode=replace` auf cell-07.

#### Schritt B: Zelle S2-01 einfügen — Import exchange_helpers

Füge nach cell-07 eine neue Code-Zelle ein:

```python
# ── Stufe 2: Exchange-Hilfsfunktionen laden ───────────────────────────────────
# exchange_helpers.py enthält: connect_to_exchange, fetch_emails, build_email_text
# Alle Funktionen sind in tests/test_exchange.py getestet (kein echter Exchange nötig)

from exchange_helpers import (
    INSTITUTIONS,
    build_email_text,
    connect_to_exchange,
    fetch_emails,
)

print("✅ Exchange-Hilfsfunktionen geladen")
```

Verwende NotebookEdit mit `edit_mode=insert` nach cell-07 (cell_id="cell-07").

#### Schritt C: Zelle S2-02 einfügen — Credential-Dialog

Füge nach S2-01 eine neue Code-Zelle ein:

```python
# ── Stufe 2: Credential-Dialog ────────────────────────────────────────────────
#
# Sicherheitsprinzipien (Lehrinhalt — mit Studierenden besprechen):
#   1. Credentials NUR im RAM der Python-Session — nie in Dateien oder Git
#   2. Passwort ist maskiert (widgets.Password → nur Punkte sichtbar)
#   3. Passwort wird nach erfolgreichem Login aus dem Widget gelöscht
#   4. Kernel-Neustart → alle Credentials weg, exchange_account = None
# ─────────────────────────────────────────────────────────────────────────────

exchange_account = None  # Wird nach Verbindung gesetzt

# ── Widgets bauen ─────────────────────────────────────────────────────────────

inst_dropdown = widgets.Dropdown(
    options=list(INSTITUTIONS.keys()),
    value="THWS",
    description="Institution:",
    style={"description_width": "110px"},
    layout=widgets.Layout(width="340px"),
)

user_input = widgets.Text(
    placeholder=INSTITUTIONS["THWS"]["username_hint"],
    description="Benutzername:",
    style={"description_width": "110px"},
    layout=widgets.Layout(width="340px"),
)

pass_input = widgets.Password(
    placeholder="Passwort",
    description="Passwort:",
    style={"description_width": "110px"},
    layout=widgets.Layout(width="340px"),
)

connect_btn = widgets.Button(
    description="🔌 Verbinden",
    button_style="success",
    layout=widgets.Layout(width="150px"),
)

disconnect_btn = widgets.Button(
    description="❌ Trennen",
    button_style="danger",
    layout=widgets.Layout(width="150px"),
    disabled=True,
)

conn_status = widgets.Output()


# ── Platzhalter dynamisch anpassen ────────────────────────────────────────────

def on_inst_change(change):
    inst = change["new"]
    user_input.placeholder = INSTITUTIONS[inst]["username_hint"]

inst_dropdown.observe(on_inst_change, names="value")


# ── Event Handler: Verbinden ──────────────────────────────────────────────────

def on_connect(b):
    global exchange_account
    with conn_status:
        conn_status.clear_output()
        uname = user_input.value.strip()
        pwd = pass_input.value
        inst = inst_dropdown.value

        if not uname or not pwd:
            display(HTML(
                "<p style='color:#dc2626'>⚠️ Benutzername und Passwort erforderlich.</p>"
            ))
            return

        display(HTML("<p>⏳ Verbinde mit Exchange-Server (Autodiscover)...</p>"))
        try:
            exchange_account = connect_to_exchange(uname, pwd, inst)

            # Postfach-Info anzeigen
            total = exchange_account.inbox.total_count
            unread = exchange_account.inbox.unread_count
            smtp = exchange_account.primary_smtp_address

            conn_status.clear_output()
            display(HTML(
                f"<div style='padding:8px; border-left:3px solid #16a34a; background:#f0fdf4'>"
                f"✅ <b>Verbunden:</b> {smtp}<br>"
                f"📬 Posteingang: {total} Mails gesamt, {unread} ungelesen"
                f"</div>"
            ))

            # Passwort sofort aus Widget löschen (Sicherheit!)
            pass_input.value = ""
            connect_btn.disabled = True
            disconnect_btn.disabled = False

        except Exception as e:
            exchange_account = None
            conn_status.clear_output()
            display(HTML(
                f"<div style='padding:8px; border-left:3px solid #dc2626; background:#fef2f2'>"
                f"❌ <b>Verbindungsfehler:</b><br><code>{e}</code><br><br>"
                f"<small>Tipps: Benutzername/Passwort prüfen · "
                f"VPN aktiv? · Exchange-Server erreichbar?</small>"
                f"</div>"
            ))


# ── Event Handler: Trennen ────────────────────────────────────────────────────

def on_disconnect(b):
    global exchange_account
    exchange_account = None
    with conn_status:
        conn_status.clear_output()
        display(HTML(
            "<p style='color:#6b7280'>🔌 Verbindung getrennt — "
            "Credentials aus RAM gelöscht.</p>"
        ))
    connect_btn.disabled = False
    disconnect_btn.disabled = True
    user_input.value = ""


connect_btn.on_click(on_connect)
disconnect_btn.on_click(on_disconnect)


# ── UI rendern ────────────────────────────────────────────────────────────────

display(
    widgets.HTML("<h3>🔐 Exchange-Verbindung</h3>"),
    inst_dropdown,
    user_input,
    pass_input,
    widgets.HTML(
        "<p style='color:#6b7280; font-size:12px; margin:2px 0 8px 0;'>"
        "⚠ Ihre Daten werden nicht gespeichert — "
        "nur im Arbeitsspeicher dieser Jupyter-Session."
        "</p>"
    ),
    widgets.HBox([connect_btn, disconnect_btn]),
    conn_status,
)
```

#### Schritt D: Zelle S2-03 einfügen — Live-Triage

Füge nach S2-02 eine neue Code-Zelle ein:

```python
# ── Stufe 2: Live E-Mail-Triage ───────────────────────────────────────────────

max_slider = widgets.IntSlider(
    value=10,
    min=1,
    max=50,
    step=1,
    description="Max. Mails:",
    style={"description_width": "100px"},
    layout=widgets.Layout(width="380px"),
)

unread_chk = widgets.Checkbox(
    value=True,
    description="Nur ungelesene E-Mails analysieren",
    indent=False,
)

live_btn = widgets.Button(
    description="📡 Live-Triage starten",
    button_style="primary",
    layout=widgets.Layout(width="210px", height="40px"),
)

live_out = widgets.Output()


def on_live_triage(b):
    with live_out:
        live_out.clear_output()

        if exchange_account is None:
            display(HTML(
                "<p style='color:#dc2626'>"
                "⚠️ Bitte zuerst Exchange verbinden (Zelle oben)."
                "</p>"
            ))
            return

        display(HTML("<p>⏳ Lade E-Mails aus Exchange-Postfach...</p>"))

        try:
            emails = fetch_emails(
                account=exchange_account,
                max_count=max_slider.value,
                unread_only=unread_chk.value,
            )
        except Exception as e:
            live_out.clear_output()
            display(HTML(
                f"<p style='color:#dc2626'>❌ Fehler beim Laden: <code>{e}</code></p>"
            ))
            return

        if not emails:
            live_out.clear_output()
            label = "ungelesene " if unread_chk.value else ""
            display(HTML(
                f"<p style='color:#6b7280'>📭 Keine {label}E-Mails gefunden.</p>"
            ))
            return

        label = "ungelesene " if unread_chk.value else ""
        live_out.clear_output()
        display(HTML(
            f"<p>🤖 Analysiere {len(emails)} {label}E-Mail(s) mit Claude...</p>"
        ))

        results_html = f"<h3>📊 Live-Triage — {len(emails)} E-Mail(s)</h3>"
        errors = 0

        for i, email_dict in enumerate(emails, 1):
            email_text = build_email_text(email_dict)
            try:
                result = analyze_email(email_text)
                results_html += format_result_html(result, email_text)
            except Exception as e:
                errors += 1
                subj = email_dict["subject"][:50]
                results_html += (
                    f"<p style='color:#dc2626'>"
                    f"❌ Fehler bei Mail {i} ({subj}...): {e}"
                    f"</p>"
                )

        live_out.clear_output()

        if errors:
            results_html += (
                f"<p style='color:#d97706'>"
                f"⚠ {errors} Mail(s) konnten nicht analysiert werden.</p>"
            )

        display(HTML(results_html))


live_btn.on_click(on_live_triage)

display(
    widgets.HTML("<h3>📡 Live E-Mail-Triage</h3>"),
    max_slider,
    unread_chk,
    live_btn,
    live_out,
)
```

**Step E: Commit**

```bash
git add UC2_Nachrichten_Triage/nachrichten_triage.ipynb
git commit -m "feat(UC2): add Stufe 2 Exchange live triage cells to notebook"
```

---

### Task 4: README aktualisieren

**Files:**
- Modify: `UC2_Nachrichten_Triage/README.md`

Lies das bestehende README, dann füge einen neuen Abschnitt **vor** dem letzten Abschnitt ein (oder am Ende falls kein guter Einfügepunkt):

```markdown
## Stufe 2: Live Exchange-Anbindung

### Voraussetzungen

```bash
pip install "exchangelib>=5.1.0"
```

### Nutzung

1. Notebook öffnen und alle Zellen bis "Stufe 1" ausführen (Setup + Funktionen)
2. Dann Stufe-2-Zellen ausführen
3. **Credential-Dialog:** Institution wählen, Benutzername und Passwort eingeben
4. **Verbinden** klicken — bei Erfolg: Postfach-Info erscheint, Passwort wird gelöscht
5. **Live-Triage starten** klicken

### Benutzername-Format

| Institution | Format | Beispiel |
|-------------|--------|---------|
| THWS | `vorname.nachname` | `robert.butscher` |
| DHBW | Vollständige E-Mail | `name@dhbw-mannheim.de` |

### Sicherheitshinweise

- Credentials werden **niemals** in Dateien, Datenbanken oder Git gespeichert
- Passwort nur im RAM der laufenden Jupyter-Session
- Passwort wird nach erfolgreichem Login aus dem Widget gelöscht
- Kernel-Neustart → alle Credentials automatisch gelöscht

### Tests ausführen

```bash
cd UC2_Nachrichten_Triage
pytest tests/ -v
# Erwartet: 4 Tests für analyze_email + 12 Tests für exchange_helpers — alle grün
```
```

**Step: Commit**

```bash
git add UC2_Nachrichten_Triage/README.md
git commit -m "docs(UC2): add Stufe 2 Exchange section to README"
```

---

### Task 5: Verification — Alle Tests laufen

**Files:** keine Änderungen

**Step 1: Alle Tests laufen**

Run: `cd "UC2_Nachrichten_Triage" && pytest tests/ -v`
Expected:
```
tests/test_analyze_email.py::test_analyze_email_returns_dict PASSED
tests/test_analyze_email.py::test_analyze_email_has_required_fields PASSED
tests/test_analyze_email.py::test_analyze_email_kategorie_valid PASSED
tests/test_analyze_email.py::test_analyze_email_priorität_range PASSED
tests/test_exchange.py::TestConnectToExchange::test_raises_for_unknown_institution PASSED
tests/test_exchange.py::TestConnectToExchange::test_thws_domain_appended PASSED
tests/test_exchange.py::TestConnectToExchange::test_full_email_passed_through PASSED
tests/test_exchange.py::TestConnectToExchange::test_autodiscover_is_enabled PASSED
tests/test_exchange.py::TestConnectToExchange::test_returns_account_object PASSED
tests/test_exchange.py::TestFetchEmails::test_returns_list PASSED
tests/test_exchange.py::TestFetchEmails::test_required_keys_present PASSED
tests/test_exchange.py::TestFetchEmails::test_unread_only_calls_filter PASSED
tests/test_exchange.py::TestFetchEmails::test_all_mails_calls_all PASSED
tests/test_exchange.py::TestFetchEmails::test_long_body_truncated PASSED
tests/test_exchange.py::TestFetchEmails::test_empty_inbox_returns_empty_list PASSED
tests/test_exchange.py::TestBuildEmailText::test_contains_sender PASSED
tests/test_exchange.py::TestBuildEmailText::test_contains_subject PASSED
tests/test_exchange.py::TestBuildEmailText::test_contains_body PASSED
tests/test_exchange.py::TestBuildEmailText::test_contains_formatted_date PASSED
tests/test_exchange.py::TestBuildEmailText::test_none_datetime_shows_unbekannt PASSED

20 passed in X.XXs
```

**Step 2: Final Commit (falls nötig)**

Wenn alle Tests grün: kein weiterer Commit nötig. Alle Änderungen sind bereits committed.

---

## Zusammenfassung

Nach Abschluss aller Tasks:
- `exchange_helpers.py`: testbare Exchange-Funktionen (connect, fetch, build)
- `tests/test_exchange.py`: 16 Tests, alle gemockt, kein echter Exchange nötig
- Notebook: 3 neue Stufe-2-Zellen (Import, Credential-Dialog, Live-Triage)
- README: Stufe-2-Dokumentation
- Insgesamt: 20 Tests grün
