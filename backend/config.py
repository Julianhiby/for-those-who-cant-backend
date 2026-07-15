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

# Spendenziel in Euro, für die Fortschrittsleiste auf der Website.
DONATION_GOAL = float(os.getenv("DONATION_GOAL", "25000"))

# Fehler-Monitoring über Sentry (optional). Ist SENTRY_DSN leer, ist das
# Monitoring komplett deaktiviert -- der Code läuft dann ohne Sentry weiter.
# DSN kostenlos auf sentry.io anlegen und hier bzw. bei Render eintragen.
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
SENTRY_ENVIRONMENT = os.getenv("SENTRY_ENVIRONMENT", "production")

# Admin-Passwort für die Zurücksetzen-Funktion (/api/admin). Ist es leer, ist
# das Zurücksetzen komplett deaktiviert -- so kann niemand versehentlich oder
# böswillig die Daten löschen.
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

# Separates Passwort für die Runden-Scan-Station (/scan.html -> /api/scan/lap).
# Bewusst getrennt vom ADMIN_TOKEN: Streckenposten-Helfer:innen können damit NUR
# Runden zählen, aber nichts löschen. Leer = Scan-Funktion deaktiviert.
SCAN_TOKEN = os.getenv("SCAN_TOKEN", "")

# Mindestabstand (Sekunden) zwischen zwei gezählten Runden derselben Startnummer
# -- schützt vor versehentlichem Doppel-Scannen. Eine echte Runde dauert mehrere
# Minuten, 20 s weist also keine legitime Runde ab.
LAP_MIN_INTERVAL_SECONDS = int(os.getenv("LAP_MIN_SECONDS", "20"))

# Datenbank. Standard: lokale SQLite-Datei. Für Produktion z. B. Neon/Postgres:
#   postgresql://user:pass@host/dbname?sslmode=require
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{(_PROJECT_ROOT / 'database.db').as_posix()}",
)

# Manche Anbieter (u. a. ältere Postgres-URLs) liefern das veraltete Schema
# "postgres://" -- SQLAlchemy 2 verlangt aber "postgresql://". Normalisieren.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

# True, sobald eine echte (nicht-SQLite) Datenbank genutzt wird.
DATABASE_IS_SQLITE = DATABASE_URL.startswith("sqlite")

# Öffentlich erreichbare Basis-URL (für Links in E-Mails, Tickets, Wallet).
# Reihenfolge: explizit gesetzte Variable > von Render automatisch gesetzte
# RENDER_EXTERNAL_URL > lokaler Standard. So funktionieren die Links auf Render
# ohne manuelles Eintragen der Domain.
PUBLIC_BASE_URL = (
    os.getenv("PUBLIC_BASE_URL")
    or os.getenv("RENDER_EXTERNAL_URL")
    or "http://localhost:8000"
).rstrip("/")


# --------------------------------------------------------------------------
# E-Mail (Anmeldebestätigung mit Ticket)
#
# Versandwege (in dieser Reihenfolge, siehe notifications.py):
#   1) Resend (HTTP-API)  -- EMPFOHLEN, funktioniert auch auf Render (Port 443).
#      Nur RESEND_API_KEY setzen. Ohne eigene Domain als Absender
#      "onboarding@resend.dev" nutzen (Resend-Testmodus: sendet nur an die
#      eigene Konto-Adresse).
#   2) SMTP  -- klassischer Mailserver (z. B. Gmail). ACHTUNG: Render blockiert
#      ausgehendes SMTP im Gratis-Plan, funktioniert dort also NICHT.
#   3) Dev-Modus  -- ist nichts konfiguriert, wird die Mail nicht verschickt,
#      sondern als HTML-Datei unter backend/dev_emails/ abgelegt.
# --------------------------------------------------------------------------

# 1) Resend (HTTP-API)
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM = os.getenv("RESEND_FROM", "") or f"{EVENT_NAME} <onboarding@resend.dev>"
RESEND_CONFIGURED = bool(RESEND_API_KEY)

# 2) SMTP (Fallback)
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "") or SMTP_USER or "no-reply@forthosewhocant-run.de"
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", EVENT_NAME)

EMAIL_CONFIGURED = bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)

# Ablage für Dev-Modus-E-Mails (wird bei Bedarf automatisch angelegt).
DEV_EMAIL_DIR = _PROJECT_ROOT / "backend" / "dev_emails"


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
