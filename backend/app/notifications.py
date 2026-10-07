"""Avisos por correo cuando una fuente se degrada.

Opcional: si no configuras SMTP en el `.env` simplemente no se envía nada
(el estado siempre se puede consultar en la pantalla de Diagnóstico).
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

log = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(settings.smtp_host and settings.notify_email)


def send(subject: str, body: str) -> bool:
    if not is_configured():
        log.info("Aviso no enviado (SMTP sin configurar): %s", subject)
        return False

    message = EmailMessage()
    message["Subject"] = f"[Columnistas] {subject}"
    message["From"] = settings.smtp_from or settings.smtp_user or settings.notify_email
    message["To"] = settings.notify_email
    message.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
            server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(message)
        return True
    except Exception as exc:  # noqa: BLE001 - un aviso fallido nunca rompe la app
        log.warning("No se pudo enviar el aviso por correo: %s", exc)
        return False
