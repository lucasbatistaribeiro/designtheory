"""Envio da edição por e-mail. Sem credenciais configuradas, não envia nada."""

from __future__ import annotations

import logging
import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

import requests

from newsletter.config import Config

log = logging.getLogger(__name__)


@dataclass
class DeliveryResult:
    sent: bool
    detail: str


def send(cfg: Config, subject: str, html: str, text: str) -> DeliveryResult:
    if not cfg.delivery.get("enabled", False):
        return DeliveryResult(False, "envio desativado no config.yml")

    recipients = cfg.recipients()
    if not recipients:
        return DeliveryResult(False, "nenhum destinatario configurado")

    provider = (cfg.delivery.get("provider") or "none").lower()
    sender = cfg.delivery.get("from") or os.environ.get("NEWSLETTER_FROM", "")

    if provider == "resend":
        return _send_resend(sender, recipients, subject, html, text)
    if provider == "smtp":
        return _send_smtp(sender, recipients, subject, html, text)
    return DeliveryResult(False, f"provider desconhecido: {provider}")


def _send_resend(sender: str, recipients: list[str], subject: str, html: str, text: str) -> DeliveryResult:
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        return DeliveryResult(False, "RESEND_API_KEY ausente")
    try:
        response = requests.post(
            "https://api.resend.com/emails",
            timeout=30,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": sender,
                "to": recipients,
                "subject": subject,
                "html": html,
                "text": text,
            },
        )
        response.raise_for_status()
    except Exception as exc:
        return DeliveryResult(False, f"erro no Resend: {exc}")
    return DeliveryResult(True, f"enviado via Resend para {len(recipients)} destinatario(s)")


def _send_smtp(sender: str, recipients: list[str], subject: str, html: str, text: str) -> DeliveryResult:
    host = os.environ.get("SMTP_HOST", "")
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASSWORD", "")
    port = int(os.environ.get("SMTP_PORT", "587"))
    if not host or not user or not password:
        return DeliveryResult(False, "SMTP_HOST/SMTP_USER/SMTP_PASSWORD ausentes")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender or user
    message["To"] = ", ".join(recipients)
    message.set_content(text)
    message.add_alternative(html, subtype="html")

    try:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(message)
    except Exception as exc:
        return DeliveryResult(False, f"erro no SMTP: {exc}")
    return DeliveryResult(True, f"enviado via SMTP para {len(recipients)} destinatario(s)")
