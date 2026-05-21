"""Smart alert system with deduplication for all monitoring tabs.

Logic per issue:
  1. Problem detected -> send 1 alert
  2. Problem continues -> stay silent (no spam)
  3. Problem fixed -> send "resolved" message
  4. New different problem -> send new alert

State tracked per (source, issue_key) pair.
"""

import json
import logging
from datetime import datetime
from typing import Dict, Tuple

from server.config import load_settings, load_servers, DATA_DIR
from server.services.monitor import get_all_metrics

logger = logging.getLogger(__name__)

# Active issues: {(category, source_name, issue_key): datetime_first_seen}
active_issues: Dict[Tuple[str, str, str], datetime] = {}
# Sustained problems waiting for threshold: {issue_key: datetime_first_seen}
_pending_sustain: Dict[Tuple[str, str, str], datetime] = {}


def _issue_key(category: str, source: str, key: str) -> tuple:
    return (category, source, key)


async def _fire_alert(message: str, subject: str, category: str):
    """Send notification via configured channels."""
    from server.services.notifier import send_notification
    await send_notification(message, subject=subject, category=category)


def _is_device_muted(category: str, source: str) -> bool:
    """Check if device is muted in settings."""
    try:
        settings = load_settings()
        muted = settings.get("muted_devices", [])
        return f"{category}:{source}" in muted
    except Exception:
        return False


async def _check_issue(category: str, source: str, key: str, is_problem: bool,
                        alert_msg: str, resolve_msg: str, subject: str):
    """Core dedup logic for one issue."""
    ik = _issue_key(category, source, key)
    was_active = ik in active_issues

    if is_problem and not was_active:
        active_issues[ik] = datetime.now()
        # Skip notification if device muted (still track state)
        if not _is_device_muted(category, source):
            await _fire_alert(alert_msg, subject, category)
            logger.info(f"Alert fired: {category}/{source}/{key}")
        else:
            logger.info(f"Alert suppressed (muted): {category}/{source}/{key}")

    elif not is_problem and was_active:
        del active_issues[ik]
        if not _is_device_muted(category, source):
            await _fire_alert(resolve_msg, f"{subject} resolved", category)
            logger.info(f"Resolved: {category}/{source}/{key}")
        else:
            logger.info(f"Resolved (muted): {category}/{source}/{key}")

    # Problem continues or no problem - stay silent


async def _check_sustained_issue(category: str, source: str, key: str, is_problem: bool,
                                 alert_msg: str, resolve_msg: str, subject: str,
                                 sustain_seconds: int = 300):
    """Alert only after problem persists for sustain_seconds (default 5 min)."""
    ik = _issue_key(category, source, key)
    was_active = ik in active_issues
    now = datetime.now()

    if is_problem:
        if ik not in _pending_sustain:
            _pending_sustain[ik] = now
        elapsed = (now - _pending_sustain[ik]).total_seconds()
        if elapsed >= sustain_seconds and not was_active:
            active_issues[ik] = _pending_sustain[ik]
            if not _is_device_muted(category, source):
                await _fire_alert(alert_msg, subject, category)
                logger.info(f"Sustained alert: {category}/{source}/{key}")
            else:
                logger.info(f"Sustained alert suppressed (muted): {category}/{source}/{key}")
    else:
        _pending_sustain.pop(ik, None)
        if was_active:
            del active_issues[ik]
            if not _is_device_muted(category, source):
                await _fire_alert(resolve_msg, f"{subject} resolved", category)
                logger.info(f"Sustained resolved: {category}/{source}/{key}")


async def check_alerts():
    """Check all 5 tabs for issues."""
    from server.api.auth_routes import mute_until

    # Check global mute
    if mute_until and datetime.now() < mute_until:
        return

    settings = load_settings()

    await _check_servers(settings)
    await _check_pc(settings)
    await _check_synology(settings)
    await _check_ha(settings)
    await _check_keenetic(settings)


# ==================== SERVERS ====================

