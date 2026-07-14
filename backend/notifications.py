"""
E-Mail-Versand: Anmeldebestätigung mit QR-Ticket.

Drei Versandwege (in dieser Reihenfolge, gesteuert über config):
  1) Resend (HTTP-API)  -> EMPFOHLEN. Funktioniert auch auf Render, weil es über
     HTTPS (Port 443) läuft -- im Gegensatz zu SMTP, das Render im Gratis-Plan
     blockiert. Aktiv, sobald RESEND_API_KEY gesetzt ist.
  2) SMTP  -> klassischer Mailserver (z. B. Gmail). Auf Render-Gratis nicht nutzbar.
  3) Dev-Modus  -> nichts konfiguriert: die E-Mail wird als HTML-Datei unter
     backend/dev_emails/ abgelegt statt verschickt.

Der QR-Code wird als *gehostetes Bild* eingebunden
(`{PUBLIC_BASE_URL}/api/qr/{id}.png`) -- das funktioniert mit der HTTP-API und wird
von Gmail & Co. angezeigt (data-URIs werden dort oft blockiert).

Alle Versandwege sind "best effort" und mit Timeout abgesichert: schlägt der
Versand fehl oder hängt, wird das nur protokolliert -- eine Anmeldung soll nie
daran scheitern oder blockieren.
"""

import json
import smtplib
import ssl
import urllib.error
import urllib.request
from datetime import datetime
from email.message import EmailMessage
from html import escape

import config

_TIMEOUT = 10  # Sekunden, für alle Netzwerk-Versandwege

# Ergebnis des letzten Versandversuchs (für /api/debug/status). Enthält keine
# Geheimnisse, nur z. B. "resend:ok" oder die Fehlermeldung der API.
last_email_result = "noch kein Versand"


def _ticket_url(runner) -> str:
    return f"{config.PUBLIC_BASE_URL}/api/ticket/{runner.id}"


def _sponsor_url(runner) -> str:
    return f"{config.PUBLIC_BASE_URL}/sponsor.html?runner={runner.id}"


def _qr_url(runner) -> str:
    return f"{config.PUBLIC_BASE_URL}/api/qr/{runner.id}.png"


def _button(href: str, label: str) -> str:
    """Ein gestylter Button (als <a>) im Event-Look."""
    return (
        f'<a href="{href}" style="display:inline-block;background:#E7B23E;'
        f'color:#100E1A;text-decoration:none;font-weight:700;padding:12px 22px;'
        f'border-radius:999px;margin:6px 8px 6px 0;font-size:0.95rem;">{label}</a>'
    )


def build_confirmation_email(runner) -> tuple[str, str, str]:
    """Gibt (Betreff, HTML-Text, Plain-Text) für die Bestätigungsmail zurück."""
    name = escape(runner.name)
    bib = escape(str(runner.bib_number or "—"))
    ticket_url = _ticket_url(runner)
    qr_url = _qr_url(runner)
    sponsor_url = _sponsor_url(runner)
    sponsor_button = _button(sponsor_url, "💛 Sponsor-Link öffnen & teilen")
    event = escape(config.EVENT_NAME)

    subject = f"Deine Anmeldung für {config.EVENT_NAME} · Startnummer {bib}"

    # Buttons: Ticket-Seite immer, Wallet-Buttons nur wenn tatsächlich eingerichtet.
    buttons = [_button(ticket_url, "🎟️ Startticket mit QR öffnen")]
    text_links = [f"- Startticket (QR-Seite): {ticket_url}"]

    if config.GOOGLE_WALLET_CONFIGURED:
        google_url = f"{config.PUBLIC_BASE_URL}/api/wallet/google/{runner.id}"
        buttons.append(_button(google_url, "🤖 Zu Google Wallet"))
        text_links.append(f"- Google Wallet: {google_url}")

    if config.APPLE_WALLET_CONFIGURED:
        apple_url = f"{config.PUBLIC_BASE_URL}/api/wallet/apple/{runner.id}"
        buttons.append(_button(apple_url, "🍏 Zu Apple Wallet"))
        text_links.append(f"- Apple Wallet: {apple_url}")

    buttons_html = "".join(buttons)
    text_links_str = "\n".join(text_links)

    html = f"""\
<div style="font-family:-apple-system,Segoe UI,Inter,sans-serif;max-width:520px;
     margin:0 auto;background:#100E1A;color:#EDE8DD;border-radius:16px;padding:32px;">
  <h1 style="font-size:1.4rem;margin:0 0 4px;">Danke, {name}! 🎉</h1>
  <p style="color:#9a94a8;margin:0 0 20px;">Deine Anmeldung für
     <strong style="color:#EDE8DD;">{event}</strong> ist gespeichert.</p>
  <p style="font-size:1rem;margin:0 0 24px;">Deine Startnummer:
     <strong style="color:#E7B23E;font-size:1.4rem;">{bib}</strong></p>

  <div style="background:#1a1730;border-radius:12px;padding:24px;margin-bottom:20px;
       text-align:center;">
    <p style="margin:0 0 16px;font-weight:600;">🎟️ Dein Startticket</p>
    <div style="background:#fff;display:inline-block;padding:12px;border-radius:12px;
         line-height:0;">
      <img src="{qr_url}" width="200" height="200" alt="QR-Code Check-in"
           style="display:block;width:200px;height:200px;">
    </div>
    <p style="color:#9a94a8;font-size:0.82rem;margin:14px 0 0;">
       Zeig diesen QR-Code beim Check-in am Start-/Zielbereich vor.</p>
  </div>

  <p style="margin:0 0 6px;font-weight:600;">So nutzt du dein Ticket:</p>
  <div style="margin-bottom:16px;">{buttons_html}</div>
  <p style="color:#9a94a8;font-size:0.85rem;margin:0;">
     Oder nutze einfach diese E-Mail als Bestätigung — der QR-Code oben genügt.
     Auf dem iPhone kannst du die Ticket-Seite über „Teilen → PDF sichern" ablegen.</p>

  <div style="background:#1a1730;border-radius:12px;padding:24px;margin-top:20px;">
    <p style="margin:0 0 8px;font-weight:600;">💛 Sammle Sponsor:innen</p>
    <p style="color:#9a94a8;font-size:0.88rem;margin:0 0 14px;">
       Teile deinen persönlichen Link mit Familie, Freunden und Firmen — sie sagen
       dort mit zwei Klicks einen Betrag pro gelaufener Runde zu. Jede Runde, die
       du läufst, wird so zur Spende.</p>
    {sponsor_button}
    <p style="color:#9a94a8;font-size:0.78rem;margin:12px 0 0;word-break:break-all;">
       {sponsor_url}</p>
  </div>

  <p style="color:#9a94a8;font-size:0.8rem;margin:24px 0 0;">
     Bis bald auf der Strecke! 🏃</p>
</div>"""

    text = f"""\
Danke, {runner.name}!

Deine Anmeldung für {config.EVENT_NAME} ist gespeichert.
Startnummer: {bib}

Dein Startticket:
{text_links_str}

Sammle Sponsor:innen -- teile deinen persönlichen Link mit Familie, Freunden
und Firmen (sie sagen dort einen Betrag pro gelaufener Runde zu):
{sponsor_url}

Der QR-Code auf der Ticket-Seite gilt als Check-in. Du kannst diese E-Mail auch
einfach als Bestätigung nutzen. Bis bald!
"""
    return subject, html, text


