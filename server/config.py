import os
import json
import tempfile
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


def load_json(path: Path, default):
    """Load JSON with explicit UTF-8 and a sane default on missing/corrupt file."""
    try:
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError):
        # Don't crash the whole app if a data file is malformed; fall back to default.
        pass
    return default


def save_json(path: Path, data) -> None:
    """Atomic JSON write: dump to temp file then rename. Survives crashes mid-write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise


def load_settings():
    if SETTINGS_FILE.exists():
        return load_json(SETTINGS_FILE, dict(DEFAULT_SETTINGS))
    save_settings(DEFAULT_SETTINGS)
    return dict(DEFAULT_SETTINGS)


def save_settings(settings):
    save_json(SETTINGS_FILE, settings)


def load_servers():
    return load_json(SERVERS_FILE, [])


def save_servers(servers):
    save_json(SERVERS_FILE, servers)