async def _check_servers(settings: dict):
    """Check VPS servers for offline/threshold issues."""
    servers = load_servers()
    metrics = get_all_metrics()

    cpu_threshold = settings.get("alert_cpu_threshold", 90)
    ram_threshold = settings.get("alert_ram_threshold", 90)
    disk_threshold = settings.get("alert_disk_threshold", 90)

    for srv in servers:
        host = srv["host"]
        name = srv.get("name", host)
        m = metrics.get(host, {})
        online = m.get("online", False)

        # Online/Offline
        await _check_issue(
            "servers", name, "offline",
            is_problem=not online,
            alert_msg=f"🔴 *{name}* ({host}) - OFFLINE!",
            resolve_msg=f"🟢 *{name}* ({host}) - back online",
            subject=f"{name} offline",
        )

        if not online:
            continue

        # CPU
        cpu = m.get("cpu_percent", 0)
        await _check_issue(
            "servers", name, "cpu_high",
            is_problem=cpu >= cpu_threshold,
            alert_msg=f"⚠️ *{name}* CPU: {cpu}% (threshold: {cpu_threshold}%)",
            resolve_msg=f"✅ *{name}* CPU normalized: {cpu}%",
            subject=f"{name} CPU",
        )

        # RAM
        ram = m.get("ram_percent", 0)
        await _check_issue(
            "servers", name, "ram_high",
            is_problem=ram >= ram_threshold,
            alert_msg=f"⚠️ *{name}* RAM: {ram}% (threshold: {ram_threshold}%)",
            resolve_msg=f"✅ *{name}* RAM normalized: {ram}%",
            subject=f"{name} RAM",
        )

        # Disk
        disk = m.get("disk_percent", 0)
        await _check_issue(
            "servers", name, "disk_high",
            is_problem=disk >= disk_threshold,
            alert_msg=f"⚠️ *{name}* Disk: {disk}% (threshold: {disk_threshold}%)",
            resolve_msg=f"✅ *{name}* Disk normalized: {disk}%",
            subject=f"{name} Disk",
        )


# ==================== PC AGENTS ====================

async def _check_pc(settings: dict):
    """Check PC agents for offline status."""
    pc_file = DATA_DIR / "pc_agents.json"
    if not pc_file.exists():
        return

    with open(pc_file) as f:
        pc_data = json.load(f)

    now = datetime.now()

    for name, data in pc_data.items():
        last_seen = data.get("last_seen", "")
        try:
            last_dt = datetime.fromisoformat(last_seen)
            stale = (now - last_dt).total_seconds() > 180  # 3 min
        except Exception:
            stale = True

        await _check_issue(
            "pc", name, "offline",
            is_problem=stale,
            alert_msg=f"🔴 *PC {name}* - no heartbeat for 3+ min",
            resolve_msg=f"🟢 *PC {name}* - back online",
            subject=f"PC {name}",
        )


# ==================== SYNOLOGY ====================

async def _check_synology(settings: dict):
    """Check Synology NAS devices."""
    from server.api.synology import synology_metrics, _load_synology

    devices = _load_synology()

    for dev in devices:
        name = dev["name"]
        m = synology_metrics.get(name, {})

        if not m:
            continue

        online = m.get("online", False)

        await _check_issue(
            "synology", name, "offline",
            is_problem=not online,
            alert_msg=f"🔴 *NAS {name}* - OFFLINE!",
            resolve_msg=f"🟢 *NAS {name}* - back online",
            subject=f"NAS {name}",
        )

        if not online:
            continue

        # Temperature
        temp = m.get("temperature", 0)
        await _check_issue(
            "synology", name, "temp_high",
            is_problem=temp >= 65,
            alert_msg=f"🌡 *NAS {name}* temperature: {temp}C (critical!)",
            resolve_msg=f"✅ *NAS {name}* temperature normalized: {temp}C",
            subject=f"NAS {name} temp",
        )

        # Volume usage
        for vol in m.get("volumes", []):
            vol_name = vol.get("name", "?")
            pct = vol.get("percent", 0)
            await _check_issue(
                "synology", name, f"vol_{vol_name}_full",
                is_problem=pct >= 90,
                alert_msg=f"💾 *NAS {name}* volume {vol_name}: {pct}% full!",
                resolve_msg=f"✅ *NAS {name}* volume {vol_name} freed: {pct}%",
                subject=f"NAS {name} disk",
            )

        # Disk SMART
        for disk in m.get("disks", []):
            disk_name = disk.get("name", "?")
            smart = disk.get("smart_status", "normal")
            await _check_issue(
                "synology", name, f"smart_{disk_name}",
                is_problem=smart not in ("normal", ""),
                alert_msg=f"🔩 *NAS {name}* disk {disk_name} SMART: {smart}!",
                resolve_msg=f"✅ *NAS {name}* disk {disk_name} SMART normal",
                subject=f"NAS {name} SMART",
            )

        # RAM
        ram_pct = m.get("ram_percent", 0)
        await _check_issue(
            "synology", name, "ram_high",
            is_problem=ram_pct >= 90,
            alert_msg=f"⚠️ *NAS {name}* RAM: {ram_pct}%",
            resolve_msg=f"✅ *NAS {name}* RAM normalized: {ram_pct}%",
            subject=f"NAS {name} RAM",
        )


