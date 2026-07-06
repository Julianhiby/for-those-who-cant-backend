# For Those Who Can't -- Backend

Kleines Backend für Anmeldung, Sponsoren-pro-Runde und Live-Tracker-Daten.
Python (FastAPI) + SQLite. Lässt sich mit wenig Aufwand kostenlos hosten.

## Lokal starten

```bash
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

Danach läuft die API unter `http://localhost:8000`. Interaktive Doku (zum
Ausprobieren im Browser) automatisch unter `http://localhost:8000/docs`.

## Endpunkte

| Methode | Pfad                              | Zweck                                            |
|---------|-----------------------------------|---------------------------------------------------|
| POST    | `/api/register`                   | Neue Anmeldung (Solo/Team) inkl. Sponsoren        |
| POST    | `/api/runners/{id}/sponsors`      | Sponsor nachträglich hinzufügen                   |
| POST    | `/api/webhook/lap`                | Vom GPS-Anbieter aufgerufen: Runde abgeschlossen  |
| GET     | `/api/live`                       | Aggregierte Daten für den Live-Tracker            |
| GET     | `/api/wallet/apple/{id}`          | .pkpass-Datei (Apple Wallet)                      |
| GET     | `/api/wallet/google/{id}`         | Weiterleitung zu "Zu Google Wallet hinzufügen"    |

## Deployment (kostenlos/günstig, ohne eigenen Server)

Empfehlung: **Render.com** oder **Railway.app** -- beide erkennen ein
Python-Projekt automatisch.

1. Dieses `backend/`-Verzeichnis in ein eigenes GitHub-Repository pushen
2. Bei Render.com: "New -> Web Service" -> Repository auswählen
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
5. Umgebungsvariablen (siehe `.env.example`) im Render-Dashboard eintragen
6. Fertig -- du bekommst eine URL wie `https://for-those-who-cant.onrender.com`

**Falls ein vorheriger Deploy schon einmal fehlgeschlagen ist:** Beim erneuten
Versuch nicht einfach "Deploy" klicken, sondern über das Dropdown neben dem
Deploy-Button **"Clear build cache & deploy"** wählen -- sonst kann Render
noch die alten, kaputten Pakete des fehlgeschlagenen Builds wiederverwenden.

Diese URL trägst du danach in der Website (`index.html`) bei der Konstante
`API_BASE_URL` ein (siehe Kommentar dort) -- damit sprechen Anmeldeformular
und Live-Tracker automatisch mit diesem Backend statt mit den Beispieldaten.

**Datenbank:** Standardmäßig SQLite (eine einzelne Datei). Für den echten
24h-Betrieb mit vielen gleichzeitigen Anmeldungen empfiehlt sich eine
echte Postgres-Datenbank (Render bietet das kostenlos für kleine Projekte
an) -- dafür einfach `DATABASE_URL` in den Umgebungsvariablen auf die
Postgres-Verbindung umstellen, der Code selbst muss nicht geändert werden.

## Apple Wallet einrichten

1. Apple Developer Program beitreten (apple.com/developer, kostenpflichtig,
   ca. 99 $/Jahr)
2. Dort ein "Pass Type ID" Zertifikat erstellen
3. Drei Dateien exportieren: dein Signer-Zertifikat, den privaten Schlüssel,
   und das Apple WWDR-Zertifikat (Apple stellt dieses öffentlich bereit)
4. Pfade zu diesen drei Dateien in die Umgebungsvariablen eintragen
   (`APPLE_WWDR_CERT_PATH`, `APPLE_SIGNER_CERT_PATH`, `APPLE_SIGNER_KEY_PATH`)
5. `APPLE_TEAM_ID` und `APPLE_PASS_TYPE_ID` ebenfalls eintragen (beide
   findest du im Apple Developer Portal)

Ohne diese Schritte gibt `/api/wallet/apple/{id}` bewusst eine verständliche
Fehlermeldung zurück (HTTP 501), statt einen ungültigen Pass auszuliefern.

## Google Wallet einrichten (einfacher, kostenlos)

1. Google-Cloud-Projekt anlegen (console.cloud.google.com)
2. "Google Wallet API" aktivieren
3. Service-Account anlegen, JSON-Schlüssel herunterladen
4. Einmalig als Wallet-Issuer registrieren: console.cloud.google.com/wallet
5. `GOOGLE_WALLET_ISSUER_ID` und `GOOGLE_SERVICE_ACCOUNT_JSON_PATH` in den
   Umgebungsvariablen eintragen

## Sponsoren-pro-Runde -- wie die Zahlen zustande kommen

Jede:r Läufer:in kann bei der Anmeldung (oder später über einen eigenen
Link) beliebig viele Sponsoren eintragen, jeweils mit einem Betrag **pro
gelaufener Runde**. `/api/live` rechnet für jede:n Läufer:in:

```
gesammelt = abgeschlossene Runden × Summe(alle Sponsoren-Beträge pro Runde)
```

Die "abgeschlossenen Runden" kommen aus `/api/webhook/lap` -- diesen
Endpunkt muss dein GPS-Tracking-Anbieter aufrufen, sobald er erkennt, dass
jemand eine Runde beendet hat. Das genaue Format hängt vom jeweiligen
Anbieter ab; sobald du weißt, welchen Anbieter du nutzt, sag mir Bescheid,
dann passe ich `webhook_lap()` in `app.py` an dessen tatsächliches Format an.
