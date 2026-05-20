from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse

from server.auth import verify_password, create_token, require_auth
from server.config import load_settings, save_settings
from server.models import LoginForm, SettingsUpdate

router = APIRouter(tags=["auth"])


@router.post("/api/login")
async def login(form: LoginForm):
    settings = load_settings()
    if (
        form.username == settings["admin_login"]
        and form.password == settings["admin_password"]
    ):
        token = create_token(form.username)
        response = JSONResponse({"status": "ok"})
        response.set_cookie("access_token", token, httponly=True, max_age=86400)
        return response
    raise HTTPException(401, "Invalid credentials")


@router.post("/api/logout")
async def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("access_token")
    return response


@router.get("/api/settings")
async def get_settings(request: Request):
    require_auth(request)
    settings = load_settings()
    # Mask sensitive data
    safe = {**settings}
    if safe.get("telegram_bot_token"):
        safe["telegram_bot_token"] = safe["telegram_bot_token"][:10] + "..."
    return safe


@router.put("/api/settings")
async def update_settings(update: SettingsUpdate, request: Request):
    require_auth(request)
    settings = load_settings()
    for key, val in update.model_dump(exclude_unset=True).items():
        if val is not None:
            settings[key] = val
    save_settings(settings)
    return {"status": "ok"}


# Mute alerts
mute_until: datetime | None = None


@router.post("/api/mute")
async def mute_alerts(request: Request):
    global mute_until
    require_auth(request)
    body = await request.json()
    hours = body.get("hours", 2)
    mute_until = datetime.now() + timedelta(hours=hours)
    return {"status": "ok", "muted_until": mute_until.isoformat()}


@router.post("/api/unmute")
async def unmute_alerts(request: Request):
    global mute_until
    require_auth(request)
    mute_until = None
    return {"status": "ok"}


@router.get("/api/mute/status")
async def mute_status(request: Request):
    require_auth(request)
    if mute_until and datetime.now() < mute_until:
        return {"muted": True, "until": mute_until.isoformat()}
    return {"muted": False}


@router.get("/api/overview")
async def overview(request: Request):
    """Full overview for Telegram Mini App."""
    require_auth(request)
    from server.config import load_servers
    from server.services.monitor import get_all_metrics

    servers = load_servers()
    metrics = get_all_metrics()

    srv_list = []
    online_count = 0
    for s in servers:
        m = metrics.get(s["host"], {})
        is_online = m.get("online", False)
        if is_online:
            online_count += 1
        srv_list.append({
            "id": s.get("id", ""),
            "name": s["name"],
            "host": s["host"],
            "online": is_online,
            "cpu": m.get("cpu_percent", 0),
            "ram": m.get("ram_percent", 0),
            "disk": m.get("disk_percent", 0),
            "uptime": m.get("uptime", ""),
            "load": m.get("load_average", ""),
        })

    is_muted = mute_until and datetime.now() < mute_until

    return {
        "servers": srv_list,
        "total": len(servers),
        "online": online_count,
        "offline": len(servers) - online_count,
        "muted": is_muted,
        "muted_until": mute_until.isoformat() if is_muted else None,
    }
