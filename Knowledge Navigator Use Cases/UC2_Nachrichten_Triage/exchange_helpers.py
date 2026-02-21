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
        try:
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
        except Exception:
            # Einzelne fehlerhafte Items (z.B. Kalendereinladungen) überspringen
            continue

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
        f"Von: {email_dict.get('sender', 'Unbekannt')}\n"
        f"Betreff: {email_dict.get('subject', '(kein Betreff)')}\n"
        f"Datum: {dt_str}\n\n"
        f"{email_dict.get('body', '')}"
    )
