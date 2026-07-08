# Container-Abbild für "For Those Who Can't".
# Baut dieselbe Umgebung wie auf Render (Python 3.11, Linux) -- so testest du
# lokal prod-nah. Start-Befehl identisch zu Render (Root-Einstiegspunkt app.py,
# der backend/app.py lädt).

FROM python:3.11-slim

# Python-Ausgabe direkt loggen (kein Buffering), keine .pyc-Dateien schreiben.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Abhängigkeiten zuerst -- so bleibt dieser Layer im Cache, solange sich
# requirements.txt nicht ändert (schnellere Rebuilds).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Restlicher Code (siehe .dockerignore, was NICHT hineinkopiert wird).
COPY . .

EXPOSE 8000

# PORT-tolerant: nutzt $PORT falls gesetzt (z. B. bei Hostern), sonst 8000.
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
