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
import imaplib
import logging
from datetime import datetime, timedelta
from email.header import decode_header
from email.utils import parsedate_to_datetime

_logger = logging.getLogger(__name__)

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

    Returns:
        Liste von Dicts: [{subject, sender, body, datetime_received, is_read}, ...]
    """
    mail = imaplib.IMAP4_SSL(imap_config["host"], imap_config["port"])
    try:
        mail.login(imap_config["username"], imap_config["password"])
        mail.select("INBOX")

        criteria = "UNSEEN" if unread_only else "ALL"
        _, msgs = mail.search(None, criteria)
        ids = msgs[0].split() if msgs[0] else []

        # IMAP liefert älteste zuerst → umkehren, dann abschneiden
        ids = ids[::-1][:max_count]

        emails = []
        for eid in ids:
            try:
                _, data = mail.fetch(eid, "(RFC822)")
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

                    if len(body) > 3_000:
                        body = body[:3_000] + "\n[... E-Mail-Inhalt abgeschnitten ...]"

                    # Datum parsen
                    try:
                        dt = parsedate_to_datetime(msg.get("Date", ""))
                        dt = dt.replace(tzinfo=None)
                    except Exception:
                        dt = None

                    emails.append({
                        "subject": subject or "(kein Betreff)",
                        "sender": sender,
                        "body": body,
                        "datetime_received": dt,
                        "is_read": not unread_only,
                    })
            except Exception:
                pass

        return emails
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
            body = item.text_body or item.body or ""
            if len(body) > 3_000:
                body = body[:3_000] + "\n[... E-Mail-Inhalt abgeschnitten ...]"
            emails.append({
                "subject": item.subject or "(kein Betreff)",
                "sender": sender_str,
                "body": body,
                "datetime_received": item.datetime_received,
                "is_read": item.is_read,
            })
        except Exception:
            skipped += 1

    if skipped:
        emails.append({"_skipped": skipped})
    return emails


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
        for item in account.tasks.filter(status__not="Completed").order_by("due_date")[:max_count]:
            tasks.append({
                "id": item.id,
                "changekey": item.changekey,
                "subject": item.subject or "(keine Bezeichnung)",
                "due_date": item.due_date.isoformat() if item.due_date else None,
                "status": str(item.status) if item.status else "NotStarted",
                "priority": str(item.importance) if item.importance else "Normal",
                "percent_complete": item.percent_complete or 0,
                "body": (item.text_body or item.body or "")[:500],
            })
        return tasks
    except Exception:
        return []


def complete_task(account: Account, task_id: str, changekey: str) -> bool:
    """Markiert eine Aufgabe als erledigt."""
    task = account.tasks.get(id=task_id, changekey=changekey)
    task.status = "Completed"
    task.percent_complete = 100
    task.save(update_fields=["status", "percent_complete"])
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
