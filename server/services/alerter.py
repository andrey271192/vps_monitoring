import logging
from datetime import datetime
from typing import Dict

from server.config import load_settings, load_servers
from server.services.monitor import get_all_metrics

logger = logging.getLogger(__name__)

previous_states: Dict[str, bool] = {}


async def check_alerts():
    """Check metrics against thresholds and send alerts."""
    from server.services.telegram_bot import send_alert

    settings = load_settings()
    servers = load_servers()
    metrics = get_all_metrics()

    cpu_threshold = settings.get("alert_cpu_threshold", 90)
    ram_threshold = settings.get("alert_ram_threshold", 90)
    disk_threshold = settings.get("alert_disk_threshold", 90)

    for srv in servers:
        host = srv["host"]
        m = metrics.get(host, {})
        name = srv.get("name", host)

        current_online = m.get("online", False)
        prev_online = previous_states.get(host)

        # Online/Offline state change
        if prev_online is not None and prev_online != current_online:
            if current_online:
                await send_alert(f"🟢 **{name}** ({host}) — снова онлайн")
            else:
                await send_alert(f"🔴 **{name}** ({host}) — OFFLINE!")

        previous_states[host] = current_online

        if not current_online:
            continue

        # Threshold alerts
        cpu = m.get("cpu_percent", 0)
        if cpu >= cpu_threshold:
            await send_alert(f"⚠️ **{name}** — CPU: {cpu}% (порог: {cpu_threshold}%)")

        ram = m.get("ram_percent", 0)
        if ram >= ram_threshold:
            await send_alert(f"⚠️ **{name}** — RAM: {ram}% (порог: {ram_threshold}%)")

        disk = m.get("disk_percent", 0)
        if disk >= disk_threshold:
            await send_alert(f"⚠️ **{name}** — Disk: {disk}% (порог: {disk_threshold}%)")
