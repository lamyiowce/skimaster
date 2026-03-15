"""Send the ski search results summary by email via SMTP."""

import os
import smtplib
from email.message import EmailMessage


def send_summary_email(results_md_path: str) -> None:
    """Send the contents of results_md_path to EMAIL_TO via SMTP.

    Required environment variables:
        EMAIL_TO        Recipient address (or comma-separated list)
        SMTP_HOST       SMTP server hostname (e.g. smtp.gmail.com)
        SMTP_USER       SMTP login / sender address
        SMTP_PASSWORD   SMTP password or app-password

    Optional:
        SMTP_PORT       Defaults to 587 (STARTTLS)
    """
    recipient = os.environ.get("EMAIL_TO", "")
    smtp_host = os.environ.get("SMTP_HOST", "")
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))

    if not all([recipient, smtp_host, smtp_user, smtp_password]):
        missing = [
            name
            for name, val in {
                "EMAIL_TO": recipient,
                "SMTP_HOST": smtp_host,
                "SMTP_USER": smtp_user,
                "SMTP_PASSWORD": smtp_password,
            }.items()
            if not val
        ]
        print(f"Email not sent — missing env vars: {', '.join(missing)}")
        return

    try:
        with open(results_md_path) as f:
            body = f.read()
    except FileNotFoundError:
        print(f"Email not sent — results file not found: {results_md_path}")
        return

    msg = EmailMessage()
    msg["Subject"] = "SkiMaster — Ski Accommodation Search Results"
    msg["From"] = smtp_user
    msg["To"] = recipient
    msg.set_content(body)

    print(f"Sending results email to {recipient} via {smtp_host}:{smtp_port}...")
    with smtplib.SMTP(smtp_host, smtp_port) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(smtp_user, smtp_password)
        smtp.send_message(msg)
    print("Email sent successfully.")
