"""Unified notification sender: Telegram, Email, WhatsApp (CallMeBot)."""

import asyncio
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

import aiohttp

from server.config import load_settings

logger = logging.getLogger(__name__)


async def send_telegram(message: str, parse_mode: str = "Markdown"):
    """Send message via Telegram bot."""
    settings = load_settings()
    token = settings.get("telegram_bot_token")
    chat_id = settings.get("telegram_chat_id")
    if not token or not chat_id:
        return False

    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            async with session.post(url, json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": parse_mode,
            }) as resp:
                ok = resp.status == 200
                if ok:
                    logger.info(f"Telegram sent: {message[:80]}")
                else:
                    body = await resp.text()
                    logger.error(f"Telegram send HTTP {resp.status}: {body[:200]}")
                return ok
    except Exception as e:
        logger.error(f"Telegram send error: {e}")
        return False


async def send_email(subject: str, body: str):
    """Send email via SMTP."""
    settings = load_settings()
    smtp_host = settings.get("smtp_host", "")
    smtp_port = int(settings.get("smtp_port", 587))
    smtp_user = settings.get("smtp_user", "")
    smtp_password = settings.get("smtp_password", "")
    email_to = settings.get("email_to", "")

    if not all([smtp_host, smtp_user, smtp_password, email_to]):
        return False

    try:
        msg = MIMEMultipart()
        msg["From"] = smtp_user
        msg["To"] = email_to
        msg["Subject"] = f"🖥 VPS Monitor: {subject}"

        # HTML body
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;
                    background:#1a1a3e;color:#e8e8ff;padding:24px;border-radius:12px">
            <h2 style="color:#6366f1;margin-bottom:16px">🖥 VPS Monitoring</h2>
            <div style="background:#0f0f23;padding:16px;border-radius:8px;
                        border-left:4px solid #6366f1;margin-bottom:16px">
                {body.replace(chr(10), '<br>')}
            </div>
            <p style="color:#a0a0cc;font-size:12px">Автоматическое уведомление VPS Monitoring</p>
        </div>
        """
        msg.attach(MIMEText(html, "html"))

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _smtp_send, smtp_host, smtp_port, smtp_user, smtp_password, email_to, msg)
        return True
    except Exception as e:
        logger.error(f"Email send error: {e}")
        return False


def _smtp_send(host, port, user, password, to, msg):
    """Blocking SMTP send (run in executor)."""
    with smtplib.SMTP(host, port, timeout=15) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(user, to, msg.as_string())


async def send_whatsapp(message: str):
    """Send WhatsApp message via CallMeBot API.

    Setup: User sends "I allow callmebot to send me messages" to
    +34 644 71 85 23 on WhatsApp, gets apikey.
    Store phone + apikey in settings.
    """
    settings = load_settings()
    wa_phone = settings.get("whatsapp_phone", "")
    wa_apikey = settings.get("whatsapp_apikey", "")

    if not wa_phone or not wa_apikey:
        return False

    try:
        # Clean message for URL
        clean_msg = message.replace("**", "*")
        async with aiohttp.ClientSession() as session:
            url = "https://api.callmebot.com/whatsapp.php"
            params = {
                "phone": wa_phone,
                "text": clean_msg,
                "apikey": wa_apikey,
            }
            async with session.get(url, params=params) as resp:
                return resp.status == 200
    except Exception as e:
        logger.error(f"WhatsApp send error: {e}")
        return False


async def send_notification(message: str, subject: str = "Alert", category: str = "servers"):
    """Send notification via all enabled channels for given category.

    Categories: servers, pc, synology, ha
    Settings key: notify_{category}_{channel} = true/false
    Channels: telegram, email, whatsapp
    """
    from datetime import datetime
    from server.api.auth_routes import mute_until

    # Check global mute
    if mute_until and datetime.now() < mute_until:
        return

    settings = load_settings()
    notify_prefs = settings.get("notifications", {})

    # Default: telegram enabled for all
    cat_prefs = notify_prefs.get(category, {"telegram": True, "email": False, "whatsapp": False})

    tasks = []
    if cat_prefs.get("telegram", True):
        tasks.append(send_telegram(message))
    if cat_prefs.get("email", False):
        tasks.append(send_email(subject, message))
    if cat_prefs.get("whatsapp", False):
        tasks.append(send_whatsapp(message))

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
