from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from server.config import load_settings

SECRET_KEY = "vps-monitoring-secret-key-change-me-in-production"
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return plain_password == hashed_password


def create_token(username: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode({"sub": username, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except Exception:
        return None


def get_current_user(request: Request) -> str | None:
    token = request.cookies.get("access_token")
    if not token:
        return None
    return verify_token(token)


def require_auth(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
