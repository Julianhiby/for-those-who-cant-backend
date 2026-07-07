"""
E-Mail-Versand: Anmeldebestätigung mit Ticket-Link.

Zwei Betriebsarten:
  1) SMTP konfiguriert (config.EMAIL_CONFIGURED) -> echte E-Mail wird verschickt.
  2) Nicht konfiguriert -> DEV-MODUS: die E-Mail wird NICHT verschickt, sondern
     als HTML-Datei unter backend/dev_emails/ gespeichert und in der Konsole
     protokolliert. So kannst du den kompletten Ablauf testen, ohne einen
     E-Mail-Anbieter einzurichten.

Der Versand wird bewusst "best effort" gehalten: schlägt er fehl, wird nur eine
Warnung protokolliert -- eine Anmeldung soll NICHT scheitern, nur weil der
Mailserver gerade nicht erreichbar ist.
"""

import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from html import escape

import config


def _ticket_url(runner) -> str:
    return f"{config.PUBLIC_BASE_URL}/api/ticket/{runner.id}"


def _google_wallet_url(runner) -> str:
    return f"{config.PUBLIC_BASE_URL}/api/wallet/google/{runner.id}"


def build_confirmation_email(runner) -> tuple[str, str, str]:
    """Gibt (Betreff, HTML-Text, Plain-Text) für die Bestätigungsmail zurück."""
    name = escape(runner.name)
    bib = escape(str(runner.bib_number or "—"))
    ticket_url = _ticket_url(runner)
    google_url = _google_wallet_url(runner)
    event = escape(config.EVENT_NAME)

    subject = f"Deine Anmeldung für {config.EVENT_NAME} · Startnummer {bib}"

    # Apple-Wallet-Zeile nur zeigen, wenn tatsächlich konfiguriert.
    apple_line_html = ""
    apple_line_text = ""
    if config.APPLE_WALLET_CONFIGURED:
        apple_url = f"{config.PUBLIC_BASE_URL}/api/wallet/apple/{runner.id}"
        apple_line_html = (
            f'<p style="margin:8px 0;">🍏 <a href="{apple_url}" '
            f'style="color:#E7B23E;">Zu Apple Wallet hinzufügen</a></p>'
        )
        apple_line_text = f"- Apple Wallet: {apple_url}\n"

    html = f"""\
<div style="font-family:-apple-system,Segoe UI,Inter,sans-serif;max-width:520px;
     margin:0 auto;background:#100E1A;color:#EDE8DD;border-radius:16px;
     padding:32px;">
  <h1 style="font-size:1.4rem;margin:0 0 4px;">Danke, {name}! 🎉</h1>
  <p style="color:#9a94a8;margin:0 0 20px;">Deine Anmeldung für
     <strong style="color:#EDE8DD;">{event}</strong> ist gespeichert.</p>
  <p style="font-size:1rem;margin:0 0 24px;">Deine Startnummer:
     <strong style="color:#E7B23E;font-size:1.4rem;">{bib}</strong></p>
  <div style="background:#1a1730;border-radius:12px;padding:20px;margin-bottom:20px;">
    <p style="margin:0 0 12px;font-weight:600;">🎟️ Dein Startticket</p>
    <p style="margin:8px 0;">📱 <a href="{ticket_url}" style="color:#E7B23E;">
       Ticket mit QR-Code öffnen</a> &nbsp;
       <span style="color:#9a94a8;font-size:.85rem;">(auf jedem Handy, iPhone: als PDF sichern)</span></p>
    <p style="margin:8px 0;">🤖 <a href="{google_url}" style="color:#E7B23E;">
       Zu Google Wallet hinzufügen</a></p>
    {apple_line_html}
  </div>
  <p style="color:#9a94a8;font-size:.85rem;margin:0;">Zeig den QR-Code beim Check-in
     am Start-/Zielbereich vor. Bis bald auf der Strecke!</p>
</div>"""

    text = f"""\
Danke, {runner.name}!

Deine Anmeldung für {config.EVENT_NAME} ist gespeichert.
Startnummer: {bib}

Dein Startticket:
- Ticket mit QR-Code: {ticket_url}
- Google Wallet: {google_url}
{apple_line_text}
Zeig den QR-Code beim Check-in am Start-/Zielbereich vor. Bis bald!
"""
    return subject, html, text


def send_confirmation(runner) -> None:
    """
    Verschickt die Bestätigungsmail (oder legt sie im Dev-Modus als Datei ab).
    Fehler werden abgefangen und nur protokolliert.
    """
    subject, html, text = build_confirmation_email(runner)

    if not config.EMAIL_CONFIGURED:
        _save_dev_email(runner.email, subject, html)
        return

    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{config.SMTP_FROM_NAME} <{config.SMTP_FROM}>"
        msg["To"] = runner.email
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")

        if config.SMTP_PORT == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, context=context) as server:
                server.login(config.SMTP_USER, config.SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
                server.starttls(context=ssl.create_default_context())
                server.login(config.SMTP_USER, config.SMTP_PASSWORD)
                server.send_message(msg)

        print(f"[email] Bestätigung an {runner.email} verschickt (Startnummer {runner.bib_number}).")
    except Exception as e:  # noqa: BLE001 -- Versand darf die Anmeldung nie umwerfen
        print(f"[email] WARNUNG: Versand an {runner.email} fehlgeschlagen: {e}")
        # Als Fallback trotzdem lokal ablegen, damit nichts verloren geht.
        _save_dev_email(runner.email, subject, html)


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
    print(f"[email:dev] Kein SMTP konfiguriert -- E-Mail an {to} gespeichert unter: {path}")
