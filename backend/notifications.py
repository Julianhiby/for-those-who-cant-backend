"""
E-Mail-Versand: Anmeldebestätigung mit QR-Ticket.

Zwei Betriebsarten:
  1) SMTP konfiguriert (config.EMAIL_CONFIGURED) -> echte E-Mail wird verschickt.
     Der QR-Code wird als *inline*-Bild (CID) angehängt -- so zeigen ihn Gmail,
     Apple Mail & Co. zuverlässig an (data-URIs werden in E-Mails oft blockiert).
  2) Nicht konfiguriert -> DEV-MODUS: die E-Mail wird NICHT verschickt, sondern
     als HTML-Datei unter backend/dev_emails/ gespeichert (QR als data-URI, damit
     die Datei beim Öffnen im Browser sofort den Code zeigt). Ideal zum Testen
     ohne E-Mail-Anbieter.

Der Versand ist bewusst "best effort": schlägt er fehl, wird nur eine Warnung
protokolliert -- eine Anmeldung soll NICHT scheitern, nur weil der Mailserver
gerade nicht erreichbar ist.
"""

import base64
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from email.utils import make_msgid
from html import escape

import config
import ticket


def _ticket_url(runner) -> str:
    return f"{config.PUBLIC_BASE_URL}/api/ticket/{runner.id}"


def _button(href: str, label: str) -> str:
    """Ein gestylter Button (als <a>) im Event-Look."""
    return (
        f'<a href="{href}" style="display:inline-block;background:#E7B23E;'
        f'color:#100E1A;text-decoration:none;font-weight:700;padding:12px 22px;'
        f'border-radius:999px;margin:6px 8px 6px 0;font-size:0.95rem;">{label}</a>'
    )


def build_confirmation_email(runner, qr_src: str) -> tuple[str, str, str]:
    """
    Gibt (Betreff, HTML-Text, Plain-Text) für die Bestätigungsmail zurück.

    `qr_src` ist die Bildquelle für den eingebetteten QR-Code -- beim echten
    Versand "cid:...", im Dev-Modus eine data-URI.
    """
    name = escape(runner.name)
    bib = escape(str(runner.bib_number or "—"))
    ticket_url = _ticket_url(runner)
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
      <img src="{qr_src}" width="200" height="200" alt="QR-Code Check-in"
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

  <p style="color:#9a94a8;font-size:0.8rem;margin:24px 0 0;">
     Bis bald auf der Strecke! 🏃</p>
</div>"""

    text = f"""\
Danke, {runner.name}!

Deine Anmeldung für {config.EVENT_NAME} ist gespeichert.
Startnummer: {bib}

Dein Startticket:
{text_links_str}

Der QR-Code auf der Ticket-Seite gilt als Check-in. Du kannst diese E-Mail auch
einfach als Bestätigung nutzen. Bis bald!
"""
    return subject, html, text


def send_confirmation(runner) -> None:
    """
    Verschickt die Bestätigungsmail (oder legt sie im Dev-Modus als Datei ab).
    Fehler werden abgefangen und nur protokolliert.
    """
    qr_png = ticket.qr_png_bytes(runner.id)

    # Dev-Modus: QR als data-URI einbetten und lokal speichern.
    if not config.EMAIL_CONFIGURED:
        data_uri = "data:image/png;base64," + base64.b64encode(qr_png).decode("ascii")
        subject, html, _ = build_confirmation_email(runner, data_uri)
        _save_dev_email(runner.email, subject, html)
        return

    # Echter Versand: QR als inline-Bild (CID) anhängen.
    image_cid = make_msgid(domain="ftwc")  # ergibt "<...@ftwc>"
    subject, html, text = build_confirmation_email(runner, f"cid:{image_cid[1:-1]}")

    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{config.SMTP_FROM_NAME} <{config.SMTP_FROM}>"
        msg["To"] = runner.email
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")
        # QR an den HTML-Teil als verwandtes inline-Bild hängen.
        msg.get_payload()[1].add_related(qr_png, "image", "png", cid=image_cid)

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
        # Fallback: trotzdem lokal ablegen, damit nichts verloren geht.
        data_uri = "data:image/png;base64," + base64.b64encode(qr_png).decode("ascii")
        _subject, _html, _ = build_confirmation_email(runner, data_uri)
        _save_dev_email(runner.email, _subject, _html)


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
