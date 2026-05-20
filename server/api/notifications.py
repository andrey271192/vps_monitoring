"""Notification settings and test endpoints."""

from fastapi import APIRouter, Request, Depends

from server.auth import require_auth
from server.config import load_settings, save_settings

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("/settings")
async def get_notification_settings(request: Request, user: str = Depends(require_auth)):
    """Get notification preferences per category."""
    settings = load_settings()
    return {
        "notifications": settings.get("notifications", {
            "servers": {"telegram": True, "email": False, "whatsapp": False},
            "pc": {"telegram": True, "email": False, "whatsapp": False},
            "synology": {"telegram": True, "email": False, "whatsapp": False},
            "ha": {"telegram": True, "email": False, "whatsapp": False},
        }),
        "email": {
            "smtp_host": settings.get("smtp_host", ""),
            "smtp_port": settings.get("smtp_port", 587),
            "smtp_user": settings.get("smtp_user", ""),
            "email_to": settings.get("email_to", ""),
            "configured": bool(settings.get("smtp_host") and settings.get("smtp_user")),
        },
        "whatsapp": {
            "phone": settings.get("whatsapp_phone", ""),
            "configured": bool(settings.get("whatsapp_phone") and settings.get("whatsapp_apikey")),
        },
        "telegram": {
            "configured": bool(settings.get("telegram_bot_token") and settings.get("telegram_chat_id")),
        },
    }


@router.put("/settings")
async def save_notification_settings(request: Request, user: str = Depends(require_auth)):
    """Save notification preferences."""
    body = await request.json()
    settings = load_settings()

    # Notification toggles per category
    if "notifications" in body:
        settings["notifications"] = body["notifications"]

    # Email settings
    if "smtp_host" in body:
        settings["smtp_host"] = body["smtp_host"]
    if "smtp_port" in body:
        settings["smtp_port"] = int(body["smtp_port"])
    if "smtp_user" in body:
        settings["smtp_user"] = body["smtp_user"]
    if "smtp_password" in body:
        settings["smtp_password"] = body["smtp_password"]
    if "email_to" in body:
        settings["email_to"] = body["email_to"]

    # WhatsApp settings
    if "whatsapp_phone" in body:
        settings["whatsapp_phone"] = body["whatsapp_phone"]
    if "whatsapp_apikey" in body:
        settings["whatsapp_apikey"] = body["whatsapp_apikey"]

    save_settings(settings)
    return {"status": "ok"}


@router.post("/test/{channel}")
async def test_notification(channel: str, request: Request, user: str = Depends(require_auth)):
    """Send test notification via specified channel."""
    from server.services.notifier import send_telegram, send_email, send_whatsapp

    message = "🧪 Тест уведомления VPS Monitoring"
    ok = False

    if channel == "telegram":
        ok = await send_telegram(message)
    elif channel == "email":
        ok = await send_email("Тест", message)
    elif channel == "whatsapp":
        ok = await send_whatsapp(message)
    else:
        return {"status": "error", "detail": f"unknown channel: {channel}"}

    return {"status": "ok" if ok else "error", "channel": channel}


@router.post("/generate-pc-agent")
async def generate_pc_agent(request: Request, user: str = Depends(require_auth)):
    """Generate personalized PC agent install command."""
    body = await request.json()
    agent_name = body.get("agent_name", "MyPC").strip()
    server_url = body.get("server_url", "").strip()

    if not server_url:
        # Auto-detect
        host = request.headers.get("host", "localhost:7272")
        proto = "http"
        server_url = f"{proto}://{host}"

    cmd = (
        f'powershell -ExecutionPolicy Bypass -Command '
        f'"Invoke-WebRequest -Uri \'{server_url}/static/downloads/install_agent.ps1\' '
        f'-OutFile install_agent.ps1; .\\install_agent.ps1 '
        f'-ServerUrl \'{server_url}\' -AgentName \'{agent_name}\'"'
    )

    return {"status": "ok", "command": cmd, "agent_name": agent_name}
