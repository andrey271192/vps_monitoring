import logging
from datetime import datetime
from typing import Dict

from server.config import load_settings, load_servers
from server.services.monitor import get_all_metrics

logger = logging.getLogger(__name__)

previous_states: Dict[str, bool] = {}


async def check_alerts():
    """Check metrics against thresholds and send alerts."""
    from server.services.notifier import send_notification
    from server.api.auth_routes import mute_until

    # Check mute
    if mute_until and datetime.now() < mute_until:
        return

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
                await send_notification(
                    f"🟢 **{name}** ({host}) — снова онлайн",
                    subject=f"{name} Online", category="servers"
                )
            else:
                await send_notification(
                    f"🔴 **{name}** ({host}) — OFFLINE!",
                    subject=f"{name} OFFLINE", category="servers"
                )

        previous_states[host] = current_online

        if not current_online:
            continue

        # Threshold alerts
        cpu = m.get("cpu_percent", 0)
        if cpu >= cpu_threshold:
            await send_notification(
                f"⚠️ **{name}** — CPU: {cpu}% (порог: {cpu_threshold}%)",
                subject=f"{name} CPU {cpu}%", category="servers"
            )

        ram = m.get("ram_percent", 0)
        if ram >= ram_threshold:
            await send_notification(
                f"⚠️ **{name}** — RAM: {ram}% (порог: {ram_threshold}%)",
                subject=f"{name} RAM {ram}%", category="servers"
            )

        disk = m.get("disk_percent", 0)
        if disk >= disk_threshold:
            await send_notification(
                f"⚠️ **{name}** — Disk: {disk}% (порог: {disk_threshold}%)",
                subject=f"{name} Disk {disk}%", category="servers"
            )
