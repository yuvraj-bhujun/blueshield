"""
services/email_alert.py

Sends an email alert (Gmail SMTP) to Coast Guard / NGO contacts the moment
a vessel's reef-grounding risk crosses into High/Critical. The email body
includes the full BlueShield AI executive report (gemmatext), which itself
now ends with two recommended follow-up actions (see gemma_engine.py).
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ---------------------------------------------------------------------------
# SENDER
# SENDER_PASSWORD must be a Gmail "App Password", not the normal account
# password — Gmail rejects plain-password SMTP logins. Generate one (with
# 2-Step Verification enabled on the account) at:
# https://myaccount.google.com/apppasswords
# ---------------------------------------------------------------------------
SENDER_EMAIL = "noreply.blueshield.mu@gmail.com"
SENDER_PASSWORD = "exbt uzuf gmld asmc"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# ---------------------------------------------------------------------------
# RECEIVERS
# Comma-separated string — one or more Coast Guard / NGO email addresses.
# ---------------------------------------------------------------------------
CG_EMAIL = "yuvrajuni06@gmail.com, naweed.emrith@gmail.com, gauravsewpal@gmail.com"


def _recipient_list():
    return [addr.strip() for addr in CG_EMAIL.split(",") if addr.strip()]


def _build_message(vessel, risk, gemma_text):
    subject = (
        f"\U0001F6A8 BlueShield AI Alert — {risk.get('level', 'High')} Risk: "
        f"{vessel.get('VesselName', 'Unknown vessel')} (MMSI {vessel.get('MMSI')})"
    )

    body = f"""BlueShield AI — Maritime Risk Alert
========================================

Vessel: {vessel.get('VesselName', 'Unknown')}
MMSI: {vessel.get('MMSI')}
Type: {vessel.get('VesselType')}
Flag: {vessel.get('Flag')}
Destination: {vessel.get('Destination')}

Risk Level: {risk.get('level')}
Risk Score: {risk.get('score')}/100
Distance To Reef: {risk.get('current_distance')} km
Trend: {risk.get('trend')}
ETA To Reef: {risk.get('eta')} hours
Lane Deviation: {risk.get('lane_deviation')} km
Inside Reef: {risk.get('inside_reef')}

----------------------------------------
BlueShield AI Executive Report
----------------------------------------
{gemma_text}

----------------------------------------
This is an automated alert from BlueShield AI. The sending address is
unmonitored (noreply) — please do not reply directly to it.
"""

    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = ", ".join(_recipient_list())
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    return msg


def send_risk_alert_email(vessel, risk, gemma_text):
    """
    vessel: normalized vessel dict (VesselName, MMSI, VesselType, Flag,
            Destination, ...) — the shape produced by app.normalize_live_ship
    risk:   risk_engine.calculate_risk() output (level, score,
            current_distance, trend, eta, lane_deviation, inside_reef, ...)
    gemma_text: the BlueShield AI executive report string returned by
                gemma_engine.generate_vessel_reasoning() — includes the two
                recommended actions.

    Returns True if the email was sent, False otherwise (missing
    recipients, SMTP/auth failure, network error, etc — never raises, so a
    failed email never breaks the alarm/broadcast flow that triggered it).
    """
    print("[email_alert] send_risk_alert_email() called.", flush=True)

    recipients = _recipient_list()
    if not recipients:
        print("[email_alert] ⚠️ No recipients configured (CG_EMAIL is empty) — skipping.", flush=True)
        return False

    if not SENDER_PASSWORD or SENDER_PASSWORD.strip().lower() == "i will in put my app password":
        print(
            "[email_alert] ⚠️⚠️⚠️ SENDER_PASSWORD is still the placeholder text — "
            "no email will be sent until you set a real Gmail App Password in "
            "services/email_alert.py. Generate one at "
            "https://myaccount.google.com/apppasswords (requires 2-Step Verification "
            "enabled on the sending Gmail account).",
            flush=True,
        )
        return False

    msg = _build_message(vessel, risk, gemma_text)

    try:
        print(f"[email_alert] Connecting to {SMTP_SERVER}:{SMTP_PORT}...", flush=True)
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
            server.starttls()
            print("[email_alert] TLS started, logging in...", flush=True)
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            print("[email_alert] Logged in, sending...", flush=True)
            server.sendmail(SENDER_EMAIL, recipients, msg.as_string())
        print(f"[email_alert] ✅ Alert email sent to {recipients}", flush=True)
        return True
    except smtplib.SMTPAuthenticationError as e:
        print(
            f"[email_alert] ❌ Gmail rejected the login (wrong address/App Password?): {e}",
            flush=True,
        )
        return False
    except Exception as e:
        print(f"[email_alert] ❌ Failed to send alert email: {type(e).__name__}: {e}", flush=True)
        return False