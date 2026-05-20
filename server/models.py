from pydantic import BaseModel
from typing import Optional


class ServerCreate(BaseModel):
    name: str
    host: str
    port: int = 22
    username: str = "root"
    password: Optional[str] = None
    ssh_key: Optional[str] = None
    description: Optional[str] = ""


class ServerUpdate(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    ssh_key: Optional[str] = None
    description: Optional[str] = None


class LoginForm(BaseModel):
    username: str
    password: str


class SettingsUpdate(BaseModel):
    admin_login: Optional[str] = None
    admin_password: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    monitor_interval: Optional[int] = None
    alert_cpu_threshold: Optional[int] = None
    alert_ram_threshold: Optional[int] = None
    alert_disk_threshold: Optional[int] = None


class ServerMetrics(BaseModel):
    cpu_percent: float = 0
    ram_percent: float = 0
    ram_used_mb: float = 0
    ram_total_mb: float = 0
    disk_percent: float = 0
    disk_used_gb: float = 0
    disk_total_gb: float = 0
    network_in_mb: float = 0
    network_out_mb: float = 0
    uptime: str = ""
    load_average: str = ""
    online: bool = False
    last_check: str = ""
