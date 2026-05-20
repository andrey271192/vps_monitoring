import asyncio
import logging
import os
import sys

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.auth import get_current_user
from server.api.servers import router as servers_router
from server.api.auth_routes import router as auth_router
from server.api.ssh_ws import router as ssh_router
from server.services.monitor import monitor_loop
from server.services.telegram_bot import start_bot, stop_bot
from server.services.alerter import check_alerts
from server.config import load_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

monitor_task = None
alert_task = None


async def alert_loop():
    """Periodic alert checking."""
    while True:
        try:
            await check_alerts()
        except Exception as e:
            logger.error(f"Alert check error: {e}")
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global monitor_task, alert_task
    # Start background tasks
    monitor_task = asyncio.create_task(monitor_loop())
    alert_task = asyncio.create_task(alert_loop())
    await start_bot()
    logger.info("VPS Monitoring started")
    yield
    # Cleanup
    if monitor_task:
        monitor_task.cancel()
    if alert_task:
        alert_task.cancel()
    await stop_bot()


app = FastAPI(title="VPS Monitoring", lifespan=lifespan)

# Static files
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Include routers
app.include_router(servers_router)
app.include_router(auth_router)
app.include_router(ssh_router)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse("/")
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/telegram-app", response_class=HTMLResponse)
async def telegram_app(request: Request):
    return templates.TemplateResponse("telegram_app.html", {"request": request})


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=True)
