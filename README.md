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

## Lokal starten (ohne Docker — schnellster Loop)

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

Danach im Browser öffnen:
- **Website (Anmeldung + Live-Tracker):** http://localhost:8000
- API-Doku (Swagger): http://localhost:8000/docs
- Health-Check: http://localhost:8000/api/health

> Das Backend liefert die Website selbst aus — alles läuft unter **einer**
> Adresse, kein zweiter Server und keine CORS-Einstellungen nötig.

## Lokal mit Docker (prod-nah, mit eigener Postgres)

Alternative zum obigen Weg — nützlich, wenn du **wie auf Render** testen willst
(gleiche Linux-Umgebung) und eine **echte, dauerhafte Datenbank** statt der
flüchtigen SQLite brauchst. Voraussetzung: Docker Desktop installiert.

```bash
docker compose up --build
```

Danach: http://localhost:8000. Es startet die App **plus** eine lokale
Postgres-Datenbank; Anmeldungen/Startnummern bleiben über Neustarts erhalten
(Volume `pgdata`). Der Code ist per Volume eingehängt und läuft mit `--reload`,
Änderungen wirken also sofort. Stoppen mit `Strg+C`, Daten löschen mit
`docker compose down -v`.

> Hinweis: Docker macht den Test-Loop **nicht schneller** als der lokale
> `uvicorn`-Weg oben — es bringt Prod-Nähe und die lokale Postgres. Für echte
> E-Mails eine `.env` mit `RESEND_API_KEY` anlegen (sonst Dev-Modus).
>
> Unter **Windows** kann das automatische Neuladen (`--reload`) über den
> Bind-Mount manchmal Datei-Änderungen nicht mitbekommen. Falls eine Änderung
> nicht greift: Container kurz neu starten (`docker compose restart web`) oder
> für schnelles Iterieren einfach den lokalen `uvicorn`-Weg (ohne Docker) nutzen.

## Test-Lauf (Probelauf ohne echtes GPS)

So testest du den kompletten Ablauf lokal:

1. **Server starten** (siehe oben) und http://localhost:8000 öffnen.
2. **Anmelden:** Unten im Formular „Startplatz sichern". Du bekommst sofort
   Startnummer + Ticket-Link angezeigt.
3. **Ticket ansehen:** Auf „Startticket mit QR-Code öffnen" klicken —
   das ist die kostenlose Wallet-Alternative (funktioniert auf jedem Handy).
4. **Bestätigungs-E-Mail:** Ist kein SMTP eingerichtet, wird die E-Mail nicht
   verschickt, sondern unter `backend/dev_emails/` als HTML-Datei abgelegt —
   einfach im Browser öffnen, um sie zu prüfen.
5. **Runden simulieren:** In einem zweiten Terminal (Server weiterlaufen lassen):
   ```bash
   cd backend
   ..\.venv\Scripts\python.exe simulate.py
   ```
   Das Skript meldet Test-Läufer:innen an und lässt Runden hochzählen. Auf der
   Website siehst du Rundenzahl und Spendenstand live steigen.

### Wallet-Optionen im Überblick

| Option | Kostenlos? | Funktioniert auf | Status |
|--------|-----------|------------------|--------|
| **QR-Ticket** (`/api/ticket/{id}`) | ✅ ja | jedem Handy (iPhone: als PDF sichern) | **sofort einsatzbereit** |
| **Google Wallet** | ✅ ja | Android | Code fertig, braucht kostenloses Google-Cloud-Setup |
| **Apple Wallet** | ❌ nein (99 €/Jahr Apple Developer) | iPhone | Code fertig, braucht Apple-Zertifikate |

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

## Deployment auf Render (kostenlose öffentliche Test-URL)

Im Projekt liegt eine fertige [`render.yaml`](render.yaml) — damit brauchst du
nur zu klicken, nichts zu konfigurieren:

1. Kostenloses Konto anlegen auf [render.com](https://render.com) („Get Started",
   am einfachsten mit dem GitHub-Konto anmelden).
2. Oben rechts **New +** → **Blueprint**.
3. Das Repository **`for-those-who-cant-backend`** auswählen (ggf. Render einmal
   den Zugriff auf dein GitHub erlauben).
4. Render liest `render.yaml`, zeigt den Dienst **for-those-who-cant-backend** an
   → **Apply** / **Create** klicken.
5. Der erste Build dauert 2–4 Minuten. Danach steht deine öffentliche Adresse
   oben im Dashboard, etwa:
   **`https://for-those-who-cant-backend.onrender.com`**

Diese URL kannst du teilen — die Website, Anmeldung, Tickets und Live-Daten
laufen dann für alle im Internet.

**Gut zu wissen (kostenloser Plan):**
- Der Dienst schläft nach ~15 Min ohne Zugriff ein; der **erste** Aufruf danach
  dauert 30–50 Sek. (Ladebildschirm), danach wieder schnell.
- Die SQLite-Datenbank ist **nicht dauerhaft** — bei einem Neustart/Deploy können
  Anmeldungen verloren gehen. Für erste Tests ok. Für den echten Betrieb in
  Render eine kostenlose **Postgres**-Datenbank anlegen und deren
  `DATABASE_URL` als Umgebungsvariable eintragen (Code bleibt unverändert).

**Echte Bestätigungs-E-Mails aktivieren:** im Render-Dashboard unter
*Environment* die `SMTP_*`-Variablen setzen (siehe [`.env.example`](.env.example),
z. B. Gmail-App-Passwort). Ohne sie werden Anmeldungen gespeichert, aber keine
Mails verschickt.

> Alternativ manuell (ohne Blueprint): **New + → Web Service**, Repo wählen,
> Build `pip install -r requirements.txt`, Start
> `uvicorn app:app --app-dir backend --host 0.0.0.0 --port $PORT`.

## Änderungen / Git-Workflow

Nicht direkt auf `main` committen, sondern **pro Änderung ein Branch + Pull Request**:

```bash
git checkout -b feat/kurzer-name   # neuer Branch
# ... Änderungen, commit(s) ...
git push -u origin feat/kurzer-name
```

Danach auf GitHub den **Pull Request** öffnen (der Push-Befehl zeigt einen Link an),
Änderungen ansehen und per **Squash-Merge** nach `main` mergen. Vorteile:

- `main` bleibt stabil und deploybar; **Render deployt nur bei Merge nach `main`**
  (Branch-Pushes lösen keinen Deploy aus).
- Saubere Historie: **ein Commit pro Feature** auf `main`.
- Jede Änderung ist als Einheit reviewbar und rücknehmbar.

Einmalig empfohlen in den GitHub-Repo-Einstellungen (*Settings → Pull Requests*):
**„Allow squash merging"** aktiv, als Standard-Merge-Methode. Für benannte Stände
optional **Tags/Releases** (z. B. `v0.1 – Anmeldung + Tickets live`).
