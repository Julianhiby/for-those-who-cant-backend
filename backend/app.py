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
from typing import Optional

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlmodel import SQLModel, Session, create_engine, select

from config import DATABASE_URL, LAP_DISTANCE_KM
from models import Runner, Sponsor, LapEvent
from wallet import apple_wallet, google_wallet

engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})


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
    wallet_apple_url: str
    wallet_google_url: str


@app.post("/api/register", response_model=RegisterOut)
def register(payload: RegisterIn):
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

        return RegisterOut(
            id=runner.id,
            bib_number=runner.bib_number,
            name=runner.name,
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
            "leaderboard": leaderboard,
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


@app.get("/api/health")
def health():
    return {"status": "ok"}
