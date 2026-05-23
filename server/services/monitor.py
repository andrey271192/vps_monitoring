import asyncio
import logging
from datetime import datetime
from typing import Dict

import asyncssh

from server.config import load_servers, load_settings, save_json, METRICS_FILE

logger = logging.getLogger(__name__)

metrics_cache: Dict[str, dict] = {}


async def collect_server_metrics(server: dict) -> dict:
    """Connect to server via SSH and collect system metrics."""
    metrics = {
        "cpu_percent": 0,
        "ram_percent": 0,
        "ram_used_mb": 0,
        "ram_total_mb": 0,
        "disk_percent": 0,
        "disk_used_gb": 0,
        "disk_total_gb": 0,
        "network_in_mb": 0,
        "network_out_mb": 0,
        "uptime": "",
        "load_average": "",
        "online": False,
        "last_check": datetime.now().isoformat(),
    }

    try:
        conn_kwargs = {
            "host": server["host"],
            "port": server.get("port", 22),
            "username": server.get("username", "root"),
            "known_hosts": None,
            "connect_timeout": 10,
        }

        if server.get("password"):
            conn_kwargs["password"] = server["password"]
        elif server.get("ssh_key"):
            conn_kwargs["client_keys"] = [server["ssh_key"]]

        async with asyncssh.connect(**conn_kwargs) as conn:
            # CPU usage
            result = await conn.run(
                "top -bn1 | grep 'Cpu(s)' | awk '{print $2}' | cut -d'%' -f1",
                check=False
            )
            if result.stdout.strip():
                try:
                    metrics["cpu_percent"] = round(float(result.stdout.strip()), 1)
                except ValueError:
                    pass

            # RAM
            result = await conn.run(
                "free -m | awk 'NR==2{printf \"%s %s %s\", $2, $3, $3/$2*100}'",
                check=False
            )
            if result.stdout.strip():
                parts = result.stdout.strip().split()
                if len(parts) >= 3:
                    try:
                        metrics["ram_total_mb"] = float(parts[0])
                        metrics["ram_used_mb"] = float(parts[1])
                        metrics["ram_percent"] = round(float(parts[2]), 1)
                    except ValueError:
                        pass

            # Disk
            result = await conn.run(
                "df -BG / | awk 'NR==2{print $2, $3, $5}'",
                check=False
            )
            if result.stdout.strip():
                parts = result.stdout.strip().replace("G", "").split()
                if len(parts) >= 3:
                    try:
                        metrics["disk_total_gb"] = float(parts[0])
                        metrics["disk_used_gb"] = float(parts[1])
                        metrics["disk_percent"] = float(parts[2].replace("%", ""))
                    except ValueError:
                        pass

            # Network
            result = await conn.run(
                "cat /proc/net/dev | awk 'NR>2{rx+=$2; tx+=$10} END{printf \"%.0f %.0f\", rx/1048576, tx/1048576}'",
                check=False
            )
            if result.stdout.strip():
                parts = result.stdout.strip().split()
                if len(parts) >= 2:
                    try:
                        metrics["network_in_mb"] = float(parts[0])
                        metrics["network_out_mb"] = float(parts[1])
                    except ValueError:
                        pass

            # Uptime
            result = await conn.run("uptime -p", check=False)
            if result.stdout.strip():
                metrics["uptime"] = result.stdout.strip()

            # Load average
            result = await conn.run("cat /proc/loadavg | awk '{print $1, $2, $3}'", check=False)
            if result.stdout.strip():
                metrics["load_average"] = result.stdout.strip()

            metrics["online"] = True

    except Exception as e:
        logger.warning(f"Failed to collect metrics from {server.get('name', server['host'])}: {e}")
        metrics["online"] = False

    return metrics


async def monitor_loop():
    """Background monitoring loop."""
    while True:
        try:
            settings = load_settings()
            servers = load_servers()
            interval = settings.get("monitor_interval", 60)

            tasks = []
            for srv in servers:
                tasks.append(collect_server_metrics(srv))

            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for srv, result in zip(servers, results):
                    if isinstance(result, Exception):
                        metrics_cache[srv["host"]] = {
                            "online": False,
                            "last_check": datetime.now().isoformat(),
                        }
                    else:
                        metrics_cache[srv["host"]] = result

                save_json(METRICS_FILE, metrics_cache)

            await asyncio.sleep(interval)

        except Exception as e:
            logger.error(f"Monitor loop error: {e}")
            await asyncio.sleep(30)


def get_metrics(host: str) -> dict:
    return metrics_cache.get(host, {})


def get_all_metrics() -> dict:
    return metrics_cache.copy()
