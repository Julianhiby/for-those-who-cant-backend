"""
Apple Wallet (.pkpass) Erstellung.

Ein .pkpass ist technisch ein ZIP-Archiv mit:
  - pass.json        (Inhalt: Name, Startnummer, QR-Code, Farben, ...)
  - icon.png, logo.png (Bilder)
  - manifest.json    (SHA1-Hashes aller Dateien)
  - signature        (kryptografische Signatur über das Manifest)

Die Signatur kann NUR mit einem echten Apple-Zertifikat erzeugt werden
(Pass Type ID Zertifikat + privater Schlüssel + Apple WWDR-Zertifikat).
Diese bekommst du ausschließlich über ein aktives Apple Developer Program
Konto (kostenpflichtig). Ohne diese drei Dateien kann kein gültiger,
von iOS akzeptierter Pass erzeugt werden -- das ist eine Einschränkung
von Apple selbst, keine technische Lücke in diesem Code.

Sobald du die drei Zertifikatsdateien hast, trage ihre Pfade in die
Umgebungsvariablen aus config.py ein -- der Rest funktioniert dann ohne
weitere Codeänderungen.
"""

import hashlib
import json
import os
import subprocess
import tempfile
import zipfile
from io import BytesIO

from config import (
    APPLE_WALLET_CONFIGURED, APPLE_TEAM_ID, APPLE_PASS_TYPE_ID,
    APPLE_WWDR_CERT_PATH, APPLE_SIGNER_CERT_PATH, APPLE_SIGNER_KEY_PATH,
    APPLE_SIGNER_KEY_PASSWORD, EVENT_NAME,
)


def build_pass_json(runner) -> dict:
    """Der eigentliche Passinhalt -- Boarding-Pass-artiges Layout ("eventTicket")."""
    return {
        "formatVersion": 1,
        "passTypeIdentifier": APPLE_PASS_TYPE_ID,
        "teamIdentifier": APPLE_TEAM_ID,
        "serialNumber": runner.id,
        "organizationName": EVENT_NAME,
        "description": f"Startticket {EVENT_NAME}",
        "backgroundColor": "rgb(16,14,26)",
        "foregroundColor": "rgb(237,232,221)",
        "labelColor": "rgb(231,178,62)",
        "eventTicket": {
            "primaryFields": [
                {"key": "name", "label": "LÄUFER:IN", "value": runner.name}
            ],
            "secondaryFields": [
                {"key": "type", "label": "FORMAT", "value": "Solo" if runner.type == "solo" else "Team"},
                {"key": "bib", "label": "STARTNUMMER", "value": str(runner.bib_number or "—")},
            ],
            "backFields": [
                {"key": "info", "label": "Info", "value": "Zeig diesen Pass beim Check-in am Start-/Zielbereich vor."}
            ],
        },
        "barcodes": [{
            "message": runner.id,
            "format": "PKBarcodeFormatQR",
            "messageEncoding": "iso-8859-1",
        }],
    }


def _sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def generate_pkpass(runner, assets_dir: str = "assets") -> bytes:
    """
    Baut das .pkpass-Archiv und signiert es mit openssl (über die drei
    Zertifikatsdateien aus der Konfiguration). Gibt die fertigen Bytes zurück.

    Wirft RuntimeError mit einer klaren, verständlichen Meldung, falls die
    Zertifikate noch nicht konfiguriert sind.
    """
    if not APPLE_WALLET_CONFIGURED:
        raise RuntimeError(
            "Apple Wallet ist noch nicht eingerichtet. Dafür brauchst du ein "
            "Apple Developer Program Konto (apple.com/developer) und ein "
            "Pass Type ID Zertifikat. Trage die Zertifikatspfade danach in "
            "die Umgebungsvariablen ein (siehe config.py)."
        )

    pass_json = build_pass_json(runner)

    files: dict[str, bytes] = {
        "pass.json": json.dumps(pass_json, ensure_ascii=False).encode("utf-8"),
    }

    # Icon/Logo: falls im assets_dir vorhanden, sonst wird Apple das Pass
    # ablehnen -- icon.png ist ein Pflichtbestandteil jedes .pkpass.
    for fname in ("icon.png", "icon@2x.png", "logo.png", "logo@2x.png"):
        fpath = os.path.join(assets_dir, fname)
        if os.path.exists(fpath):
            with open(fpath, "rb") as f:
                files[fname] = f.read()

    manifest = {name: _sha1(content) for name, content in files.items()}
    manifest_bytes = json.dumps(manifest).encode("utf-8")
    files["manifest.json"] = manifest_bytes

    signature = _sign_manifest(manifest_bytes)
    files["signature"] = signature

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)

    return buffer.getvalue()


def _sign_manifest(manifest_bytes: bytes) -> bytes:
    """Signiert manifest.json per openssl smime (PKCS#7, wie von Apple gefordert)."""
    with tempfile.NamedTemporaryFile(suffix=".json") as manifest_file, \
         tempfile.NamedTemporaryFile(suffix=".sig") as sig_file:
        manifest_file.write(manifest_bytes)
        manifest_file.flush()

        cmd = [
            "openssl", "smime", "-binary", "-sign",
            "-certfile", APPLE_WWDR_CERT_PATH,
            "-signer", APPLE_SIGNER_CERT_PATH,
            "-inkey", APPLE_SIGNER_KEY_PATH,
            "-in", manifest_file.name,
            "-out", sig_file.name,
            "-outform", "DER",
        ]
        if APPLE_SIGNER_KEY_PASSWORD:
            cmd += ["-passin", f"pass:{APPLE_SIGNER_KEY_PASSWORD}"]

        subprocess.run(cmd, check=True, capture_output=True)
        sig_file.seek(0)
        return sig_file.read()
