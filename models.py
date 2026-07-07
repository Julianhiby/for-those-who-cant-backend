"""
Datenmodelle für "For Those Who Can't".

- Runner: eine Anmeldung (Solo oder Team)
- Sponsor: eine Spendenzusage pro Runde, an einen Runner gebunden
- LapEvent: eine vom GPS-Tracking-Anbieter gemeldete abgeschlossene Runde

Alles liegt in einer einzigen SQLite-Datei (database.db). Für den echten
Produktivbetrieb später einfach DATABASE_URL auf eine Postgres-Instanz
umstellen (siehe config.py) -- der Code selbst muss dafür nicht geändert
werden, da SQLModel/SQLAlchemy beides unterstützt.
"""

from datetime import datetime
from typing import Optional
import uuid

from sqlmodel import SQLModel, Field, Relationship


def new_id() -> str:
    return uuid.uuid4().hex[:12]


class Runner(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    bib_number: Optional[int] = Field(default=None, index=True)  # fortlaufende Startnummer (1, 2, 3, ...)
    name: str
    email: str
    type: str  # "solo" oder "team"
    team_name: Optional[str] = None
    team_size: Optional[int] = None
    lap_goal: Optional[int] = None
    gps_device_needed: bool = True
    dedication_name: Optional[str] = None  # "Ich laufe für ..." (Patenschaft)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    sponsors: list["Sponsor"] = Relationship(back_populates="runner")
    laps: list["LapEvent"] = Relationship(back_populates="runner")


class Sponsor(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    runner_id: str = Field(foreign_key="runner.id")
    sponsor_name: str
    sponsor_email: Optional[str] = None
    amount_per_lap: float  # Euro, die dieser Sponsor pro gelaufener Runde zahlt
    created_at: datetime = Field(default_factory=datetime.utcnow)

    runner: Runner = Relationship(back_populates="sponsors")


class LapEvent(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    runner_id: str = Field(foreign_key="runner.id")
    lap_number: int  # laufende Rundenzählung für diese:n Läufer:in
    recorded_at: datetime = Field(default_factory=datetime.utcnow)

    runner: Runner = Relationship(back_populates="laps")
