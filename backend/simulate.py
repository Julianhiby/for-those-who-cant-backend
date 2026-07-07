"""
Test-Skript für einen Probelauf.

Meldet ein paar Beispiel-Läufer:innen an und simuliert dann laufend neue Runden,
damit du auf der Website siehst, wie Leaderboard, Rundenzahl und Spendenstand
live hochzählen -- ganz ohne echtes GPS-Gerät.

Voraussetzung: Der Server läuft bereits (in einem anderen Terminal):
    cd backend
    ..\.venv\Scripts\python.exe -m uvicorn app:app --reload --port 8000

Dann in einem zweiten Terminal:
    ..\.venv\Scripts\python.exe simulate.py

Abbrechen mit Strg+C.
"""

import json
import random
import time
import urllib.request

BASE = "http://localhost:8000"

TEST_RUNNERS = [
    {"name": "Mara Test", "email": "mara@example.com", "type": "solo",
     "sponsors": [{"sponsor_name": "Oma", "amount_per_lap": 5.0},
                  {"sponsor_name": "Firma X", "amount_per_lap": 10.0}]},
    {"name": "Jonas Test", "email": "jonas@example.com", "type": "solo",
     "sponsors": [{"sponsor_name": "Fußballverein", "amount_per_lap": 3.0}]},
    {"name": "Team Blitz", "email": "team@example.com", "type": "team",
     "team_name": "Blitz", "team_size": 4,
     "sponsors": [{"sponsor_name": "Sponsor A", "amount_per_lap": 8.0}]},
]


def _post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as res:
        return json.load(res)


def main() -> None:
    print("Melde Test-Läufer:innen an ...")
    runners = []
    for r in TEST_RUNNERS:
        data = _post("/api/register", r)
        runners.append(data)
        print(f"  #{data['bib_number']:<3} {data['name']}  ->  Ticket: {BASE}{data['ticket_url']}")

    print("\nSimuliere Runden (Strg+C zum Beenden) ...")
    lap_counter = {r["id"]: 0 for r in runners}
    try:
        while True:
            runner = random.choice(runners)
            lap_counter[runner["id"]] += 1
            _post("/api/webhook/lap", {
                "runner_id": runner["id"],
                "lap_number": lap_counter[runner["id"]],
            })
            print(f"  Runde {lap_counter[runner['id']]:<3} für {runner['name']}")
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nBeendet. Schau dir das Leaderboard auf der Website an!")


if __name__ == "__main__":
    main()
