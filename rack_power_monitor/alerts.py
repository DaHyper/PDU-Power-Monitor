from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from rack_power_monitor.config import SmtpConfig


class EmailSender:
    def __init__(self, smtp: SmtpConfig) -> None:
        self.smtp = smtp

    @property
    def configured(self) -> bool:
        return bool(self.smtp.host and self.smtp.recipients)

    def send(self, subject: str, body: str) -> None:
        if not self.configured:
            return

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.smtp.from_address or self.smtp.username
        message["To"] = ", ".join(self.smtp.recipients)
        message.set_content(body)

        if self.smtp.security == "ssl":
            with smtplib.SMTP_SSL(self.smtp.host, self.smtp.port) as client:
                self._authenticate(client)
                client.send_message(message)
        else:
            with smtplib.SMTP(self.smtp.host, self.smtp.port) as client:
                if self.smtp.security == "tls":
                    client.starttls(context=ssl.create_default_context())
                self._authenticate(client)
                client.send_message(message)

    def _authenticate(self, client: smtplib.SMTP) -> None:
        if self.smtp.username:
            client.login(self.smtp.username, self.smtp.password)

    def send_test(self) -> None:
        self.send(
            subject="[Rack Power Monitor] Test alert",
            body="This is a test email from Rack Power Monitor. SMTP settings are working.",
        )