# ==================== HOME ASSISTANT ====================

async def _check_ha(settings: dict):
    """Check Home Assistant instances."""
    from server.api.ha import ha_metrics, _load_ha

    instances = _load_ha()

    for inst in instances:
        name = inst["name"]
        m = ha_metrics.get(name, {})

        if not m:
            continue

        online = m.get("online", False)

        await _check_issue(
            "ha", name, "offline",
            is_problem=not online,
            alert_msg=f"🔴 *HA {name}* - OFFLINE!",
            resolve_msg=f"🟢 *HA {name}* - back online",
            subject=f"HA {name}",
        )

        if not online:
            continue

        # Problem entities
        problems = m.get("problem_entities", [])
        await _check_issue(
            "ha", name, "problems",
            is_problem=len(problems) > 0,
            alert_msg=f"⚠️ *HA {name}* {len(problems)} problem entities",
            resolve_msg=f"✅ *HA {name}* all entities OK",
            subject=f"HA {name} problems",
        )

        # Low battery devices
        battery_sensors = m.get("sensors", {}).get("battery", [])
        low_battery = [b for b in battery_sensors if b.get("value") is not None and b["value"] < 10]
        await _check_issue(
            "ha", name, "low_battery",
            is_problem=len(low_battery) > 0,
            alert_msg=f"🔋 *HA {name}* {len(low_battery)} devices critical battery (<10%)",
            resolve_msg=f"✅ *HA {name}* all batteries OK",
            subject=f"HA {name} battery",
        )


# ==================== KEENETIC ====================

async def _check_keenetic(settings: dict):
    """Check Keenetic routers."""
    from server.api.keenetic import keenetic_metrics, _load_keenetic

    devices = _load_keenetic()

    for dev in devices:
        name = dev["name"]
        m = keenetic_metrics.get(name, {})

        if not m:
            continue

        online = m.get("online", False)

        await _check_issue(
            "keenetic", name, "offline",
            is_problem=not online,
            alert_msg=f"🔴 *Router {name}* - OFFLINE!",
            resolve_msg=f"🟢 *Router {name}* - back online",
            subject=f"Router {name}",
        )

        if not online:
            continue

        # Internet connectivity
        internet = m.get("internet", True)
        await _check_issue(
            "keenetic", name, "no_internet",
            is_problem=not internet,
            alert_msg=f"🌐 *Router {name}* - NO INTERNET!",
            resolve_msg=f"✅ *Router {name}* - internet restored",
            subject=f"Router {name} internet",
        )

        # High CPU
        cpuload = m.get("cpuload", 0)
        await _check_issue(
            "keenetic", name, "cpu_high",
            is_problem=cpuload >= 90,
            alert_msg=f"⚠️ *Router {name}* CPU: {cpuload}%",
            resolve_msg=f"✅ *Router {name}* CPU normalized: {cpuload}%",
            subject=f"Router {name} CPU",
        )

        # High memory
        mem_pct = m.get("mem_percent", 0)
        await _check_issue(
            "keenetic", name, "mem_high",
            is_problem=mem_pct >= 90,
            alert_msg=f"⚠️ *Router {name}* RAM: {mem_pct}%",
            resolve_msg=f"✅ *Router {name}* RAM normalized: {mem_pct}%",
            subject=f"Router {name} RAM",
        )

        # VPN down for 5+ minutes (per tunnel)
        host = dev.get("host", "")
        for vpn in m.get("vpn", []):
            vpn_name = vpn.get("name", "vpn")
            vpn_label = vpn.get("description") or vpn_name
            vpn_type = vpn.get("type", "")
            state = (vpn.get("state") or "").lower()
            is_down = state != "up"
            ts = datetime.now().strftime("%H:%M %d.%m.%Y")
            await _check_sustained_issue(
                "keenetic", name, f"vpn_{vpn_name}",
                is_problem=is_down,
                alert_msg=(
                    f"🔻 *VPN недоступен 5+ мин*\n"
                    f"Роутер: *{name}*\n"
                    f"VPN: `{vpn_label}` ({vpn_type})\n"
                    f"Состояние: `{state or 'down'}`\n"
                    f"Хост: `{host}`\n"
                    f"Время: {ts}"
                ),
                resolve_msg=(
                    f"✅ *VPN восстановлен*\n"
                    f"Роутер: *{name}*\n"
                    f"VPN: `{vpn_label}` ({vpn_type})"
                ),
                subject=f"VPN {name} {vpn_label}",
                sustain_seconds=300,
            )


