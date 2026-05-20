"""Synology DSM API client for NAS monitoring."""

import logging
from typing import Optional, Dict, Any

import aiohttp

logger = logging.getLogger(__name__)


class SynologyClient:
    """Client for Synology DSM 6/7 REST API."""

    def __init__(self, host: str, port: int = 5000, https: bool = False,
                 username: str = "", password: str = ""):
        proto = "https" if https else "http"
        self.base_url = f"{proto}://{host}:{port}"
        self.username = username
        self.password = password
        self.sid: Optional[str] = None

    async def login(self) -> bool:
        """Authenticate and get session ID."""
        try:
            url = f"{self.base_url}/webapi/auth.cgi"
            params = {
                "api": "SYNO.API.Auth",
                "version": "6",
                "method": "login",
                "account": self.username,
                "passwd": self.password,
                "session": "VPSMonitor",
                "format": "sid",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10),
                                       ssl=False) as resp:
                    data = await resp.json()
                    if data.get("success"):
                        self.sid = data["data"]["sid"]
                        return True
                    logger.error(f"Synology login failed: {data}")
                    return False
        except Exception as e:
            logger.error(f"Synology login error: {e}")
            return False

    async def _api_call(self, cgi: str, api: str, version: str = "1",
                        method: str = "get", extra_params: dict = None) -> Optional[dict]:
        """Make authenticated API call."""
        if not self.sid:
            if not await self.login():
                return None

        url = f"{self.base_url}/webapi/{cgi}"
        params = {
            "api": api,
            "version": version,
            "method": method,
            "_sid": self.sid,
        }
        if extra_params:
            params.update(extra_params)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15),
                                       ssl=False) as resp:
                    data = await resp.json()
                    if data.get("success"):
                        return data.get("data", {})
                    # Session expired? Re-login once
                    if data.get("error", {}).get("code") == 119:
                        self.sid = None
                        if await self.login():
                            params["_sid"] = self.sid
                            async with session.get(url, params=params, ssl=False) as resp2:
                                data2 = await resp2.json()
                                if data2.get("success"):
                                    return data2.get("data", {})
                    return None
        except Exception as e:
            logger.error(f"Synology API error ({api}): {e}")
            return None

    async def get_system_info(self) -> Optional[dict]:
        """Get DSM system info (model, version, uptime, temperature)."""
        return await self._api_call("entry.cgi", "SYNO.DSM.Info", version="2", method="getinfo")

    async def get_cpu_memory(self) -> Optional[dict]:
        """Get CPU and memory utilization."""
        return await self._api_call("entry.cgi", "SYNO.Core.System.Utilization", version="1")

    async def get_storage(self) -> Optional[dict]:
        """Get storage pool and volume info."""
        return await self._api_call("entry.cgi", "SYNO.Storage.CGI.Storage", version="1",
                                    method="load_info")

    async def get_network(self) -> Optional[dict]:
        """Get network interface info."""
        return await self._api_call("entry.cgi", "SYNO.Core.System.Utilization", version="1")

    async def get_vms(self) -> Optional[dict]:
        """Get Virtual Machine Manager guests (VMM package required)."""
        return await self._api_call("entry.cgi", "SYNO.Virtualization.API.Guest", version="1",
                                    method="list", extra_params={"offset": "0", "limit": "50"})

    async def get_docker_containers(self) -> Optional[dict]:
        """Get Docker/Container Manager containers."""
        return await self._api_call("entry.cgi", "SYNO.Docker.Container", version="1",
                                    method="list", extra_params={"offset": "0", "limit": "50"})

    async def get_disk_info(self) -> Optional[dict]:
        """Get physical disk info (SMART, temperature)."""
        return await self._api_call("entry.cgi", "SYNO.Storage.CGI.Storage", version="1",
                                    method="load_info")

    async def get_services(self) -> Optional[dict]:
        """Get running services/packages."""
        return await self._api_call("entry.cgi", "SYNO.Core.Package", version="2",
                                    method="list")

    async def collect_all_metrics(self) -> dict:
        """Collect all metrics in one go."""
        result = {
            "online": False,
            "system": {},
            "cpu_percent": 0,
            "ram_percent": 0,
            "ram_used_mb": 0,
            "ram_total_mb": 0,
            "volumes": [],
            "disks": [],
            "vms": [],
            "docker": [],
            "temperature": 0,
            "uptime": "",
            "model": "",
            "dsm_version": "",
        }

        # System info
        sys_info = await self.get_system_info()
        if sys_info is None:
            return result

        result["online"] = True
        result["model"] = sys_info.get("model", "")
        result["dsm_version"] = f"DSM {sys_info.get('version_string', '')}"
        result["temperature"] = sys_info.get("temperature", 0)
        result["uptime"] = _format_uptime(sys_info.get("up_time", 0))

        # CPU / Memory
        util = await self.get_cpu_memory()
        if util:
            cpu_data = util.get("cpu", {})
            if cpu_data:
                # CPU total = user + system
                user = cpu_data.get("user_load", 0)
                sys_load = cpu_data.get("system_load", 0)
                result["cpu_percent"] = user + sys_load

            mem_data = util.get("memory", {})
            if mem_data:
                total = mem_data.get("memory_size", 0) / 1024  # KB to MB
                avail = mem_data.get("avail_swap", 0)
                real_use = mem_data.get("real_usage", 0)
                result["ram_total_mb"] = round(total)
                result["ram_percent"] = real_use
                result["ram_used_mb"] = round(total * real_use / 100)

        # Storage
        storage = await self.get_storage()
        if storage:
            for vol in storage.get("volumes", []):
                total_bytes = vol.get("size", {}).get("total", 0)
                used_bytes = vol.get("size", {}).get("used", 0)
                total_gb = total_bytes / (1024 ** 3) if total_bytes else 0
                used_gb = used_bytes / (1024 ** 3) if used_bytes else 0
                percent = round(used_gb / total_gb * 100, 1) if total_gb > 0 else 0
                result["volumes"].append({
                    "name": vol.get("display_name", vol.get("id", "")),
                    "total_gb": round(total_gb, 1),
                    "used_gb": round(used_gb, 1),
                    "percent": percent,
                    "status": vol.get("status", ""),
                })

            for disk in storage.get("disks", []):
                result["disks"].append({
                    "name": disk.get("name", ""),
                    "model": disk.get("model", ""),
                    "temp": disk.get("temp", 0),
                    "status": disk.get("status", ""),
                    "size_gb": round(int(disk.get("size_total", 0)) / (1024 ** 3), 1),
                    "smart_status": disk.get("smart_status", ""),
                })

        # VMs
        vms = await self.get_vms()
        if vms:
            for vm in vms.get("guests", []):
                result["vms"].append({
                    "name": vm.get("guest_name", ""),
                    "status": vm.get("status", ""),
                    "vcpu": vm.get("vcpu_num", 0),
                    "ram_mb": vm.get("vram_size", 0),
                    "autorun": vm.get("autorun", 0),
                })

        # Docker
        docker = await self.get_docker_containers()
        if docker:
            for c in docker.get("containers", []):
                result["docker"].append({
                    "name": c.get("name", ""),
                    "status": c.get("status", ""),
                    "image": c.get("image", ""),
                    "state": c.get("state", ""),
                })

        return result

    async def logout(self):
        """Close session."""
        if self.sid:
            try:
                await self._api_call("auth.cgi", "SYNO.API.Auth", version="6", method="logout")
            except Exception:
                pass
            self.sid = None


def _format_uptime(seconds: int) -> str:
    """Format seconds to human-readable uptime."""
    if not seconds:
        return "N/A"
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    if days > 0:
        return f"{days}d {hours}h"
    return f"{hours}h {(seconds % 3600) // 60}m"
