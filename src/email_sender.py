"""
Email Sender — Gmail SMTP with STARTTLS
Sends HTML Trading Card as email body + JSON artifact as attachment
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
        self.recipients = cfg["email"]["recipients"]
        self.subject_template = cfg["email"]["subject_template"]

    def send(self, html_body, recommendation, artifact=None):
        if not self.gmail_user or not self.gmail_password:
            print("  WARNING: Gmail credentials not set — skipping email")
            return False

        # Read recipient from env (GitHub Secret) or fall back to config
        recipient_env = os.environ.get("RECIPIENT_EMAIL", "")
        if recipient_env:
            self.recipients = [recipient_env]

        seg = recommendation.get("segment", "unknown").upper()
        ticker = recommendation.get("symbol", "N/A")
        score = recommendation.get("conviction", 0)
        date = datetime.date.today().strftime("%Y-%m-%d")

        subject = self.subject_template.format(
            segment=seg,
            ticker=ticker,
            score=score,
            date=date,
        )

        msg = MIMEMultipart("mixed")
        msg["From"] = self.gmail_user
        msg["To"] = ", ".join(self.recipients)
        msg["Subject"] = subject

        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText("Bitte HTML-Ansicht aktivieren.", "plain"))
        alt.attach(MIMEText(html_body, "html"))
        msg.attach(alt)

        if artifact:
            try:
                artifact_bytes = json.dumps(artifact, indent=2).encode("utf-8")
                attachment = MIMEApplication(artifact_bytes, _subtype="json")
                attachment.add_header(
                    "Content-Disposition",
                    "attachment",
                    filename=f"screener_run_{date}.json",
                )
                msg.attach(attachment)
            except Exception as e:
                print(f"  Warning: could not attach artifact: {e}")

        last_error = None
        for attempt in range(1, 4):
            try:
                with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(self.gmail_user, self.gmail_password)
                    server.sendmail(self.gmail_user, self.recipients, msg.as_string())
                print(f"  Email sent to {self.recipients} (attempt {attempt})")
                return True
            except smtplib.SMTPException as e:
                last_error = e
                print(f"  SMTP error attempt {attempt}: {e}")
                import time; time.sleep(30)
            except Exception as e:
                last_error = e
                print(f"  Email error attempt {attempt}: {e}")
                import time; time.sleep(30)

        print(f"  Email failed after 3 attempts: {last_error}")
        return False
