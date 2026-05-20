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
