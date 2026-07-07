"""
Zentrale Konfiguration für "For Those Who Can't".

Alle Werte werden aus Umgebungsvariablen gelesen. Für die lokale Entwicklung
kannst du sie in eine Datei namens `.env` im Projektwurzelverzeichnis schreiben
(Vorlage: `.env.example`). Diese `.env` wird NICHT nach GitHub hochgeladen
(siehe `.gitignore`), damit keine Geheimnisse (Zertifikate, Schlüssel) im
öffentlichen Repo landen.

Wichtig: Der Code selbst muss beim Wechsel von lokal (SQLite) auf Produktion
(Postgres) oder beim Nachtragen der Wallet-Zertifikate NICHT geändert werden --
es genügt, hier die passenden Umgebungsvariablen zu setzen.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# .env aus dem Projektwurzelverzeichnis laden (eine Ebene über backend/),
# damit lokale Einstellungen automatisch greifen.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


# --------------------------------------------------------------------------
# Allgemein
# --------------------------------------------------------------------------

EVENT_NAME = os.getenv("EVENT_NAME", "For Those Who Can't")

# Länge einer Runde in Kilometern (für die km-Anzeige im Leaderboard).
LAP_DISTANCE_KM = float(os.getenv("LAP_DISTANCE_KM", "1.0"))

# Datenbank. Standard: lokale SQLite-Datei. Für Produktion z. B.:
#   postgresql+psycopg://user:pass@host:5432/dbname
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{(_PROJECT_ROOT / 'database.db').as_posix()}",
)


# --------------------------------------------------------------------------
# Apple Wallet
# Aktiv, sobald alle drei Zertifikatspfade gesetzt sind (Pass Type ID
# Zertifikat, privater Schlüssel, Apple WWDR-Zertifikat).
# --------------------------------------------------------------------------

APPLE_TEAM_ID = os.getenv("APPLE_TEAM_ID", "")
APPLE_PASS_TYPE_ID = os.getenv("APPLE_PASS_TYPE_ID", "")
APPLE_WWDR_CERT_PATH = os.getenv("APPLE_WWDR_CERT_PATH", "")
APPLE_SIGNER_CERT_PATH = os.getenv("APPLE_SIGNER_CERT_PATH", "")
APPLE_SIGNER_KEY_PATH = os.getenv("APPLE_SIGNER_KEY_PATH", "")
APPLE_SIGNER_KEY_PASSWORD = os.getenv("APPLE_SIGNER_KEY_PASSWORD", "")

APPLE_WALLET_CONFIGURED = all([
    APPLE_TEAM_ID,
    APPLE_PASS_TYPE_ID,
    APPLE_WWDR_CERT_PATH,
    APPLE_SIGNER_CERT_PATH,
    APPLE_SIGNER_KEY_PATH,
])


# --------------------------------------------------------------------------
# Google Wallet
# Aktiv, sobald Issuer-ID und der Pfad zur Service-Account-JSON gesetzt sind.
# --------------------------------------------------------------------------

GOOGLE_WALLET_ISSUER_ID = os.getenv("GOOGLE_WALLET_ISSUER_ID", "")
GOOGLE_SERVICE_ACCOUNT_JSON_PATH = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_PATH", "")

GOOGLE_WALLET_CONFIGURED = bool(
    GOOGLE_WALLET_ISSUER_ID and GOOGLE_SERVICE_ACCOUNT_JSON_PATH
)
