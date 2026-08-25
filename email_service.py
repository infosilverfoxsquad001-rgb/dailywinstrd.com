
import logging
import smtplib
from email.message import EmailMessage
from flask import current_app

log = logging.getLogger(__name__)

def send_email(to_email: str, subject: str, body: str) -> bool:
    host = current_app.config["SMTP_HOST"]
    if not host:
        log.warning("SMTP is not configured. Email not sent to %s.", to_email)
        log.info("EMAIL SUBJECT: %s\n%s", subject, body)
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = current_app.config["MAIL_FROM"]
    message["To"] = to_email
    message.set_content(body)

    try:
        if current_app.config["SMTP_USE_TLS"]:
            with smtplib.SMTP(host, current_app.config["SMTP_PORT"], timeout=20) as server:
                server.starttls()
                if current_app.config["SMTP_USERNAME"]:
                    server.login(
                        current_app.config["SMTP_USERNAME"],
                        current_app.config["SMTP_PASSWORD"],
                    )
                server.send_message(message)
        else:
            with smtplib.SMTP(host, current_app.config["SMTP_PORT"], timeout=20) as server:
                if current_app.config["SMTP_USERNAME"]:
                    server.login(
                        current_app.config["SMTP_USERNAME"],
                        current_app.config["SMTP_PASSWORD"],
                    )
                server.send_message(message)
        return True
    except Exception:
        log.exception("Could not send email to %s", to_email)
        return False
