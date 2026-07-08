"""
Backend für "For Those Who Can't".

Startest du lokal mit:
    uvicorn app:app --reload --port 8000

Wichtigste Endpunkte:
    POST /api/register            -> neue Anmeldung (Solo/Team + Sponsoren)
    POST /api/runners/{id}/sponsors -> Sponsor nachträglich hinzufügen
    POST /api/webhook/lap          -> vom GPS-Anbieter aufgerufen, wenn eine Runde fertig ist
    GET  /api/live                 -> aggregierte Live-Daten für die Website (Leaderboard, Spendenstand)
    GET  /api/wallet/apple/{id}    -> .pkpass-Datei zum Download
    GET  /api/wallet/google/{id}   -> Weiterleitung zum "Zu Google Wallet hinzufügen"-Link

Siehe README.md für Deployment-Hinweise (Render/Railway) und wie du die
Wallet-Zertifikate einträgst.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import secrets

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr
from sqlmodel import SQLModel, Session, create_engine, select

from config import DATABASE_URL, DATABASE_IS_SQLITE, LAP_DISTANCE_KM, DONATION_GOAL
from models import Runner, Sponsor, LapEvent
from wallet import apple_wallet, google_wallet
import notifications
import ticket

# connect_args={"check_same_thread": False} ist SQLite-spezifisch -- bei Postgres
# würde dieses Argument einen Fehler werfen. Deshalb nur für SQLite setzen.
_engine_kwargs = {"echo": False}
if DATABASE_IS_SQLITE:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, **_engine_kwargs)


@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    yield


app = FastAPI(title="For Those Who Can't -- Backend", lifespan=lifespan)

# Erlaubt Anfragen von deiner Website. Für den echten Betrieb hier die genaue
# Domain eintragen, statt "*", sobald die Seite eine feste URL hat.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_session():
    with Session(engine) as session:
        yield session


# --------------------------------------------------------------------------
# Anmeldung
# --------------------------------------------------------------------------

class SponsorIn(BaseModel):
    sponsor_name: str
    sponsor_email: Optional[EmailStr] = None
    amount_per_lap: float


class RegisterIn(BaseModel):
    name: str
    email: EmailStr
    type: str  # "solo" | "team"
    team_name: Optional[str] = None
    team_size: Optional[int] = None
    lap_goal: Optional[int] = None
    gps_device_needed: bool = True
    sponsors: list[SponsorIn] = []


class RegisterOut(BaseModel):
    id: str
    bib_number: int
    name: str
    ticket_url: str
    wallet_apple_url: str
    wallet_google_url: str


@app.post("/api/register", response_model=RegisterOut)
def register(payload: RegisterIn, background_tasks: BackgroundTasks):
    with Session(engine) as session:
        # Nächste fortlaufende Startnummer bestimmen (höchste vorhandene + 1,
        # oder 1 bei der allerersten Anmeldung).
        max_bib = session.exec(
            select(Runner.bib_number).order_by(Runner.bib_number.desc())
        ).first()
        next_bib = (max_bib or 0) + 1

        runner = Runner(
            bib_number=next_bib,
            name=payload.name,
            email=payload.email,
            type=payload.type,
            team_name=payload.team_name,
            team_size=payload.team_size,
            lap_goal=payload.lap_goal,
            gps_device_needed=payload.gps_device_needed,
        )
        session.add(runner)
        session.commit()
        session.refresh(runner)

        for s in payload.sponsors:
            session.add(Sponsor(
                runner_id=runner.id,
                sponsor_name=s.sponsor_name,
                sponsor_email=s.sponsor_email,
                amount_per_lap=s.amount_per_lap,
            ))
        session.commit()

        # Bestätigungs-E-Mail im Hintergrund verschicken (bzw. im Dev-Modus
        # lokal ablegen). Läuft NACH der Antwort, damit die Anmeldung schnell
        # bleibt und ein Mailserver-Problem sie nie scheitern lässt.
        background_tasks.add_task(notifications.send_confirmation, runner)

        return RegisterOut(
            id=runner.id,
            bib_number=runner.bib_number,
            name=runner.name,
            ticket_url=f"/api/ticket/{runner.id}",
            wallet_apple_url=f"/api/wallet/apple/{runner.id}",
            wallet_google_url=f"/api/wallet/google/{runner.id}",
        )


# --------------------------------------------------------------------------
# Sponsoren nachträglich hinzufügen (z. B. über einen persönlichen Link,
# den der/die Läufer:in nach der Anmeldung per E-Mail bekommt)
# --------------------------------------------------------------------------

@app.post("/api/runners/{runner_id}/sponsors")
def add_sponsor(runner_id: str, payload: SponsorIn):
    with Session(engine) as session:
        runner = session.get(Runner, runner_id)
        if not runner:
            raise HTTPException(404, "Läufer:in nicht gefunden")
        sponsor = Sponsor(
            runner_id=runner_id,
            sponsor_name=payload.sponsor_name,
            sponsor_email=payload.sponsor_email,
            amount_per_lap=payload.amount_per_lap,
        )
        session.add(sponsor)
        session.commit()
        return {"ok": True, "sponsor_id": sponsor.id}


# --------------------------------------------------------------------------
# GPS-Webhook: wird vom Tracking-Anbieter aufgerufen, sobald eine Runde
# abgeschlossen wurde. Das genaue Format hängt von deinem GPS-Anbieter ab --
# passe runner_id/lap_number hier an dessen tatsächliches Webhook-Format an.
# --------------------------------------------------------------------------

class LapWebhookIn(BaseModel):
    runner_id: str
    lap_number: int


@app.post("/api/webhook/lap")
def webhook_lap(payload: LapWebhookIn):
    with Session(engine) as session:
        runner = session.get(Runner, payload.runner_id)
        if not runner:
            raise HTTPException(404, "Unbekannte runner_id")
        session.add(LapEvent(runner_id=payload.runner_id, lap_number=payload.lap_number))
        session.commit()
        return {"ok": True}


# --------------------------------------------------------------------------
# Live-Daten für die Website (ersetzt die Mock-Daten in fetchLiveData())
# --------------------------------------------------------------------------

@app.get("/api/live")
def live_data():
    with Session(engine) as session:
        runners = session.exec(select(Runner)).all()

        leaderboard = []
        total_laps = 0
        total_funds = 0.0

        for runner in runners:
            laps = session.exec(
                select(LapEvent).where(LapEvent.runner_id == runner.id)
            ).all()
            lap_count = len(laps)
            sponsors = session.exec(
                select(Sponsor).where(Sponsor.runner_id == runner.id)
            ).all()
            per_lap_total = sum(s.amount_per_lap for s in sponsors)
            raised = lap_count * per_lap_total

            total_laps += lap_count
            total_funds += raised

            leaderboard.append({
                "id": runner.id,
                "bib_number": runner.bib_number,
                "name": runner.name if runner.type == "solo" else (runner.team_name or runner.name),
                "type": runner.type,
                "laps": lap_count,
                "km": round(lap_count * LAP_DISTANCE_KM, 1),
                "raised": round(raised, 2),
            })

        leaderboard.sort(key=lambda r: r["laps"], reverse=True)

        return {
            "totalRunners": len(runners),
            "totalLaps": total_laps,
            "fundsRaised": round(total_funds, 2),
            "donationGoal": DONATION_GOAL,
            "leaderboard": leaderboard,
        }


# --------------------------------------------------------------------------
# Kostenloses QR-Ticket (funktioniert auf jedem Handy, ohne Wallet-Konto)
# --------------------------------------------------------------------------

@app.get("/api/ticket/{runner_id}", response_class=HTMLResponse)
def ticket_page(runner_id: str):
    with Session(engine) as session:
        runner = session.get(Runner, runner_id)
        if not runner:
            raise HTTPException(404, "Läufer:in nicht gefunden")
        return HTMLResponse(ticket.render_ticket_html(runner))


@app.get("/api/qr/{runner_id}.png")
def qr_image(runner_id: str):
    """QR-Code als PNG -- wird u. a. von der Bestätigungs-E-Mail eingebunden.
    Kodiert die Ticket-Seiten-URL, sodass ein Scan direkt das Ticket öffnet."""
    return Response(ticket.qr_png_bytes(ticket.qr_target(runner_id)), media_type="image/png")


@app.get("/api/debug/status")
def debug_status():
    """Kleiner Diagnose-Endpunkt (KEINE Geheimnisse) -- zeigt, welche Dienste
    konfiguriert sind und wie der letzte E-Mail-Versand ausging."""
    from config import (
        RESEND_CONFIGURED, EMAIL_CONFIGURED, DATABASE_IS_SQLITE, PUBLIC_BASE_URL,
        GOOGLE_WALLET_CONFIGURED, APPLE_WALLET_CONFIGURED,
    )
    return {
        "resend_configured": RESEND_CONFIGURED,
        "smtp_configured": EMAIL_CONFIGURED,
        "database_is_sqlite": DATABASE_IS_SQLITE,
        "public_base_url": PUBLIC_BASE_URL,
        "google_wallet_configured": GOOGLE_WALLET_CONFIGURED,
        "apple_wallet_configured": APPLE_WALLET_CONFIGURED,
        "last_email_result": notifications.last_email_result,
    }


# --------------------------------------------------------------------------
# Wallet-Pässe
# --------------------------------------------------------------------------

@app.get("/api/wallet/apple/{runner_id}")
def wallet_apple(runner_id: str):
    with Session(engine) as session:
        runner = session.get(Runner, runner_id)
        if not runner:
            raise HTTPException(404, "Läufer:in nicht gefunden")
        try:
            pkpass_bytes = apple_wallet.generate_pkpass(runner)
        except RuntimeError as e:
            raise HTTPException(501, str(e))
        return Response(
            content=pkpass_bytes,
            media_type="application/vnd.apple.pkpass",
            headers={"Content-Disposition": f'attachment; filename="{runner.id}.pkpass"'},
        )


@app.get("/api/wallet/google/{runner_id}")
def wallet_google(runner_id: str):
    with Session(engine) as session:
        runner = session.get(Runner, runner_id)
        if not runner:
            raise HTTPException(404, "Läufer:in nicht gefunden")
        try:
            url = google_wallet.generate_save_link(runner)
        except RuntimeError as e:
            raise HTTPException(501, str(e))
        return RedirectResponse(url)


# --------------------------------------------------------------------------
# Admin: Datenbank zurücksetzen (passwortgeschützt)
# --------------------------------------------------------------------------

@app.post("/api/admin/reset")
def admin_reset(x_admin_token: str = Header(default="")):
    """Löscht ALLE Anmeldungen, Sponsoren und Runden. Nur mit korrektem
    Admin-Passwort (ADMIN_TOKEN). Ist kein Passwort gesetzt, ist die Funktion
    komplett deaktiviert."""
    from config import ADMIN_TOKEN
    if not ADMIN_TOKEN:
        raise HTTPException(403, "Zurücksetzen ist nicht konfiguriert (ADMIN_TOKEN fehlt).")
    if not secrets.compare_digest(x_admin_token or "", ADMIN_TOKEN):
        raise HTTPException(401, "Falsches Admin-Passwort.")

    with Session(engine) as session:
        laps = session.exec(select(LapEvent)).all()
        sponsors = session.exec(select(Sponsor)).all()
        runners = session.exec(select(Runner)).all()
        for row in laps + sponsors + runners:
            session.delete(row)
        session.commit()

    return {"ok": True, "deleted": {
        "runners": len(runners), "sponsors": len(sponsors), "laps": len(laps),
    }}


@app.get("/api/admin", response_class=HTMLResponse)
def admin_page():
    """Kleine geschützte Admin-Seite mit dem Zurücksetzen-Knopf."""
    return HTMLResponse(_ADMIN_HTML)


_ADMIN_HTML = """<!doctype html>
<html lang="de"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Admin · For Those Who Can't</title>
<style>
  body{font-family:-apple-system,Segoe UI,Inter,sans-serif;background:#100E1A;color:#EDE8DD;
       display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:24px;}
  .card{background:#1a1730;border:1px solid rgba(237,232,221,.14);border-radius:18px;
        padding:32px;max-width:420px;width:100%;}
  h1{font-size:1.2rem;margin:0 0 6px;}
  p{color:#9a94a8;font-size:.9rem;margin:0 0 20px;}
  label{display:block;font-size:.75rem;letter-spacing:.1em;text-transform:uppercase;
        color:#9a94a8;margin-bottom:6px;}
  input{width:100%;padding:12px 14px;border-radius:10px;border:1px solid rgba(237,232,221,.2);
        background:#100E1A;color:#EDE8DD;font-size:1rem;box-sizing:border-box;margin-bottom:16px;}
  button{width:100%;padding:13px;border:0;border-radius:999px;font-weight:700;font-size:.95rem;
         cursor:pointer;background:#c0392b;color:#fff;}
  button:disabled{opacity:.5;cursor:default;}
  .msg{margin-top:16px;font-size:.9rem;line-height:1.5;display:none;}
  .msg.show{display:block;}
  .ok{color:#4ade80;} .err{color:#f87171;}
</style></head><body>
  <div class="card">
    <h1>Datenbank zurücksetzen</h1>
    <p>Löscht <strong>alle</strong> Anmeldungen, Sponsoren und Runden — unwiderruflich.
       Nur für den Übergang von Test zu echtem Betrieb gedacht.</p>
    <label for="token">Admin-Passwort</label>
    <input type="password" id="token" placeholder="ADMIN_TOKEN" autocomplete="off">
    <button id="btn">Alle Anmeldungen löschen</button>
    <div class="msg" id="msg"></div>
  </div>
<script>
  const btn=document.getElementById('btn'), msg=document.getElementById('msg');
  btn.addEventListener('click', async ()=>{
    const token=document.getElementById('token').value.trim();
    if(!token){ show('Bitte Admin-Passwort eingeben.','err'); return; }
    if(!confirm('Wirklich ALLE Anmeldungen unwiderruflich löschen?')) return;
    btn.disabled=true; btn.textContent='Wird gelöscht …';
    try{
      const res=await fetch('/api/admin/reset',{method:'POST',headers:{'X-Admin-Token':token}});
      const data=await res.json();
      if(!res.ok) throw new Error(data.detail||('Fehler '+res.status));
      const d=data.deleted;
      show('✓ Zurückgesetzt: '+d.runners+' Anmeldungen, '+d.sponsors+' Sponsoren, '+d.laps+' Runden gelöscht.','ok');
    }catch(e){ show('Fehlgeschlagen: '+e.message,'err'); }
    btn.disabled=false; btn.textContent='Alle Anmeldungen löschen';
  });
  function show(t,c){ msg.textContent=t; msg.className='msg show '+c; }
</script>
</body></html>"""


@app.get("/api/health")
def health():
    return {"status": "ok"}


# --------------------------------------------------------------------------
# Website ausliefern
# Das Frontend (../frontend) wird direkt vom Backend bedient. So läuft im Test
# alles unter einer Adresse (http://localhost:8000) -- ohne CORS-Probleme und
# ohne zweiten Server. Diese Zeilen stehen bewusst GANZ UNTEN, damit alle
# /api/...-Routen Vorrang vor dem statischen Katch-all haben.
# --------------------------------------------------------------------------

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