def _dispatch(to: str, subject: str, html: str, text: str, *, label: str) -> None:
    """Verschickt eine Mail über den ersten konfigurierten Weg
    (Resend -> SMTP -> Dev-Modus). Fehler werden abgefangen und protokolliert;
    im Fehlerfall (oder wenn nichts konfiguriert ist) wird die Mail lokal
    abgelegt. `label` beschreibt die Mail nur für das Log/last_email_result.
    Gemeinsame Basis für Läufer- und Sponsor-Mails."""
    global last_email_result
    try:
        if config.RESEND_CONFIGURED:
            _send_via_resend(to, subject, html, text)
            last_email_result = f"resend:ok ({label}) -> {to}"
            print(f"[email] Resend: {label} an {to} verschickt.")
            return
        if config.EMAIL_CONFIGURED:
            _send_via_smtp(to, subject, html, text)
            last_email_result = f"smtp:ok ({label}) -> {to}"
            print(f"[email] SMTP: {label} an {to} verschickt.")
            return
    except Exception as e:  # noqa: BLE001 -- Versand darf die Anmeldung nie umwerfen
        last_email_result = f"FEHLER ({label}) -> {to}: {e}"
        print(f"[email] WARNUNG: Versand ({label}) an {to} fehlgeschlagen: {e}")
        _save_dev_email(to, subject, html)
        return

    # Nichts konfiguriert -> Dev-Modus.
    last_email_result = f"dev-modus ({label}, kein Versand konfiguriert) -> {to}"
    _save_dev_email(to, subject, html)


def send_confirmation(runner) -> None:
    """Anmeldebestätigung mit QR-Ticket an die Läufer:in."""
    subject, html, text = build_confirmation_email(runner)
    _dispatch(runner.email, subject, html, text,
              label=f"Bestätigung Startnummer {runner.bib_number}")


