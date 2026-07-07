# For Those Who Can't — Backend

Backend + Website für den Spendenlauf **„For Those Who Can't"**.
Läufer:innen melden sich an (Solo oder Team), sammeln Sponsoren (Betrag pro
Runde), ein GPS-Tracker meldet gelaufene Runden per Webhook, und die Website
zeigt live ein Leaderboard und den Spendenstand. Optional bekommt jede:r
Teilnehmer:in ein Startticket für Apple/Google Wallet.

## Projektstruktur

```
for-those-who-cant-backend/
├── backend/                 # FastAPI-Backend
│   ├── app.py               # API-Endpunkte
│   ├── models.py            # Datenbankmodelle (Runner, Sponsor, LapEvent)
│   ├── config.py            # Konfiguration aus Umgebungsvariablen / .env
│   └── wallet/
│       ├── apple_wallet.py  # .pkpass-Erzeugung
│       └── google_wallet.py # Google-Wallet-Link
├── frontend/
│   └── index.html           # Website
├── assets/                  # Icons/Logos für die Wallet-Pässe
├── requirements.txt
├── .env.example             # Vorlage für lokale Konfiguration
└── README.md
```

## Lokal starten

Voraussetzung: Python 3.9+ (unter Windows: `py`).

```bash
# 1. Virtuelle Umgebung anlegen und aktivieren
py -m venv .venv
.venv\Scripts\activate        # Windows (PowerShell/CMD)
# source .venv/bin/activate   # macOS/Linux

# 2. Abhängigkeiten installieren
pip install -r requirements.txt

# 3. Konfiguration anlegen (einmalig)
copy .env.example .env         # Windows
# cp .env.example .env         # macOS/Linux

# 4. Server starten (aus dem backend-Ordner)
cd backend
uvicorn app:app --reload --port 8000
```

Danach:
- API-Doku (Swagger): http://localhost:8000/docs
- Health-Check: http://localhost:8000/api/health

## Wichtigste API-Endpunkte

| Methode | Pfad | Zweck |
|---------|------|-------|
| POST | `/api/register` | Neue Anmeldung (Solo/Team + Sponsoren) |
| POST | `/api/runners/{id}/sponsors` | Sponsor nachträglich hinzufügen |
| POST | `/api/webhook/lap` | Vom GPS-Anbieter aufgerufen, wenn eine Runde fertig ist |
| GET | `/api/live` | Aggregierte Live-Daten (Leaderboard, Spendenstand) |
| GET | `/api/wallet/apple/{id}` | `.pkpass`-Datei zum Download |
| GET | `/api/wallet/google/{id}` | Weiterleitung zum Google-Wallet-Link |
| GET | `/api/health` | Statusprüfung |

## Konfiguration

Alle Einstellungen kommen aus Umgebungsvariablen (lokal aus `.env`).
Siehe [`.env.example`](.env.example) für die vollständige Liste.

- **Datenbank:** Standard ist eine lokale SQLite-Datei (`database.db`).
  Für Produktion `DATABASE_URL` auf eine Postgres-Instanz setzen — der Code
  bleibt gleich.
- **Apple Wallet:** Braucht ein (kostenpflichtiges) Apple Developer Program
  Konto und ein Pass Type ID Zertifikat. Ohne die Zertifikate liefert der
  Wallet-Endpunkt eine verständliche Fehlermeldung (HTTP 501).
- **Google Wallet:** Kostenlos. Google-Cloud-Projekt + Wallet API + Service
  Account nötig.

> ⚠️ Zertifikate, Schlüssel und die `.env` gehören **niemals** ins Git-Repo —
> die `.gitignore` schließt sie bereits aus.

## Deployment

Als ASGI-App deploybar auf z. B. [Render](https://render.com) oder
[Railway](https://railway.app):

- **Start-Befehl:** `uvicorn app:app --host 0.0.0.0 --port $PORT`
  (Arbeitsverzeichnis: `backend/`)
- **Umgebungsvariablen** im Hosting-Dashboard setzen (statt `.env`).
- Für persistente Daten in Produktion eine Postgres-Datenbank verbinden
  (`DATABASE_URL`).
