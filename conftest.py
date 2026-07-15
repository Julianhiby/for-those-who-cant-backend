"""
Gemeinsame Test-Konfiguration (pytest).

Setzt VOR dem Import der App eine eigene, temporäre SQLite-Datenbank und ein
Test-Admin-Passwort -- so laufen die Tests komplett isoliert von der echten
Konfiguration und ohne Netzwerk.
"""

import os
import sys
import tempfile
from pathlib import Path

# backend/ auf den Importpfad legen, damit "import app" das Backend trifft
# (nicht den schlanken Wurzel-app.py-Wrapper).
_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT / "backend"))

# Umgebung für die Tests -- MUSS vor dem Import von config/app gesetzt sein.
_TMP_DB = Path(tempfile.gettempdir()) / "ftwc_test.db"
if _TMP_DB.exists():
    _TMP_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB.as_posix()}"
os.environ["ADMIN_TOKEN"] = "test-admin-token"
os.environ["SCAN_TOKEN"] = "test-scan-token"
os.environ["LAP_MIN_SECONDS"] = "0"       # Doppelscan-Guard in Tests aus
os.environ.pop("RESEND_API_KEY", None)   # sicher: kein echter Mailversand
os.environ.pop("SMTP_HOST", None)

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, select

import app as app_module
from models import Runner, Sponsor, LapEvent

ADMIN_TOKEN = "test-admin-token"

# Tabellen einmalig anlegen (sonst schlägt das Leeren vor dem ersten Client fehl).
SQLModel.metadata.create_all(app_module.engine)


@pytest.fixture(autouse=True)
def _no_email(monkeypatch):
    """Verhindert echten Mailversand/Datei-Schreiben; merkt sich die Aufrufe,
    damit Tests prüfen können, dass eine Bestätigung ausgelöst wurde."""
    calls = []
    monkeypatch.setattr(
        app_module.notifications, "send_confirmation", lambda runner: calls.append(runner)
    )
    # Sponsor-Bestätigungsmails (Double-Opt-in) ebenfalls neutralisieren -- sonst
    # würde der Hintergrund-Task in den Dev-Modus fallen und HTML-Dateien schreiben.
    monkeypatch.setattr(
        app_module.notifications, "send_sponsor_confirmation", lambda **kw: None
    )
    return calls


@pytest.fixture(autouse=True)
def _clean_db():
    """Leert die Tabellen vor jedem Test -> jeder Test startet frisch."""
    with Session(app_module.engine) as s:
        for model in (LapEvent, Sponsor, Runner):
            for row in s.exec(select(model)).all():
                s.delete(row)
        s.commit()
    yield


@pytest.fixture
def client():
    with TestClient(app_module.app) as c:
        yield c


@pytest.fixture
def admin_headers():
    return {"X-Admin-Token": ADMIN_TOKEN}


@pytest.fixture
def scan_headers():
    return {"X-Scan-Token": "test-scan-token"}
