"""
Kostenloses QR-Ticket als HTML-Seite.

Funktioniert auf jedem Smartphone sofort -- ohne Apple-Developer-Konto und ohne
Google-Cloud-Setup. Der/die Läufer:in kann die Seite auf dem iPhone über
"Teilen -> PDF sichern" oder "Zum Home-Bildschirm" ablegen. Der QR-Code enthält
dieselbe Läufer-ID wie die Wallet-Pässe, sodass der Check-in-Scan identisch ist.

Der QR-Code wird lokal mit der 'qrcode'-Bibliothek erzeugt und als Base64-PNG
direkt in die Seite eingebettet -- es wird also KEIN externer QR-Dienst
aufgerufen (gut für Datenschutz und Offline-Nutzung).
"""

import base64
from io import BytesIO
from html import escape

import qrcode

import config
from config import EVENT_NAME


def qr_target(runner_id: str) -> str:
    """Der Inhalt, den der QR-Code kodiert: die Ticket-Seite dieser Person.
    So öffnet ein Scan (Handy-Kamera ODER Check-in-Scanner) direkt das Ticket --
    statt nur eine nackte ID anzuzeigen."""
    return f"{config.PUBLIC_BASE_URL}/api/ticket/{runner_id}"


def qr_png_bytes(payload: str) -> bytes:
    """Erzeugt einen QR-Code und gibt ihn als PNG-Bytes zurück."""
    img = qrcode.make(payload, box_size=8, border=2)
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def _qr_data_uri(payload: str) -> str:
    """Erzeugt einen QR-Code und gibt ihn als 'data:image/png;base64,...' zurück."""
    encoded = base64.b64encode(qr_png_bytes(payload)).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def render_ticket_html(runner) -> str:
    """Baut die vollständige HTML-Ticket-Seite für eine:n Läufer:in."""
    qr = _qr_data_uri(qr_target(runner.id))
    name = escape(runner.name)
    bib = escape(str(runner.bib_number or "—"))
    fmt = "Solo" if runner.type == "solo" else f"Team: {escape(runner.team_name or '')}"
    event = escape(EVENT_NAME)

    return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Startticket · {event}</title>
<style>
  :root {{
    --bg:#100E1A; --card:#1a1730; --paper:#EDE8DD; --paper-dim:#9a94a8;
    --gold:#E7B23E; --line:rgba(237,232,221,.14);
  }}
  * {{ box-sizing:border-box; }}
  body {{
    margin:0; min-height:100vh; background:var(--bg); color:var(--paper);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif;
    display:flex; align-items:center; justify-content:center; padding:24px;
  }}
  .ticket {{
    width:100%; max-width:420px; background:var(--card);
    border:1px solid var(--line); border-radius:22px; overflow:hidden;
    box-shadow:0 20px 60px rgba(0,0,0,.5);
  }}
  .head {{
    padding:22px 26px; border-bottom:1px dashed var(--line);
    display:flex; justify-content:space-between; align-items:flex-start;
  }}
  .event {{ font-weight:700; letter-spacing:.03em; line-height:1.15; font-size:.95rem; }}
  .event span {{ color:var(--gold); }}
  .badge {{
    font-size:.62rem; letter-spacing:.14em; text-transform:uppercase;
    color:var(--gold); border:1px solid var(--gold); border-radius:999px;
    padding:5px 10px; white-space:nowrap;
  }}
  .body {{ padding:26px; text-align:center; }}
  .qr {{
    background:#fff; padding:14px; border-radius:16px; display:inline-block;
    line-height:0; margin-bottom:20px;
  }}
  .qr img {{ width:200px; height:200px; display:block; }}
  .name {{ font-size:1.5rem; font-weight:700; margin:0 0 4px; }}
  .rows {{ margin-top:20px; text-align:left; }}
  .row {{
    display:flex; justify-content:space-between; gap:16px;
    padding:11px 0; border-top:1px solid var(--line);
  }}
  .row .k {{ font-size:.7rem; letter-spacing:.12em; text-transform:uppercase; color:var(--paper-dim); }}
  .row .v {{ font-weight:600; text-align:right; }}
  .bib .v {{ color:var(--gold); font-size:1.1rem; }}
  .foot {{
    padding:18px 26px 24px; border-top:1px dashed var(--line);
    font-size:.72rem; color:var(--paper-dim); text-align:center; line-height:1.5;
  }}
  @media print {{ body {{ background:#fff; }} .ticket {{ box-shadow:none; }} }}
</style>
</head>
<body>
  <div class="ticket">
    <div class="head">
      <div class="event">FOR THOSE<br><span>WHO CAN'T</span></div>
      <div class="badge">Startticket</div>
    </div>
    <div class="body">
      <div class="qr"><img src="{qr}" alt="QR-Code Check-in"></div>
      <p class="name">{name}</p>
      <div class="rows">
        <div class="row bib"><span class="k">Startnummer</span><span class="v">{bib}</span></div>
        <div class="row"><span class="k">Format</span><span class="v">{fmt}</span></div>
      </div>
    </div>
    <div class="foot">
      Zeig diesen QR-Code beim Check-in am Start-/Zielbereich vor.<br>
      Auf dem iPhone: Teilen → „PDF sichern" oder „Zum Home-Bildschirm".
    </div>
  </div>
</body>
</html>"""
