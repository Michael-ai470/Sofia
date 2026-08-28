"""Sofia — outbound email over SMTP. cPanel gives you a mailbox; use it."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from config import Config

log = logging.getLogger("sofia.mail")


def send(to: str, subject: str, text_body: str, html_body: str | None = None) -> bool:
    if not Config.SMTP_HOST:
        log.warning("SMTP is not configured; would have sent %r to %s", subject, to)
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = Config.MAIL_FROM
    message["To"] = to
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    context = ssl.create_default_context()
    try:
        if Config.SMTP_PORT == 465:
            with smtplib.SMTP_SSL(Config.SMTP_HOST, Config.SMTP_PORT,
                                  context=context, timeout=20) as server:
                if Config.SMTP_USER:
                    server.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
                server.send_message(message)
        else:
            with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=20) as server:
                server.starttls(context=context)
                if Config.SMTP_USER:
                    server.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
                server.send_message(message)
        return True
    except Exception:
        log.exception("Failed to send %r to %s", subject, to)
        return False


def send_reset_email(to: str, name: str | None, link: str) -> bool:
    first = (name or "").split(" ")[0] if name else "there"
    text = (
        f"Hi {first},\n\n"
        "Someone asked to reset the password on your Sofia account.\n\n"
        f"{link}\n\n"
        "The link works once and expires in an hour. If this was not you, "
        "ignore this email — nothing has changed.\n\n"
        "— Sofia"
    )
    html = (
        f"<p>Hi {first},</p>"
        "<p>Someone asked to reset the password on your Sofia account.</p>"
        f'<p><a href="{link}" style="display:inline-block;padding:12px 22px;'
        'background:#4F46E5;color:#fff;border-radius:8px;text-decoration:none;'
        'font-family:sans-serif">Choose a new password</a></p>'
        "<p style='color:#6B6F7B;font-size:14px'>The link works once and expires "
        "in an hour. If this was not you, ignore this email — nothing has changed.</p>"
    )
    return send(to, "Reset your Sofia password", text, html)
