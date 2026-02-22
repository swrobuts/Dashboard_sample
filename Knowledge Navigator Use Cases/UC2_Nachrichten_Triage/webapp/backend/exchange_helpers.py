"""
exchange_helpers.py — Mail-Anbindung für PHIL PIM Dashboard.

THWS: zwei Protokolle parallel
  - IMAP  Port 993 SSL   → E-Mails lesen (imaplib)
  - EWS   Port 443 HTTPS → Kalender + Aufgaben (exchangelib)
  Server: webmail.thws.de

DHBW: nur EWS (autodiscover)

Sicherheitsprinzip:
    Credentials werden NIEMALS gespeichert — nur im RAM der laufenden Session.
    Diese Datei enthält keine Passwörter, Keys oder sensible Daten.
"""

import email
import html
import imaplib
import json
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta
from email.header import decode_header
from email.utils import parsedate_to_datetime

_logger = logging.getLogger(__name__)


def strip_html(text: str) -> str:
    """Entfernt HTML-Tags aus einem String und gibt lesbaren Klartext zurück."""
    if not text:
        return ""
    # Script- und Style-Blöcke komplett entfernen (inkl. Inhalt)
    text = re.sub(r'<(script|style)[^>]*>.*?</(script|style)>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    # Zeilenumbruch-Tags in Newlines umwandeln
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?(p|div|tr|li|h[1-6])[^>]*>', '\n', text, flags=re.IGNORECASE)
    # Alle übrigen Tags entfernen
    text = re.sub(r'<[^>]+>', ' ', text)
    # HTML-Entities dekodieren (&amp; → &, &nbsp; → Leerzeichen, usw.)
    text = html.unescape(text)
    # Mehrfache Leerzeichen / Leerzeilen bereinigen
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _to_rfc3339(dt_str: str) -> str:
    """'2026-02-23T14:00' → '2026-02-23T14:00:00+01:00' (lokale Zeitzone).

    gog CLI erwartet RFC3339 mit Timezone-Offset; datetime-local-Inputs
    aus dem Browser liefern nur 'YYYY-MM-DDTHH:MM' ohne Offset.
    """
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.astimezone()   # lokale Systemzeitzone anhängen
        return dt.isoformat()
    except ValueError:
        return dt_str  # bereits RFC3339 oder unbekanntes Format → unverändert

from exchangelib import (
    DELEGATE,
    NTLM,
    Account,
    CalendarItem,
    Configuration,
    Credentials,
    Task as EWSTask,
)

# ── Institution-Konfiguration ─────────────────────────────────────────────────

INSTITUTIONS: dict[str, dict] = {
    "THWS": {
        "display": "THWS Würzburg-Schweinfurt",
        "username_hint": "butscher  oder  robert.butscher@fhws.de",
        # IMAP — E-Mails
        "protocol": "imap+ews",
        "imap_host": "webmail.thws.de",
        "imap_port": 993,
        # EWS — Kalender + Aufgaben (manuell konfiguriert, kein autodiscover)
        "ews_host": "webmail.thws.de",
        "ews_url": "https://webmail.thws.de/EWS/Exchange.asmx",
    },
    "DHBW": {
        "display": "DHBW",
        "username_hint": "vollständige E-Mail  (z.B. name@dhbw-xyz.de)",
        "protocol": "ews",
        "ews_url": None,   # autodiscover
    },
}


# ── IMAP ──────────────────────────────────────────────────────────────────────

def connect_to_imap(username: str, password: str, host: str, port: int = 993) -> dict:
    """
    Testet IMAP-Credentials und gibt ein Konfigurations-Dict zurück.

    Probiert Login-Formate:
        "butscher"          → zuerst butscher (plain), dann butscher@fhws.de
        "butscher@fhws.de"  → direkt

    Returns:
        {"host", "port", "username", "password", "inbox_count"}

    Raises:
        imaplib.IMAP4.error bei Login-Fehler
    """
    if "@" in username:
        candidates = [username]
    else:
        # Plain zuerst (wie MAIL_LOGIN in der Konfiguration), dann mit Domain
        candidates = [username, f"{username}@fhws.de", f"{username}@thws.de"]

    last_error: Exception = Exception("IMAP-Verbindung fehlgeschlagen")
    for uname in candidates:
        try:
            mail = imaplib.IMAP4_SSL(host, port)
            mail.login(uname, password)
            mail.select("INBOX")
            _, msgs = mail.search(None, "UNSEEN")
            unread = len(msgs[0].split()) if msgs[0] else 0
            mail.logout()
            return {
                "host": host,
                "port": port,
                "username": uname,
                "password": password,
                "inbox_count": unread,
            }
        except imaplib.IMAP4.error as e:
            last_error = e
    raise last_error


def fetch_emails_imap(
    imap_config: dict,
    max_count: int = 20,
    unread_only: bool = True,
) -> list[dict]:
    """
    Lädt E-Mails via IMAP (neue Verbindung pro Aufruf).
    Verwendet UID-basierte Befehle für stabile Mail-IDs (auch nach Löschvorgängen).

    Returns:
        Liste von Dicts: [{subject, sender, body, datetime_received, is_read, mail_uid}, ...]
    """
    mail = imaplib.IMAP4_SSL(imap_config["host"], imap_config["port"])
    try:
        mail.login(imap_config["username"], imap_config["password"])
        mail.select("INBOX")

        criteria = "UNSEEN" if unread_only else "ALL"
        # UID-basierte Suche — stabile IDs unabhängig von anderen Löschvorgängen
        _, msgs = mail.uid("search", None, criteria)
        uids = msgs[0].split() if msgs[0] else []

        # IMAP liefert älteste zuerst → umkehren, dann abschneiden
        uids = uids[::-1][:max_count]

        emails = []
        for uid in uids:
            try:
                _, data = mail.uid("fetch", uid, "(RFC822)")
                for part in data:
                    if not isinstance(part, tuple):
                        continue
                    msg = email.message_from_bytes(part[1])

                    # Betreff dekodieren
                    raw_subj = decode_header(msg.get("Subject") or "")
                    subject = ""
                    for chunk, enc in raw_subj:
                        if isinstance(chunk, bytes):
                            subject += chunk.decode(enc or "utf-8", errors="replace")
                        else:
                            subject += str(chunk)

                    # Absender dekodieren (MIME-encoded words möglich)
                    raw_from = msg.get("From", "Unbekannt")
                    decoded_parts = []
                    for chunk, enc in decode_header(raw_from):
                        if isinstance(chunk, bytes):
                            decoded_parts.append(chunk.decode(enc or "utf-8", errors="replace"))
                        else:
                            decoded_parts.append(str(chunk))
                    sender = "".join(decoded_parts) or "Unbekannt"

                    # Body extrahieren
                    body = ""
                    if msg.is_multipart():
                        for p in msg.walk():
                            if (
                                p.get_content_type() == "text/plain"
                                and p.get("Content-Disposition") is None
                            ):
                                payload = p.get_payload(decode=True)
                                if payload:
                                    enc = p.get_content_charset() or "utf-8"
                                    body = payload.decode(enc, errors="replace")
                                    break
                    else:
                        payload = msg.get_payload(decode=True)
                        if payload:
                            enc = msg.get_content_charset() or "utf-8"
                            body = payload.decode(enc, errors="replace")

                    body = strip_html(body)
                    if len(body) > 3_000:
                        body = body[:3_000] + "\n[... E-Mail-Inhalt abgeschnitten ...]"

                    # Datum parsen
                    try:
                        dt = parsedate_to_datetime(msg.get("Date", ""))
                        dt = dt.replace(tzinfo=None)
                    except Exception:
                        dt = None

                    uid_str = uid.decode() if isinstance(uid, bytes) else str(uid)
                    emails.append({
                        "subject": subject or "(kein Betreff)",
                        "sender": sender,
                        "body": body,
                        "datetime_received": dt,
                        "is_read": not unread_only,
                        "mail_uid": uid_str,  # stabile IMAP UID für Löschvorgänge
                    })
            except Exception:
                pass

        return emails
    finally:
        try:
            mail.logout()
        except Exception:
            pass


def delete_mail_imap(imap_config: dict, mail_uid: str) -> bool:
    """Löscht eine E-Mail dauerhaft via IMAP UID (HardDelete + Expunge)."""
    mail = imaplib.IMAP4_SSL(imap_config["host"], imap_config["port"])
    try:
        mail.login(imap_config["username"], imap_config["password"])
        mail.select("INBOX")
        uid_bytes = mail_uid.encode() if isinstance(mail_uid, str) else mail_uid
        mail.uid("store", uid_bytes, "+FLAGS", "\\Deleted")
        mail.expunge()
        return True
    finally:
        try:
            mail.logout()
        except Exception:
            pass


# ── EWS Connect ───────────────────────────────────────────────────────────────

def connect_to_exchange_thws(
    username: str, password: str, exchange_email: str | None = None
) -> Account:
    """
    Baut EWS-Verbindung zu THWS auf (webmail.thws.de/EWS/Exchange.asmx).
    Autodiscover ist deaktiviert — direkter Endpoint.

    exchange_email: Falls angegeben, wird diese Adresse als primary_smtp_address
                    verwendet (z.B. "robert.butscher@fhws.de"). Sonst automatische
                    Ableitung aus dem Benutzernamen.

    Probiert 5 Username-Formate automatisch durch:
        1. THWS\\{base}
        2. thws\\{base}
        3. {base}           (plain)
        4. {base}@thws.de
        5. {base}@fhws.de

    Raises:
        Exception wenn alle Formate scheitern
    """
    ews_url = INSTITUTIONS["THWS"]["ews_url"]

    # Basis-Username extrahieren (ohne Domain, ohne DOMAIN\)
    if "\\" in username:
        base = username.split("\\", 1)[1]
    elif "@" in username:
        base = username.split("@")[0]
    else:
        base = username

    # primary_smtp: nutze angegebene E-Mail oder leite aus Username ab
    if exchange_email and "@" in exchange_email:
        primary_smtp_candidates = [exchange_email.strip()]
    else:
        primary_smtp_candidates = [f"{base}@fhws.de", f"{base}@thws.de"]

    auth_candidates = [
        f"THWS\\{base}",
        f"thws\\{base}",
        base,
        f"{base}@thws.de",
        f"{base}@fhws.de",
    ]

    last_error: Exception = Exception("EWS-Verbindung fehlgeschlagen")
    for primary_smtp in primary_smtp_candidates:
        for uname in auth_candidates:
            try:
                credentials = Credentials(username=uname, password=password)
                config = Configuration(
                    service_endpoint=ews_url,
                    credentials=credentials,
                    auth_type=NTLM,
                )
                account = Account(
                    primary_smtp_address=primary_smtp,
                    config=config,
                    autodiscover=False,
                    access_type=DELEGATE,
                )
                # Erster echter Netzwerk-Call — testet die Credentials
                _ = account.inbox.total_count
                _logger.info(f"[EWS] Verbunden als {uname} / {primary_smtp}")
                return account
            except Exception as e:
                _logger.warning(
                    f"[EWS] {uname} / {primary_smtp} fehlgeschlagen: "
                    f"{type(e).__name__}: {str(e)[:200]}"
                )
                last_error = e

    raise last_error


def connect_to_exchange(username: str, password: str, institution: str) -> Account:
    """
    Baut eine EWS-Verbindung auf.
    THWS → connect_to_exchange_thws (manueller Endpoint + Username-Fallback)
    DHBW → NTLM + autodiscover
    """
    if institution not in INSTITUTIONS:
        raise ValueError(
            f"Unbekannte Institution '{institution}'. "
            f"Erlaubt: {sorted(INSTITUTIONS.keys())}"
        )

    if institution == "THWS":
        return connect_to_exchange_thws(username, password)

    # DHBW und andere EWS-Institutionen
    inst = INSTITUTIONS[institution]
    if inst.get("protocol") != "ews":
        raise ValueError(f"Institution '{institution}' nutzt nicht EWS.")

    inst_domain = inst.get("domain", "")
    if "@" in username:
        primary_smtp = username
        ntlm_username = username
    else:
        primary_smtp = f"{username}@{inst_domain}"
        ntlm_username = username

    credentials = Credentials(username=ntlm_username, password=password)
    ews_url = inst.get("ews_url")

    if ews_url:
        config = Configuration(
            service_endpoint=ews_url,
            credentials=credentials,
            auth_type=NTLM,
        )
        account = Account(
            primary_smtp_address=primary_smtp,
            config=config,
            autodiscover=False,
            access_type=DELEGATE,
        )
    else:
        config = Configuration(credentials=credentials, auth_type=NTLM)
        account = Account(
            primary_smtp_address=primary_smtp,
            config=config,
            autodiscover=True,
            access_type=DELEGATE,
        )
    return account


# ── EWS Email ─────────────────────────────────────────────────────────────────

def fetch_emails(
    account: Account,
    max_count: int = 20,
    unread_only: bool = True,
) -> list[dict]:
    """Lädt E-Mails via EWS, sortiert nach Empfangsdatum (neueste zuerst)."""
    inbox = account.inbox
    items = inbox.filter(is_read=False) if unread_only else inbox.all()
    items = items.order_by("-datetime_received")[:max_count]

    emails = []
    skipped = 0
    for item in items:
        try:
            sender_str = str(item.sender) if item.sender else "Unbekannt"
            raw = item.text_body or item.body or ""
            body = strip_html(raw) if raw else ""
            if len(body) > 3_000:
                body = body[:3_000] + "\n[... E-Mail-Inhalt abgeschnitten ...]"
            emails.append({
                "subject": item.subject or "(kein Betreff)",
                "sender": sender_str,
                "body": body,
                "datetime_received": item.datetime_received,
                "is_read": item.is_read,
                "mail_uid": item.id,  # EWS Item-ID für Löschvorgänge
            })
        except Exception:
            skipped += 1

    if skipped:
        emails.append({"_skipped": skipped})
    return emails


def delete_mail_ews(account: Account, item_id: str) -> bool:
    """Löscht eine E-Mail via EWS (HardDelete). Sucht nach ID im Posteingang."""
    try:
        for item in account.inbox.all()[:500]:
            if item.id == item_id:
                item.delete()
                return True
    except Exception as e:
        _logger.warning(f"[EWS-DeleteMail] {type(e).__name__}: {e}")
    return True  # Best effort — bei Fehler trotzdem OK


def build_email_text(email_dict: dict) -> str:
    """Formatiert ein E-Mail-Dict als Plaintext für analyze_email()."""
    dt = email_dict.get("datetime_received")
    dt_str = dt.strftime("%d.%m.%Y %H:%M") if dt else "unbekannt"
    return (
        f"Von: {email_dict.get('sender', 'Unbekannt')}\n"
        f"Betreff: {email_dict.get('subject', '(kein Betreff)')}\n"
        f"Datum: {dt_str}\n\n"
        f"{email_dict.get('body', '')}"
    )


# ── EWS Calendar ──────────────────────────────────────────────────────────────

def fetch_calendar(account: Account, days_ahead: int = 14) -> list[dict]:
    """Lädt Kalender-Einträge der nächsten `days_ahead` Tage."""
    try:
        from exchangelib import EWSDateTime, EWSTimeZone
        tz = EWSTimeZone.localzone()
        now = EWSDateTime.now(tz=tz)
        end = now + timedelta(days=days_ahead)
        items = []
        for item in account.calendar.view(start=now, end=end):
            items.append({
                "id": item.id,
                "changekey": item.changekey,
                "subject": item.subject or "(kein Titel)",
                "start": item.start.isoformat() if item.start else None,
                "end": item.end.isoformat() if item.end else None,
                "location": item.location or "",
                "body": (item.text_body or item.body or "")[:500],
                "is_recurring": bool(getattr(item, "is_recurring", False)),
            })
        items.sort(key=lambda x: x["start"] or "")
        return items
    except Exception:
        return []


def create_calendar_entry(
    account: Account,
    subject: str,
    start: str,
    end: str,
    location: str = "",
    body: str = "",
) -> dict:
    """Erstellt einen neuen Kalender-Eintrag."""
    from exchangelib import EWSDateTime, EWSTimeZone
    tz = EWSTimeZone.localzone()
    item = CalendarItem(
        account=account,
        folder=account.calendar,
        subject=subject,
        start=EWSDateTime.from_datetime(datetime.fromisoformat(start)).astimezone(tz),
        end=EWSDateTime.from_datetime(datetime.fromisoformat(end)).astimezone(tz),
        location=location,
        body=body,
    )
    item.save()
    return {"id": item.id, "subject": item.subject}


# ── EWS Tasks ─────────────────────────────────────────────────────────────────

def fetch_tasks(account: Account, max_count: int = 100) -> list[dict]:
    """Lädt offene Aufgaben (nicht 'Completed')."""
    try:
        tasks = []
        # Alle Aufgaben holen, dann in Python filtern (vermeidet Syntax-Probleme
        # mit exchangelib-Feldfiltern für Choice-Felder wie status)
        for item in account.tasks.all()[:max_count * 2]:
            status_str = str(item.status) if item.status else "NotStarted"
            if status_str == "Completed":
                continue
            tasks.append({
                "id": item.id,
                "changekey": item.changekey,
                "subject": item.subject or "(keine Bezeichnung)",
                "due_date": item.due_date.isoformat() if item.due_date else None,
                "status": status_str,
                "priority": str(item.importance) if item.importance else "Normal",
                "percent_complete": item.percent_complete or 0,
                "body": (item.text_body or item.body or "")[:500],
            })
            if len(tasks) >= max_count:
                break
        _logger.warning(f"[EWS-Tasks] {len(tasks)} offene Aufgaben geladen")
        return tasks
    except Exception as exc:
        _logger.warning(f"[EWS-Tasks] fetch_tasks fehlgeschlagen: {type(exc).__name__}: {exc}")
        return []


def complete_task(account: Account, task_id: str, changekey: str) -> bool:
    """Markiert eine Aufgabe als erledigt."""
    task = account.tasks.get(id=task_id, changekey=changekey)
    task.status = "Completed"
    task.percent_complete = 100
    task.save(update_fields=["status", "percent_complete"])
    return True


def delete_task(account: Account, task_id: str, changekey: str) -> bool:
    """Löscht eine Aufgabe dauerhaft aus Exchange (HardDelete).
    Fällt auf ID-only-Suche zurück, falls der changekey veraltet ist."""
    try:
        task = account.tasks.get(id=task_id, changekey=changekey)
    except Exception:
        # changekey könnte veraltet sein → alle Tasks nach ID durchsuchen
        task = next((t for t in account.tasks.all()[:500] if t.id == task_id), None)
        if task is None:
            return True  # Bereits gelöscht oder nicht mehr vorhanden
    task.delete()
    return True


def create_task(
    account: Account,
    subject: str,
    due_date: str | None,
    body: str,
    priority: str = "Normal",
) -> dict:
    """Erstellt eine neue Aufgabe."""
    task = EWSTask(
        account=account,
        folder=account.tasks,
        subject=subject,
        due_date=datetime.fromisoformat(due_date).date() if due_date else None,
        body=body,
        importance=priority,
    )
    task.save()
    return {"id": task.id, "subject": task.subject}


# ── Google Calendar via gog CLI ───────────────────────────────────────────────

def _gog_binary() -> str:
    """Findet das gog-Binary: ~/bin/gog (Docker/Linux) oder PATH (macOS/Dev)."""
    home_bin = os.path.expanduser("~/bin/gog")
    if os.path.isfile(home_bin) and os.access(home_bin, os.X_OK):
        return home_bin
    gog_in_path = shutil.which("gog")
    if gog_in_path:
        return gog_in_path
    raise FileNotFoundError("gog binary nicht gefunden (~/.bin/gog oder PATH)")


def _gog_env() -> dict:
    """Env-Dict für gog-Aufrufe (inkl. optionalem Keyring-Passwort für Docker)."""
    env = dict(os.environ)
    keyring_pw = os.getenv("GOG_KEYRING_PASSWORD", "")
    if keyring_pw:
        env["GOG_KEYRING_PASSWORD"] = keyring_pw
    return env


def fetch_google_calendar(days_ahead: int = 180) -> list[dict]:
    """Liest Google Kalender via gog CLI (±6 Monate)."""
    account = os.getenv("GOG_ACCOUNT", "swrobuts@googlemail.com")
    gog = _gog_binary()

    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    from_dt = (now - timedelta(days=180)).strftime("%Y-%m-%d")
    to_dt   = (now + timedelta(days=180)).strftime("%Y-%m-%d")

    result = subprocess.run(
        [
            gog, "calendar", "events",
            "--account", account,
            "--from", from_dt,
            "--to",   to_dt,
            "--json",
            "--max", "500",
            "--no-input",
        ],
        capture_output=True, text=True,
        env=_gog_env(), timeout=30,
    )

    if result.returncode != 0:
        _logger.warning(f"[GCal] gog error (rc={result.returncode}): {result.stderr.strip()[:300]}")
        raise Exception(f"Google Calendar: {result.stderr.strip()[:200]}")

    data = json.loads(result.stdout)
    events_raw = data.get("events", []) if isinstance(data, dict) else data
    _logger.warning(f"[GCal] {len(events_raw)} Einträge geladen")

    items = []
    for e in events_raw:
        start_obj = e.get("start", {})
        end_obj = e.get("end", {})
        items.append({
            "id": e.get("id", ""),
            "changekey": "",
            "subject": e.get("summary", "(kein Titel)"),
            "start": start_obj.get("dateTime") or start_obj.get("date"),
            "end": end_obj.get("dateTime") or end_obj.get("date"),
            "location": e.get("location", ""),
            "body": "",
            "is_recurring": bool(e.get("recurringEventId")),
        })
    items.sort(key=lambda x: x["start"] or "")
    return items


def delete_google_calendar_event(event_id: str) -> bool:
    """Löscht ein Google Kalender-Ereignis via gog CLI."""
    account_email = os.getenv("GOG_ACCOUNT", "swrobuts@googlemail.com")
    gog = _gog_binary()
    result = subprocess.run(
        [gog, "calendar", "delete", account_email, event_id, "--force", "--no-input"],
        capture_output=True, text=True,
        env=_gog_env(), timeout=20,
    )
    if result.returncode != 0:
        raise Exception(f"gog calendar delete: {result.stderr.strip()[:200]}")
    return True


def update_google_calendar_event(
    event_id: str,
    subject: str,
    start: str,
    end: str,
    location: str = "",
    body: str = "",
) -> dict:
    """Aktualisiert einen Google Kalender-Termin via gog CLI."""
    account = os.getenv("GOG_ACCOUNT", "swrobuts@googlemail.com")
    gog = _gog_binary()

    cmd = [
        gog, "calendar", "update", account, event_id,
        "--summary", subject,
        "--from", _to_rfc3339(start),
        "--to", _to_rfc3339(end),
        "--location", location,   # leer = löscht Location
        "--json",
        "--no-input",
    ]
    if body:
        cmd += ["--description", body]
    else:
        cmd += ["--description", ""]  # löscht bestehende Description

    result = subprocess.run(
        cmd, capture_output=True, text=True,
        env=_gog_env(), timeout=20,
    )
    if result.returncode != 0:
        raise Exception(f"gog calendar update: {result.stderr.strip()[:200]}")

    return {"id": event_id, "subject": subject}


def create_google_calendar_event(
    subject: str,
    start: str,
    end: str,
    location: str = "",
    body: str = "",
) -> dict:
    """Erstellt einen Google Kalender-Termin via gog CLI."""
    account = os.getenv("GOG_ACCOUNT", "swrobuts@googlemail.com")
    gog = _gog_binary()

    cmd = [
        gog, "calendar", "create", account,
        "--summary", subject,
        "--from", _to_rfc3339(start),
        "--to", _to_rfc3339(end),
        "--json",
        "--no-input",
    ]
    if location:
        cmd += ["--location", location]
    if body:
        cmd += ["--description", body]

    result = subprocess.run(
        cmd, capture_output=True, text=True,
        env=_gog_env(), timeout=20,
    )
    if result.returncode != 0:
        raise Exception(f"gog create: {result.stderr.strip()[:200]}")

    created = json.loads(result.stdout)
    return {"id": created.get("id", ""), "subject": created.get("summary", subject)}