def build_sponsor_confirmation_email(
    *, sponsor_name: str, amount_per_lap: float, runner_display_name: str,
    confirm_url: str,
) -> tuple[str, str, str]:
    """Gibt (Betreff, HTML, Plain-Text) für die Double-Opt-in-Mail an eine:n
    Sponsor:in zurück -- gleicher Event-Look wie die Läufer-Bestätigung."""
    name = escape(sponsor_name)
    runner = escape(runner_display_name)
    betrag = f"{amount_per_lap:.2f}".replace(".", ",")
    event = escape(config.EVENT_NAME)
    confirm_button = _button(confirm_url, "✅ Zusage jetzt bestätigen")

    subject = f"Bitte bestätige deine Sponsor-Zusage für {config.EVENT_NAME}"

    html = f"""\
<div style="font-family:-apple-system,Segoe UI,Inter,sans-serif;max-width:520px;
     margin:0 auto;background:#100E1A;color:#EDE8DD;border-radius:16px;padding:32px;">
  <h1 style="font-size:1.35rem;margin:0 0 12px;">Danke für deine Unterstützung, {name}! 💛</h1>
  <p style="color:#9a94a8;margin:0 0 16px;">Du möchtest <strong style="color:#EDE8DD;">{runner}</strong>
     beim Spendenlauf <strong style="color:#EDE8DD;">{event}</strong> mit
     <strong style="color:#E7B23E;">{betrag} € pro gelaufener Runde</strong> unterstützen.</p>
  <p style="margin:0 0 20px;">Damit deine Zusage in den Spendenstand zählt, bestätige
     sie bitte einmal mit einem Klick:</p>
  <div style="text-align:center;margin-bottom:20px;">{confirm_button}</div>
  <p style="color:#9a94a8;font-size:0.8rem;margin:0 0 6px;">Falls der Button nicht geht,
     kopiere diesen Link in deinen Browser:</p>
  <p style="color:#9a94a8;font-size:0.78rem;margin:0 0 20px;word-break:break-all;">{escape(confirm_url)}</p>
  <p style="color:#9a94a8;font-size:0.82rem;margin:0;">Deine Zusage ist eine
     Absichtserklärung, keine sofortige Zahlung. Nach dem Lauf melden wir uns mit
     der Rundenzahl und den Spendendetails. Wenn du diese Mail nicht erwartet hast,
     ignoriere sie einfach — dann zählt nichts.</p>
</div>"""

    text = f"""\
Danke für deine Unterstützung, {sponsor_name}!

Du möchtest {runner_display_name} beim Spendenlauf {config.EVENT_NAME} mit
{betrag} EUR pro gelaufener Runde unterstützen.

Damit deine Zusage in den Spendenstand zählt, bestätige sie bitte über diesen Link:
{confirm_url}

Deine Zusage ist eine Absichtserklärung, keine sofortige Zahlung. Nach dem Lauf
melden wir uns mit der Rundenzahl und den Spendendetails. Wenn du diese Mail nicht
erwartet hast, ignoriere sie einfach -- dann zählt nichts.
"""
    return subject, html, text


def send_sponsor_confirmation(
    *, sponsor_email: str, sponsor_name: str, amount_per_lap: float,
    runner_display_name: str, confirm_url: str,
) -> None:
    """Verschickt die Double-Opt-in-Mail an eine:n Sponsor:in (primitive Args,
    damit dies gefahrlos als BackgroundTask nach Session-Ende läuft)."""
    subject, html, text = build_sponsor_confirmation_email(
        sponsor_name=sponsor_name, amount_per_lap=amount_per_lap,
        runner_display_name=runner_display_name, confirm_url=confirm_url,
    )
    _dispatch(sponsor_email, subject, html, text, label="Sponsor-Bestätigung")


def _send_via_resend(to: str, subject: str, html: str, text: str) -> None:
    """Versand über die Resend-HTTP-API (POST /emails)."""
    payload = json.dumps({
        "from": config.RESEND_FROM,
        "to": [to],
        "subject": subject,
        "html": html,
        "text": text,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {config.RESEND_API_KEY}",
            "Content-Type": "application/json",
            # WICHTIG: Ohne eigenen User-Agent blockt die Cloudflare vor Resends
            # API den Standard-"Python-urllib" mit Fehler 1010 (403). Ein normaler
            # User-Agent kommt durch.
            "User-Agent": "ForThoseWhoCant-Backend/1.0",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as res:
            res.read()  # Antwort auslesen (enthält die Message-ID)
    except urllib.error.HTTPError as e:
        # Fehlermeldung der API mitnehmen (z. B. "nur an eigene Adresse erlaubt").
        detail = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"Resend HTTP {e.code}: {detail}") from e


def _send_via_smtp(to: str, subject: str, html: str, text: str) -> None:
    """Versand über einen SMTP-Server (mit Timeout, damit nichts hängen bleibt)."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{config.SMTP_FROM_NAME} <{config.SMTP_FROM}>"
    msg["To"] = to
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    if config.SMTP_PORT == 465:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT,
                              context=context, timeout=_TIMEOUT) as server:
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.send_message(msg)
    else:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=_TIMEOUT) as server:
            server.starttls(context=ssl.create_default_context())
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.send_message(msg)


def _save_dev_email(to: str, subject: str, html: str) -> None:
    """Legt die E-Mail als HTML-Datei ab (Dev-Modus / Fallback)."""
    config.DEV_EMAIL_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_to = to.replace("@", "_at_").replace("/", "_")
    path = config.DEV_EMAIL_DIR / f"{stamp}_{safe_to}.html"
    path.write_text(
        f"<!-- An: {to} | Betreff: {subject} -->\n{html}",
        encoding="utf-8",
    )
    print(f"[email:dev] Kein Versand konfiguriert -- E-Mail an {to} gespeichert unter: {path}")
