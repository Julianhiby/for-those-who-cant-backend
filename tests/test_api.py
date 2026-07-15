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


def _confirm_all_sponsors(client, runner_id):
    """Bestätigt alle Sponsor:innen eines Runners über den Double-Opt-in-Link
    (Token direkt aus der Test-DB gelesen -- die API gibt ihn nicht heraus)."""
    from sqlmodel import Session, select
    import app as app_module
    from models import Sponsor

    with Session(app_module.engine) as s:
        toks = [(sp.id, sp.confirm_token)
                for sp in s.exec(select(Sponsor).where(Sponsor.runner_id == runner_id)).all()]
    for sid, tok in toks:
        res = client.get(f"/api/sponsors/{sid}/confirm", params={"token": tok})
        assert res.status_code == 200, res.text
    return toks


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
        sponsors=[{"sponsor_name": "Oma", "sponsor_email": "oma@example.com",
                   "amount_per_lap": 2.5}],
    )
    runner = client.get(f"/api/runners/{data['id']}").json()
    assert runner["type"] == "team"
    assert runner["team_name"] == "Blitz"


def test_register_rejects_invalid_email(client):
    res = client.post("/api/register", json={**REG_SOLO, "email": "keine-mail"})
    assert res.status_code == 422


def test_register_rejects_sponsor_without_email(client):
    # Sponsor-E-Mail ist Pflicht (an sie geht die Bestätigungsmail).
    res = client.post("/api/register", json={
        **REG_SOLO, "sponsors": [{"sponsor_name": "Ohne Mail", "amount_per_lap": 1.0}],
    })
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

def test_unconfirmed_sponsors_count_as_pending_not_raised(client):
    # 2 €/Runde bei der Anmeldung, 3,50 € nachträglich = 5,50 € pro Runde.
    data = _register(client, sponsors=[
        {"sponsor_name": "A", "sponsor_email": "a@example.com", "amount_per_lap": 2.0}])
    rid = data["id"]
    assert client.post(
        f"/api/runners/{rid}/sponsors",
        json={"sponsor_name": "B", "sponsor_email": "b@example.com", "amount_per_lap": 3.5},
    ).status_code == 200

    for lap in (1, 2):
        assert client.post(
            "/api/webhook/lap", json={"runner_id": rid, "lap_number": lap}
        ).status_code == 200

    # Solange niemand bestätigt hat: alles "offen", nichts "gesichert".
    live = client.get("/api/live").json()
    assert live["totalLaps"] == 2
    assert live["fundsRaised"] == 0.0
    assert live["fundsPending"] == 11.0     # 2 Runden * (2,0 + 3,5)
    assert live["totalRunners"] == 1
    assert live["donationGoal"] == 25000


def test_confirmed_sponsors_count_as_raised(client):
    data = _register(client, sponsors=[
        {"sponsor_name": "A", "sponsor_email": "a@example.com", "amount_per_lap": 2.0}])
    rid = data["id"]
    client.post(f"/api/runners/{rid}/sponsors",
                json={"sponsor_name": "B", "sponsor_email": "b@example.com", "amount_per_lap": 3.5})
    for lap in (1, 2):
        client.post("/api/webhook/lap", json={"runner_id": rid, "lap_number": lap})

    _confirm_all_sponsors(client, rid)

    live = client.get("/api/live").json()
    assert live["fundsRaised"] == 11.0      # jetzt beide bestätigt -> gesichert
    assert live["fundsPending"] == 0.0


def test_confirm_with_wrong_token_keeps_sponsor_pending(client):
    from sqlmodel import Session, select
    import app as app_module
    from models import Sponsor

    data = _register(client, sponsors=[
        {"sponsor_name": "A", "sponsor_email": "a@example.com", "amount_per_lap": 2.0}])
    rid = data["id"]
    client.post("/api/webhook/lap", json={"runner_id": rid, "lap_number": 1})

    with Session(app_module.engine) as s:
        sp = s.exec(select(Sponsor).where(Sponsor.runner_id == rid)).first()
    res = client.get(f"/api/sponsors/{sp.id}/confirm", params={"token": "FALSCH"})
    assert res.status_code == 400

    live = client.get("/api/live").json()
    assert live["fundsRaised"] == 0.0       # unverändert offen
    assert live["fundsPending"] == 2.0


def test_confirm_is_idempotent(client):
    from sqlmodel import Session, select
    import app as app_module
    from models import Sponsor

    data = _register(client, sponsors=[
        {"sponsor_name": "A", "sponsor_email": "a@example.com", "amount_per_lap": 2.0}])
    rid = data["id"]
    with Session(app_module.engine) as s:
        sp = s.exec(select(Sponsor).where(Sponsor.runner_id == rid)).first()
        sid, tok = sp.id, sp.confirm_token
    assert client.get(f"/api/sponsors/{sid}/confirm", params={"token": tok}).status_code == 200
    # Zweiter Aufruf bleibt 200 ("schon bestätigt"), kein Fehler.
    again = client.get(f"/api/sponsors/{sid}/confirm", params={"token": tok})
    assert again.status_code == 200
    assert "bereits bestätigt" in again.text