# ==================== STATUS REQUEST ====================

async def get_full_status() -> str:
    """Generate full status summary for Telegram /status command."""
    lines = ["📊 *VPS Monitoring Status*\n"]

    # Servers
    servers = load_servers()
    metrics = get_all_metrics()
    if servers:
        lines.append("*VPS Servers:*")
        for srv in servers:
            m = metrics.get(srv["host"], {})
            name = srv.get("name", srv["host"])
            if m.get("online"):
                cpu = m.get("cpu_percent", 0)
                ram = m.get("ram_percent", 0)
                disk = m.get("disk_percent", 0)
                lines.append(f"  🟢 {name}: CPU {cpu}% RAM {ram}% Disk {disk}%")
            else:
                lines.append(f"  🔴 {name}: OFFLINE")

    # PC
    pc_file = DATA_DIR / "pc_agents.json"
    if pc_file.exists():
        with open(pc_file) as f:
            pc_data = json.load(f)
        if pc_data:
            lines.append("\n*PC Agents:*")
            now = datetime.now()
            for name, data in pc_data.items():
                last_seen = data.get("last_seen", "")
                try:
                    last_dt = datetime.fromisoformat(last_seen)
                    stale = (now - last_dt).total_seconds() > 180
                except Exception:
                    stale = True
                m = data.get("metrics", {})
                if not stale:
                    lines.append(f"  🟢 {name}: CPU {m.get('cpu_percent', 0)}% RAM {m.get('ram_percent', 0)}%")
                else:
                    lines.append(f"  🔴 {name}: offline")

    # Synology
    from server.api.synology import synology_metrics, _load_synology
    syn_devs = _load_synology()
    if syn_devs:
        lines.append("\n*Synology NAS:*")
        for dev in syn_devs:
            m = synology_metrics.get(dev["name"], {})
            if m.get("online"):
                lines.append(f"  🟢 {dev['name']}: {m.get('model', '')} CPU {m.get('cpu_percent', 0)}% RAM {m.get('ram_percent', 0)}% {m.get('temperature', 0)}C")
            else:
                lines.append(f"  🔴 {dev['name']}: offline")

    # HA
    from server.api.ha import ha_metrics, _load_ha
    ha_insts = _load_ha()
    if ha_insts:
        lines.append("\n*Home Assistant:*")
        for inst in ha_insts:
            m = ha_metrics.get(inst["name"], {})
            if m.get("online"):
                ent = m.get("entities_count", 0)
                lines.append(f"  🟢 {inst['name']}: v{m.get('version', '?')} ({ent} entities)")
            else:
                lines.append(f"  🔴 {inst['name']}: offline")

    # Keenetic
    from server.api.keenetic import keenetic_metrics, _load_keenetic
    keen_devs = _load_keenetic()
    if keen_devs:
        lines.append("\n*Keenetic Routers:*")
        for dev in keen_devs:
            m = keenetic_metrics.get(dev["name"], {})
            if m.get("online"):
                inet = "🌐" if m.get("internet") else "⚠️NO-INET"
                lines.append(f"  🟢 {dev['name']}: {m.get('model', '')} CPU {m.get('cpuload', 0)}% RAM {m.get('mem_percent', 0)}% {inet} {m.get('clients_count', 0)} clients")
            else:
                lines.append(f"  🔴 {dev['name']}: offline")

    # Active issues
    if active_issues:
        lines.append(f"\n⚠️ *Active issues: {len(active_issues)}*")
        for (cat, src, key), since in active_issues.items():
            lines.append(f"  - {cat}/{src}: {key}")
    else:
        lines.append("\n✅ *No active issues*")

    return "\n".join(lines)
