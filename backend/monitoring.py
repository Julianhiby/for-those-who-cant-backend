"""
Fehler-Monitoring über Sentry -- optional und komplett no-op, wenn kein
SENTRY_DSN gesetzt ist.

Ist ein DSN konfiguriert (kostenloser Sentry-Account), werden unbehandelte
Server-Fehler automatisch mit Stacktrace erfasst und man bekommt eine
E-Mail-Benachrichtigung. Zusätzlich lassen sich gezielt "weiche" Probleme
melden (z. B. eine fehlgeschlagene Bestätigungsmail), die die App zwar nicht
zum Absturz bringen, die man aber trotzdem mitbekommen möchte.
"""

import config

_enabled = False


def init() -> None:
    """Sentry initialisieren, falls ein DSN gesetzt ist. Beim App-Start aufrufen."""
    global _enabled
    if not config.SENTRY_DSN:
        return
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=config.SENTRY_DSN,
            environment=config.SENTRY_ENVIRONMENT,
            # Nur Fehler erfassen (kein Performance-Tracing) und keine
            # personenbezogenen Daten automatisch mitschicken (DSGVO).
            traces_sample_rate=0.0,
            send_default_pii=False,
        )
        _enabled = True
        print(f"[monitoring] Sentry aktiv (environment={config.SENTRY_ENVIRONMENT}).")
    except Exception as e:  # noqa: BLE001 -- Monitoring darf den Start nie verhindern
        print(f"[monitoring] Sentry konnte nicht gestartet werden: {e}")


def capture_exception(exc: BaseException) -> None:
    """Einen abgefangenen Fehler an Sentry melden (falls aktiv)."""
    if not _enabled:
        return
    try:
        import sentry_sdk
        sentry_sdk.capture_exception(exc)
    except Exception:  # noqa: BLE001
        pass


def capture_message(message: str, level: str = "warning") -> None:
    """Eine Hinweis-/Warnmeldung an Sentry senden (falls aktiv)."""
    if not _enabled:
        return
    try:
        import sentry_sdk
        sentry_sdk.capture_message(message, level=level)
    except Exception:  # noqa: BLE001
        pass
