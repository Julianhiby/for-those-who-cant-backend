"""
Zentrale Konfiguration -- liest alles aus Umgebungsvariablen, damit keine
Geheimnisse (Zertifikate, Keys) im Code landen. Für lokale Entwicklung
kannst du eine .env-Datei anlegen (siehe .env.example).
"""

import os

# --- Datenbank -----------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./database.db")

# --- Event-Grunddaten ------------------------------------------------------
EVENT_NAME = os.getenv("EVENT_NAME", "For Those Who Can't")
LAP_DISTANCE_KM = float(os.getenv("LAP_DISTANCE_KM", "5.0"))

# --- Apple Wallet ----------------------------------------------------------
# Diese Dateien bekommst du erst, nachdem du dich im Apple Developer Program
# (kostenpflichtig, apple.com/developer) angemeldet und dort einen
# "Pass Type ID"-Zertifikat erstellt hast. Bis dahin bleibt der Wallet-
# Endpunkt inaktiv und gibt eine verständliche Fehlermeldung zurück.
APPLE_TEAM_ID = os.getenv("APPLE_TEAM_ID", "")
APPLE_PASS_TYPE_ID = os.getenv("APPLE_PASS_TYPE_ID", "")
APPLE_WWDR_CERT_PATH = os.getenv("APPLE_WWDR_CERT_PATH", "")
APPLE_SIGNER_CERT_PATH = os.getenv("APPLE_SIGNER_CERT_PATH", "")
APPLE_SIGNER_KEY_PATH = os.getenv("APPLE_SIGNER_KEY_PATH", "")
APPLE_SIGNER_KEY_PASSWORD = os.getenv("APPLE_SIGNER_KEY_PASSWORD", "")

# --- Google Wallet ----------------------------------------------------------
# Diese Datei bekommst du über die Google Wallet API Console (kostenlos):
# console.cloud.google.com -> Google Wallet API aktivieren -> Service-Account
# anlegen -> JSON-Schlüssel herunterladen.
GOOGLE_WALLET_ISSUER_ID = os.getenv("GOOGLE_WALLET_ISSUER_ID", "")
GOOGLE_SERVICE_ACCOUNT_JSON_PATH = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_PATH", "")

APPLE_WALLET_CONFIGURED = all([
    APPLE_TEAM_ID, APPLE_PASS_TYPE_ID,
    APPLE_WWDR_CERT_PATH, APPLE_SIGNER_CERT_PATH, APPLE_SIGNER_KEY_PATH,
])
GOOGLE_WALLET_CONFIGURED = all([
    GOOGLE_WALLET_ISSUER_ID, GOOGLE_SERVICE_ACCOUNT_JSON_PATH,
])
