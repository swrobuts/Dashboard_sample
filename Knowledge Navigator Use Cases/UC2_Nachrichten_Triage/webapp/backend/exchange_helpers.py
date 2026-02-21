"""
exchange_helpers.py — Exchange-Anbindung für PHIL PIM Dashboard.

Verbindet sich mit Exchange-Postfächern von THWS und DHBW via EWS
(Exchange Web Services / Autodiscover).

Sicherheitsprinzip:
    Credentials werden NIEMALS gespeichert — nur im RAM der laufenden Session.
    Diese Datei enthält keine Passwörter, Keys oder sensible Daten.
"""

from datetime import datetime, timedelta
from exchangelib import Account, Credentials, DELEGATE, CalendarItem, Task as EWSTask

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

    Returns:
        Liste von Dicts: [{subject, sender, body, datetime_received, is_read}, ...]
        Das letzte Element kann einen Sonderschlüssel "_skipped" enthalten.
    """
    inbox = account.inbox

    if unread_only:
        items = inbox.filter(is_read=False)
    else:
        items = inbox.all()

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


# ── Calendar ──────────────────────────────────────────────────────────────────

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


# ── Tasks ─────────────────────────────────────────────────────────────────────

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
