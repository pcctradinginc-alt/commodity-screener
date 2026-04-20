"""
Email Sender — Gmail SMTP with STARTTLS
Nur HTML-Card als Body, KEIN JSON-Anhang standardmäßig
"""

import os
import json
import smtplib
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication


class EmailSender:
    def __init__(self, cfg):
        self.cfg = cfg
        self.gmail_user = os.environ.get("GMAIL_USER", "")
        self.gmail_password = os.environ.get("GMAIL_APP_PASSWORD", "")
        self.recipients = cfg.get("email", {}).get("recipients", [])
        self.subject_template = cfg.get("email", {}).get("subject_template", "[Screener] {segment} | {ticker} | {score}/10 | {date}")

    def send(self, html_body, recommendation, artifact=None):
        if not self.gmail_user or not self.gmail_password:
            print(" WARNING: Gmail credentials not set — skipping email")
            return False

        # Env-Secret hat Vorrang
        recipient_env = os.environ.get("RECIPIENT_EMAIL", "")
        if recipient_env:
            self.recipients = [recipient_env]

        seg = recommendation.get("segment", "unknown").upper()
        ticker = recommendation.get("symbol", "N/A")
        score = recommendation.get("conviction", 0)
        date = datetime.date.today().strftime("%Y-%m-%d")

        subject = self.subject_template.format(
            segment=seg, ticker=ticker, score=score, date=date
        )

        # Saubere Alternative-Struktur (besser für Gmail)
        msg = MIMEMultipart("alternative")
        msg["From"] = self.gmail_user
        msg["To"] = ", ".join(self.recipients)
        msg["Subject"] = subject

        # Plain-Text Fallback
        plain = MIMEText("Bitte HTML-Ansicht aktivieren.", "plain")
        html = MIMEText(html_body, "html")

        msg.attach(plain)
        msg.attach(html)

        # JSON-Anhang nur, wenn explizit gewünscht (für Debugging)
        if artifact and isinstance(artifact, dict):
            try:
                artifact_bytes = json.dumps(artifact, indent=2, ensure_ascii=False).encode("utf-8")
                attachment = MIMEApplication(artifact_bytes, _subtype="json")
                attachment.add_header(
                    "Content-Disposition",
                    "attachment",
                    filename=f"screener_run_{date}.json"
                )
                msg.attach(attachment)
                print("   → JSON-Artifact als Anhang beigefügt (Debug-Modus)")
            except Exception as e:
                print(f" Warning: could not attach artifact: {e}")

        # Sendeversuch mit Retry
        last_error = None
        for attempt in range(1, 4):
            try:
                with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(self.gmail_user, self.gmail_password)
                    server.sendmail(self.gmail_user, self.recipients, msg.as_string())
                print(f" Email sent to {self.recipients} (attempt {attempt})")
                return True
            except Exception as e:
                last_error = e
                print(f" Email error attempt {attempt}: {e}")
                time.sleep(10)

        print(f" Email failed after 3 attempts: {last_error}")
        return False