def test_add_sponsor_unknown_runner_404(client):
    res = client.post(
        "/api/runners/gibtsnicht/sponsors",
        json={"sponsor_name": "X", "sponsor_email": "x@example.com", "amount_per_lap": 1},
    )
    assert res.status_code == 404


def test_webhook_unknown_runner_404(client):
    res = client.post("/api/webhook/lap", json={"runner_id": "nix", "lap_number": 1})
    assert res.status_code == 404


# --------------------------------------------------------------------------
# Runden-Scan-Station (/api/scan/lap)
# --------------------------------------------------------------------------

def test_scan_requires_token(client, scan_headers):
    data = _register(client)
    assert client.post("/api/scan/lap", json={"runner_id": data["id"]}).status_code == 401
    assert client.post(
        "/api/scan/lap", json={"runner_id": data["id"]},
        headers={"X-Scan-Token": "falsch"},
    ).status_code == 401
    assert client.post(
        "/api/scan/lap", json={"runner_id": data["id"]}, headers=scan_headers
    ).status_code == 200


def test_scan_unknown_runner_and_missing_ref(client, scan_headers):
    assert client.post(
        "/api/scan/lap", json={"runner_id": "gibtsnicht"}, headers=scan_headers
    ).status_code == 404
    assert client.post(
        "/api/scan/lap", json={"bib_number": 999}, headers=scan_headers
    ).status_code == 404
    assert client.post(
        "/api/scan/lap", json={}, headers=scan_headers
    ).status_code == 422


def test_scan_by_id_increments_laps(client, scan_headers):
    data = _register(client)
    rid = data["id"]
    r1 = client.post("/api/scan/lap", json={"runner_id": rid}, headers=scan_headers).json()
    assert r1["laps"] == 1 and r1["bib_number"] == data["bib_number"]
    r2 = client.post("/api/scan/lap", json={"runner_id": rid}, headers=scan_headers).json()
    assert r2["laps"] == 2
    assert client.get("/api/live").json()["totalLaps"] == 2


def test_scan_by_bib_number(client, scan_headers):
    data = _register(client)
    res = client.post(
        "/api/scan/lap", json={"bib_number": data["bib_number"]}, headers=scan_headers
    )
    assert res.status_code == 200 and res.json()["laps"] == 1


def test_scan_double_scan_guard(client, scan_headers, monkeypatch):
    import app as app_module
    # Guard aktivieren -> zweiter sofortiger Scan wird abgelehnt.
    monkeypatch.setattr(app_module.config, "LAP_MIN_INTERVAL_SECONDS", 60)
    data = _register(client)
    rid = data["id"]
    assert client.post("/api/scan/lap", json={"runner_id": rid}, headers=scan_headers).status_code == 200
    dup = client.post("/api/scan/lap", json={"runner_id": rid}, headers=scan_headers)
    assert dup.status_code == 409
    # Es blieb bei genau einer Runde.
    assert client.get("/api/live").json()["totalLaps"] == 1


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
        {"sponsor_name": "Oma", "sponsor_email": "oma@example.com", "amount_per_lap": 2.0},
        {"sponsor_name": "Firma", "sponsor_email": "firma@example.com", "amount_per_lap": 1.5},
    ])
    client.post("/api/webhook/lap", json={"runner_id": data["id"], "lap_number": 1})
    # Nur "Oma" bestätigen -> Admin muss bestätigt/offen getrennt zeigen.
    from sqlmodel import Session, select
    import app as app_module
    from models import Sponsor
    with Session(app_module.engine) as s:
        oma = s.exec(select(Sponsor).where(Sponsor.sponsor_name == "Oma")).first()
        sid, tok = oma.id, oma.confirm_token
    client.get(f"/api/sponsors/{sid}/confirm", params={"token": tok})

    body = client.get("/api/admin/participants", headers=admin_headers).json()
    assert body["count"] == 1
    p = body["participants"][0]
    assert p["email"] == "laeufer@example.com"   # Admin sieht die E-Mail
    assert p["laps"] == 1
    assert p["sponsor_count"] == 2
    assert p["per_lap_total"] == 3.5
    assert p["confirmed_per_lap"] == 2.0
    assert p["pending_per_lap"] == 1.5
    assert p["sponsor_confirmed_count"] == 1
    assert p["sponsor_pending_count"] == 1
    assert set(p["sponsor_names"]) == {"Oma", "Firma"}


def test_admin_csv_is_excel_ready(client, admin_headers):
    _register(client, name="Jürgen Müßig",
              sponsors=[{"sponsor_name": "Bäckerei", "sponsor_email": "baeck@example.com",
                         "amount_per_lap": 2.0}])
    res = client.get("/api/admin/participants.csv", headers=admin_headers)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    raw = res.content
    assert raw.startswith(b"\xef\xbb\xbf")             # UTF-8-BOM für Excel
    text = raw.decode("utf-8-sig")
    assert text.split("\r\n")[0].startswith("Startnummer;")   # Semikolon-Trennung
    assert "Jürgen Müßig" in text                      # Umlaute korrekt


def test_admin_reset_deletes_everything(client, admin_headers):
    _register(client, sponsors=[
        {"sponsor_name": "A", "sponsor_email": "a@example.com", "amount_per_lap": 1}])
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
