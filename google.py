"""
Google Wallet -- deutlich einfacher als Apple, weil kein eigenes Zertifikat
gekauft werden muss. Du brauchst nur (kostenlos):
  1) Ein Google-Cloud-Projekt
  2) Darin die "Google Wallet API" aktivieren
  3) Einen Service-Account anlegen und dessen JSON-Schlüssel herunterladen
  4) Dich einmalig als "Google Wallet Issuer" registrieren (ebenfalls kostenlos,
     console.cloud.google.com/wallet)

Mit der Service-Account-Datei wird hier ein JWT erzeugt, das man in einen
"Zu Google Wallet hinzufügen"-Link einbaut. Der Nutzer klickt den Link auf
seinem Handy, und die Karte landet direkt im Wallet -- kein Zertifikatsbau
wie bei Apple nötig.
"""

import json
import time

import jwt

from config import (
    GOOGLE_WALLET_CONFIGURED, GOOGLE_WALLET_ISSUER_ID,
    GOOGLE_SERVICE_ACCOUNT_JSON_PATH, EVENT_NAME,
)

CLASS_SUFFIX = "for_those_who_cant_ticket"


def _load_service_account() -> dict:
    with open(GOOGLE_SERVICE_ACCOUNT_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def build_generic_object(runner) -> dict:
    """Die eigentliche Wallet-Karte (Objekt) für eine:n Läufer:in."""
    return {
        "id": f"{GOOGLE_WALLET_ISSUER_ID}.{runner.id}",
        "classId": f"{GOOGLE_WALLET_ISSUER_ID}.{CLASS_SUFFIX}",
        "state": "ACTIVE",
        "cardTitle": {"defaultValue": {"language": "de", "value": EVENT_NAME}},
        "header": {"defaultValue": {"language": "de", "value": runner.name}},
        "subheader": {
            "defaultValue": {
                "language": "de",
                "value": "Solo" if runner.type == "solo" else f"Team: {runner.team_name or ''}",
            }
        },
        "textModulesData": [
            {"header": "STARTNUMMER", "body": runner.id.upper()},
            {"header": "ICH LAUFE FÜR", "body": runner.dedication_name or "wird zugeteilt"},
        ],
        "barcode": {"type": "QR_CODE", "value": runner.id},
        "hexBackgroundColor": "#100E1A",
    }


def generate_save_link(runner) -> str:
    """
    Gibt eine fertige "Zu Google Wallet hinzufügen"-URL zurück.
    Wirft RuntimeError mit verständlicher Meldung, falls noch nicht konfiguriert.
    """
    if not GOOGLE_WALLET_CONFIGURED:
        raise RuntimeError(
            "Google Wallet ist noch nicht eingerichtet. Aktiviere dazu die "
            "Google Wallet API in der Google Cloud Console, lege einen "
            "Service-Account an und trage den Pfad zur JSON-Schlüsseldatei "
            "sowie deine Issuer-ID in die Umgebungsvariablen ein."
        )

    service_account = _load_service_account()
    payload = {
        "iss": service_account["client_email"],
        "aud": "google",
        "typ": "savetowallet",
        "iat": int(time.time()),
        "payload": {"genericObjects": [build_generic_object(runner)]},
    }
    token = jwt.encode(payload, service_account["private_key"], algorithm="RS256")
    return f"https://pay.google.com/gp/v/save/{token}"
