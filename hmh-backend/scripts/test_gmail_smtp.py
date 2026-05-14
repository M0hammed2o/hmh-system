"""
Gmail SMTP diagnostic and test script.

Usage:
    python scripts/test_gmail_smtp.py [recipient@example.com]

If no recipient is given, the email is sent to the configured SMTP_USERNAME address (self-test).

This script:
 1. Loads settings from .env (including alias resolution: SMTP_USER → SMTP_USERNAME, etc.)
 2. Prints the resolved SMTP configuration (no password shown)
 3. Attempts a real Gmail send
 4. Prints clear SUCCESS or FAILURE with the exact error

Exit code: 0 = success, 1 = failure
"""

import sys
import os

# Allow running from any directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Force the lru_cache to reload settings from .env
from app.core.config import get_settings
get_settings.cache_clear()

from app.core.config import settings  # noqa: E402 — must import after sys.path fix

print("=" * 60)
print("HMH Gmail SMTP Test")
print("=" * 60)
use_ssl = settings.SMTP_USE_SSL or settings.SMTP_PORT == 465
mode    = "SSL (port 465)" if use_ssl else "STARTTLS (port 587)"

print(f"SMTP_ENABLED    : {settings.SMTP_ENABLED}")
print(f"EMAIL_MOCK_MODE : {settings.EMAIL_MOCK_MODE}")
print(f"SMTP_HOST       : {settings.SMTP_HOST}:{settings.SMTP_PORT}")
print(f"SMTP_MODE       : {mode}")
print(f"SMTP_USERNAME   : {settings.SMTP_USERNAME or '<NOT SET>'}")
print(f"SMTP_PASSWORD   : {'<set>' if settings.SMTP_PASSWORD else '<NOT SET>'}")
print(f"SMTP_FROM       : {settings.smtp_sender_address or '<NOT SET>'}")
print("=" * 60)

if not settings.SMTP_ENABLED:
    print()
    print("ERROR: SMTP_ENABLED=false in .env")
    print("Fix:   Set  SMTP_ENABLED=true  in .env")
    sys.exit(1)

if not settings.SMTP_USERNAME:
    print()
    print("ERROR: SMTP_USERNAME is empty.")
    print("Tip:   The .env must contain one of:")
    print("         SMTP_USERNAME=procurementhmhgroup@gmail.com")
    print("         SMTP_USER=procurementhmhgroup@gmail.com   (legacy alias)")
    print("         GMAIL_USER=procurementhmhgroup@gmail.com  (alternate alias)")
    sys.exit(1)

if not settings.SMTP_PASSWORD:
    print()
    print("ERROR: SMTP_PASSWORD is empty.")
    print("Tip:   Use a Gmail App Password (16 chars, spaces stripped automatically).")
    print("         SMTP_PASSWORD=xxxx xxxx xxxx xxxx  <- spaces are OK, stripped at load time")
    sys.exit(1)

recipient = sys.argv[1] if len(sys.argv) > 1 else settings.SMTP_USERNAME
print(f"Recipient       : {recipient}")
print()
print(f"Attempting real SMTP send ({mode}) ...")
print()

import smtplib  # noqa: E402
from email.mime.multipart import MIMEMultipart  # noqa: E402
from email.mime.text import MIMEText  # noqa: E402

subject   = "HMH Gmail SMTP Test"
html_body = """
<html><body style="font-family:Arial,sans-serif;color:#1a1a1a">
<div style="background:#e85d04;padding:20px 30px">
  <h2 style="color:white;margin:0">HMH Group — Gmail Test</h2>
</div>
<div style="padding:20px 30px">
  <p>If you can read this email, Gmail SMTP is configured correctly.</p>
  <p style="color:#888;font-size:12px">HMH Construction OS — test_gmail_smtp.py</p>
</div>
</body></html>
"""

try:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{settings.SMTP_FROM_NAME} <{settings.smtp_sender_address}>"
    msg["To"]      = recipient
    msg.attach(MIMEText(html_body, "html"))

    if use_ssl:
        # Direct SSL connection (port 465)
        with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as server:
            server.set_debuglevel(0)  # set to 1 for full SMTP transcript
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.sendmail(settings.smtp_sender_address, [recipient], msg.as_string())
    else:
        # STARTTLS connection (port 587)
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as server:
            server.set_debuglevel(0)  # set to 1 for full SMTP transcript
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.sendmail(settings.smtp_sender_address, [recipient], msg.as_string())

    print("=" * 60)
    print(f"SUCCESS — email sent to {recipient}")
    print("Check your inbox (and Spam folder).")
    print("=" * 60)
    sys.exit(0)

except smtplib.SMTPAuthenticationError as e:
    print("=" * 60)
    print("FAILED — Authentication error")
    print(f"  Error: {e}")
    print()
    print("Troubleshooting:")
    print("  1. Make sure you are using a Gmail APP PASSWORD (not your account password).")
    print("     Generate at: myaccount.google.com/apppasswords")
    print("  2. Spaces in the app password are stripped automatically.")
    print("     e.g.  xkds uwam hfbb hxua  →  xkdsuwamhfbbhxua  (both work in .env)")
    print("  3. Make sure 2-Step Verification is enabled on the Gmail account.")
    print("=" * 60)
    sys.exit(1)

except Exception as e:
    print("=" * 60)
    print(f"FAILED — {type(e).__name__}: {e}")
    print("=" * 60)
    sys.exit(1)
