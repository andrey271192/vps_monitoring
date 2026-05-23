import hashlib
import hmac
import os
from datetime import datetime, timedelta
from urllib.parse import parse_qs

from jose import jwt
from fastapi import Request, HTTPException
from server.config import load_settings

# Allow override via env so a single deployment can rotate secrets without
# rebaking the image. Falls back to a known value for backwards compatibility.
SECRET_KEY = os.getenv("VPS_MONITORING_SECRET", "vps-monitoring-secret-key-change-me-in-production")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24


def verify_password(plain_password: str, stored_password: str) -> bool:
    """Plain-text comparison — admin password is stored verbatim in settings.json."""
    return plain_password == stored_password


def create_token(username: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode({"sub": username, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except Exception:
        return None


def verify_telegram_init_data(init_data: str) -> bool:
    """Validate Telegram WebApp initData using bot token."""
    settings = load_settings()
    bot_token = settings.get("telegram_bot_token", "")
    if not bot_token:
        return False

    try:
        parsed = parse_qs(init_data)
        received_hash = parsed.get("hash", [""])[0]
        if not received_hash:
            return False

        # Build data-check-string
        data_pairs = []
        for key, values in parsed.items():
            if key != "hash":
                data_pairs.append(f"{key}={values[0]}")
        data_pairs.sort()
        data_check_string = "\n".join(data_pairs)

        # HMAC-SHA256
        secret_key = hmac.new(
            b"WebAppData", bot_token.encode(), hashlib.sha256
        ).digest()
        calculated_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        return calculated_hash == received_hash
    except Exception:
        return False


def get_current_user(request: Request) -> str | None:
    # 1. Cookie auth
    token = request.cookies.get("access_token")
    if token:
        user = verify_token(token)
        if user:
            return user

    # 2. Telegram initData auth (header)
    tg_init = request.headers.get("X-Telegram-Init-Data")
    if tg_init and verify_telegram_init_data(tg_init):
        return "telegram_user"

    return None


def require_auth(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
