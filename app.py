"""
ASGI-Einstiegspunkt für das Deployment.

Manche Hosting-Konfigurationen (u. a. der bereits bestehende Render-Service)
starten die App mit `uvicorn app:app` vom PROJEKTWURZELVERZEICHNIS aus -- also
nicht aus dem backend/-Ordner. Damit dieser Befehl funktioniert, liegt hier ein
schlanker Einstiegspunkt, der den eigentlichen Code aus backend/app.py lädt und
dessen FastAPI-Instanz `app` weiterreicht.

Der eigentliche Anwendungscode bleibt vollständig in backend/. Lokal kannst du
weiterhin direkt aus dem backend/-Ordner starten
(`uvicorn app:app --app-dir backend`) -- dieser Wrapper ändert daran nichts.
"""

import importlib.util
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent / "backend"

# backend/ auf den Importpfad legen, damit config, models, wallet, notifications
# und ticket beim Laden von backend/app.py gefunden werden.
sys.path.insert(0, str(_BACKEND))

# backend/app.py unter eigenem Modulnamen laden (NICHT "app", sonst würde es mit
# dieser Datei kollidieren) und die darin definierte FastAPI-App übernehmen.
_spec = importlib.util.spec_from_file_location("ftwc_backend_app", _BACKEND / "app.py")
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

app = _module.app
