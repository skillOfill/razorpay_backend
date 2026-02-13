"""Send license key email via SMTP or SendGrid."""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def send_license_email(to_email: str, license_key: str, app_url: str = "") -> bool:
    """
    Send email with license key. Uses SMTP (Gmail etc.) or SendGrid API from env.
    Returns True if sent, False otherwise.
    """
    subject = "Your SQL Humanizer License Key"
    app_url = app_url or os.environ.get("APP_URL", "the app")
    body_plain = f"""Thank you for your purchase!

Your SQL Humanizer Pro license key is:

  {license_key}

Enter this key in the License field in the app sidebar to unlock unlimited translations.

If you have any questions, reply to this email.
"""
    body_html = f"""
    <p>Thank you for your purchase!</p>
    <p>Your <strong>SQL Humanizer Pro</strong> license key is:</p>
    <p style="font-size:1.2em; font-family:monospace; background:#f1f5f9; padding:0.5rem 1rem; border-radius:6px;">{license_key}</p>
    <p>Enter this key in the License field in the app sidebar to unlock unlimited translations.</p>
    <p>If you have any questions, reply to this email.</p>
    """

    # SendGrid
    sendgrid_key = os.environ.get("SENDGRID_API_KEY")
    if sendgrid_key:
        return _send_sendgrid(to_email, subject, body_plain, body_html, sendgrid_key)

    # SMTP (Gmail, etc.)
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASSWORD")
    from_email = os.environ.get("MAIL_FROM", smtp_user or "noreply@example.com")

    if smtp_host and smtp_user and smtp_pass:
        return _send_smtp(from_email, to_email, subject, body_plain, body_html, smtp_host, smtp_port, smtp_user, smtp_pass)

    # No mail config: log and skip (webhook still saves the key)
    import logging
    logging.warning("No SMTP or SendGrid configured; license key not emailed (still saved). To=%s Key=%s", to_email, license_key[:8] + "...")
    return False


def _send_smtp(from_addr, to_addr, subject, body_plain, body_html, host, port, user, password):
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_addr
        msg.attach(MIMEText(body_plain, "plain"))
        msg.attach(MIMEText(body_html, "html"))
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(from_addr, [to_addr], msg.as_string())
        return True
    except Exception as e:
        import logging
        logging.exception("SMTP send failed: %s", e)
        return False


def _send_sendgrid(to_email, subject, body_plain, body_html, api_key):
    try:
        import urllib.request
        import json
        from_email = os.environ.get("MAIL_FROM", "noreply@example.com")
        from_name = os.environ.get("MAIL_FROM_NAME", "SQL Humanizer")
        data = {
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {"email": from_email, "name": from_name},
            "subject": subject,
            "content": [
                {"type": "text/plain", "value": body_plain},
                {"type": "text/html", "value": body_html},
            ],
        }
        req = urllib.request.Request(
            "https://api.sendgrid.com/v3/mail/send",
            data=json.dumps(data).encode(),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            return 200 <= resp.status < 300
    except Exception as e:
        import logging
        logging.exception("SendGrid send failed: %s", e)
        return False
