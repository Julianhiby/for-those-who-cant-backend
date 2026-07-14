"""
End-to-End-Tests der wichtigsten API-Wege: Anmeldung, Sponsoren, Runden,
Live-Aggregation, öffentliche Läufer-Infos, Admin-Schutz und -Export sowie
Ticket/QR. Läuft gegen eine temporäre SQLite-DB (siehe conftest.py).
"""

REG_SOLO = {"name": "Test Läufer", "email": "laeufer@example.com", "type": "solo"}


def _register(client, **overrides):
    payload = {**REG_SOLO, **overrides}
    res = client.post("/api/register", json=payload)
    assert res.status_code == 200, res.text
    return res.json()


# --------------------------------------------------------------------------
# Anmeldung
# --------------------------------------------------------------------------

def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_register_returns_bib_and_links(client, _no_email):
    data = _register(client)
    assert data["bib_number"] == 1
    assert data["name"] == "Test Läufer"
    assert data["ticket_url"] == f"/api/ticket/{data['id']}"
    assert data["wallet_google_url"].endswith(data["id"])
    # Bestätigungsmail wurde als Hintergrund-Task ausgelöst.
    assert len(_no_email) == 1


def test_bib_number_increments(client):
    a = _register(client, email="a@example.com")
    b = _register(client, email="b@example.com")
    c = _register(client, email="c@example.com")
    assert [a["bib_number"], b["bib_number"], c["bib_number"]] == [1, 2, 3]


def test_register_team_with_sponsors(client):
    data = _register(
        client, type="team", team_name="Blitz", team_size=4,
        sponsors=[{"sponsor_name": "Oma", "amount_per_lap": 2.5}],
    )
    runner = client.get(f"/api/runners/{data['id']}").json()
    assert runner["type"] == "team"
    assert runner["team_name"] == "Blitz"


def test_register_rejects_invalid_email(client):
    res = client.post("/api/register", json={**REG_SOLO, "email": "keine-mail"})
    assert res.status_code == 422


# --------------------------------------------------------------------------
# Öffentliche Läufer-Infos (Sponsor-Seite) -- KEINE E-Mail nach außen
# --------------------------------------------------------------------------

def test_get_runner_public_has_no_email(client):
    data = _register(client)
    runner = client.get(f"/api/runners/{data['id']}").json()
    assert "email" not in runner
    assert set(runner) == {"id", "name", "bib_number", "type", "team_name"}


def test_get_runner_unknown_404(client):
    assert client.get("/api/runners/gibtsnicht").status_code == 404


# --------------------------------------------------------------------------
# Sponsoren + Runden + Spendenstand
# --------------------------------------------------------------------------

def test_funds_are_sponsors_times_laps(client):
    # 2 €/Runde bei der Anmeldung, 3,50 € nachträglich = 5,50 € pro Runde.
    data = _register(client, sponsors=[{"sponsor_name": "A", "amount_per_lap": 2.0}])
    rid = data["id"]
    assert client.post(
        f"/api/runners/{rid}/sponsors",
        json={"sponsor_name": "B", "amount_per_lap": 3.5},
    ).status_code == 200

    # Ohne Runden noch 0 €.
    assert client.get("/api/live").json()["fundsRaised"] == 0

    # Zwei Runden -> 2 * 5,50 = 11,00 €.
    for lap in (1, 2):
        assert client.post(
            "/api/webhook/lap", json={"runner_id": rid, "lap_number": lap}
        ).status_code == 200

    live = client.get("/api/live").json()
    assert live["totalLaps"] == 2
    assert live["fundsRaised"] == 11.0
    assert live["totalRunners"] == 1
    assert live["donationGoal"] == 25000


def test_add_sponsor_unknown_runner_404(client):
    res = client.post(
        "/api/runners/gibtsnicht/sponsors",
        json={"sponsor_name": "X", "amount_per_lap": 1},
    )
    assert res.status_code == 404


def test_webhook_unknown_runner_404(client):
    res = client.post("/api/webhook/lap", json={"runner_id": "nix", "lap_number": 1})
    assert res.status_code == 404


# --------------------------------------------------------------------------
# Admin: Schutz, Teilnehmerliste, CSV, Reset
# --------------------------------------------------------------------------

def test_admin_requires_token(client, admin_headers):
    assert client.get("/api/admin/participants").status_code == 401
    assert client.get(
        "/api/admin/participants", headers={"X-Admin-Token": "falsch"}
    ).status_code == 401
    assert client.get("/api/admin/participants", headers=admin_headers).status_code == 200


def test_admin_participants_content(client, admin_headers):
    data = _register(client, sponsors=[
        {"sponsor_name": "Oma", "amount_per_lap": 2.0},
        {"sponsor_name": "Firma", "amount_per_lap": 1.5},
    ])
    client.post("/api/webhook/lap", json={"runner_id": data["id"], "lap_number": 1})

    body = client.get("/api/admin/participants", headers=admin_headers).json()
    assert body["count"] == 1
    p = body["participants"][0]
    assert p["email"] == "laeufer@example.com"   # Admin sieht die E-Mail
    assert p["laps"] == 1
    assert p["sponsor_count"] == 2
    assert p["per_lap_total"] == 3.5
    assert set(p["sponsor_names"]) == {"Oma", "Firma"}


def test_admin_csv_is_excel_ready(client, admin_headers):
    _register(client, name="Jürgen Müßig",
              sponsors=[{"sponsor_name": "Bäckerei", "amount_per_lap": 2.0}])
    res = client.get("/api/admin/participants.csv", headers=admin_headers)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    raw = res.content
    assert raw.startswith(b"\xef\xbb\xbf")             # UTF-8-BOM für Excel
    text = raw.decode("utf-8-sig")
    assert text.split("\r\n")[0].startswith("Startnummer;")   # Semikolon-Trennung
    assert "Jürgen Müßig" in text                      # Umlaute korrekt


def test_admin_reset_deletes_everything(client, admin_headers):
    _register(client, sponsors=[{"sponsor_name": "A", "amount_per_lap": 1}])
    res = client.post("/api/admin/reset", headers=admin_headers)
    assert res.json()["ok"] is True
    assert client.get("/api/live").json()["totalRunners"] == 0


# --------------------------------------------------------------------------
# Ticket / QR
# --------------------------------------------------------------------------

def test_ticket_page_renders(client):
    data = _register(client)
    res = client.get(f"/api/ticket/{data['id']}")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "Startticket" in res.text


def test_qr_endpoint_returns_png(client):
    data = _register(client)
    res = client.get(f"/api/qr/{data['id']}.png")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert res.content[:8] == b"\x89PNG\r\n\x1a\n"


# --------------------------------------------------------------------------
# E-Mail-Aufbau (ohne Versand) -- persönlicher Sponsor-Link muss drinstehen
# --------------------------------------------------------------------------

def test_confirmation_email_contains_links():
    import notifications

    class FakeRunner:
        id = "abc123"
        name = "Max"
        bib_number = 7
        type = "solo"
        team_name = None
        dedication_name = None
        email = "max@example.com"

    subject, html, text = notifications.build_confirmation_email(FakeRunner())
    assert "abc123" in subject or "Startnummer 7" in subject
    for needle in ("/api/ticket/abc123", "/api/qr/abc123.png", "/sponsor.html?runner=abc123"):
        assert needle in html
    assert "/sponsor.html?runner=abc123" in text
