import os
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

SERVERS_FILE = DATA_DIR / "servers.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
METRICS_FILE = DATA_DIR / "metrics.json"

DEFAULT_SETTINGS = {
    "admin_login": "admin",
    "admin_password": "admin",
    "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
    "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
    "monitor_interval": 60,
    "alert_cpu_threshold": 90,
    "alert_ram_threshold": 90,
    "alert_disk_threshold": 90,
}


def load_settings():
    if SETTINGS_FILE.exists():
        with open(SETTINGS_FILE) as f:
            return json.load(f)
    save_settings(DEFAULT_SETTINGS)
    return DEFAULT_SETTINGS.copy()


def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


def load_servers():
    if SERVERS_FILE.exists():
        with open(SERVERS_FILE) as f:
            return json.load(f)
    return []


def save_servers(servers):
    with open(SERVERS_FILE, "w") as f:
        json.dump(servers, f, indent=2, ensure_ascii=False)
