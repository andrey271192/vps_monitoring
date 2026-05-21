"""Keenetic router RCI API client for monitoring via KeenDNS."""

import hashlib
import logging
from typing import Optional
from urllib.parse import urlparse

import aiohttp

logger = logging.getLogger(__name__)

KEENDNS_MARKERS = (".pro", ".club", ".link", "netcraze", "keenetic")


def normalize_web_url(url: str) -> str:
    """Ensure web UI URL has a scheme (https by default)."""
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    return url.rstrip("/")


def build_api_base_url(host: str, web_url: str = "") -> str:
    """Build RCI API base URL from host and/or Keenetic web URL column."""
    raw = (host or "").strip()
    if not raw and web_url:
        parsed = urlparse(normalize_web_url(web_url))
        raw = parsed.netloc or (parsed.path.split("/")[0] if parsed.path else "")
    if not raw:
        return ""

    if raw.startswith("http://") or raw.startswith("https://"):
        return raw.rstrip("/")

    domain = raw.split(":")[0].lower()
    is_keendns = any(m in domain for m in KEENDNS_MARKERS)
    scheme = "https" if is_keendns else "http"
    return f"{scheme}://{raw}".rstrip("/")


class KeeneticClient:
    """Async client for Keenetic router RCI API.

    Auth flow:
      1. GET /auth -> 401 with X-NDM-Challenge + X-NDM-Realm headers
      2. Compute: md5(login:realm:password) -> sha256(challenge + md5_hex)
      3. POST /auth {"login": ..., "password": sha256_hex}
      4. Session cookie persists for subsequent requests
    """

    def __init__(self, host: str, login: str = "admin", password: str = "",
                 web_url: str = ""):
        base = build_api_base_url(host, web_url)
        if not base:
            raise ValueError("host or web_url required")
        self.base_url = base
        self.login = login
        self.password = password
        self._session: Optional[aiohttp.ClientSession] = None
        self._authenticated = False
        self.last_error = ""

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=25, connect=10)
            jar = aiohttp.CookieJar(unsafe=True)
            self._session = aiohttp.ClientSession(timeout=timeout, cookie_jar=jar)
        return self._session

    async def authenticate(self) -> bool:
        """Perform challenge-response authentication."""
        self.last_error = ""
        session = await self._get_session()
        auth_url = f"{self.base_url}/auth"

        try:
            async with session.get(auth_url, ssl=False) as resp:
                if resp.status == 200:
                    self._authenticated = True
                    return True

                if resp.status != 401:
                    if resp.status in (400, 403):
                        self.last_error = "Wrong protocol or port (try http/https)"
                    else:
                        self.last_error = f"Auth HTTP {resp.status}"
                    logger.error(f"Keenetic auth unexpected status: {resp.status} @ {self.base_url}")
                    return False

                challenge = resp.headers.get("X-NDM-Challenge", "")
                realm = resp.headers.get("X-NDM-Realm", "")

                if not challenge or not realm:
                    self.last_error = "No auth challenge from router"
                    logger.error("Keenetic auth: missing challenge/realm headers")
                    return False

            md5_input = f"{self.login}:{realm}:{self.password}"
            md5_hex = hashlib.md5(md5_input.encode("utf-8")).hexdigest()
            sha_input = f"{challenge}{md5_hex}"
            sha_hex = hashlib.sha256(sha_input.encode("utf-8")).hexdigest()

            async with session.post(
                auth_url,
                json={"login": self.login, "password": sha_hex},
                ssl=False,
            ) as resp:
                if resp.status == 200:
                    self._authenticated = True
                    return True
                self.last_error = "Wrong login or password"
                logger.error(f"Keenetic auth failed: {resp.status} @ {self.base_url}")
                return False

        except aiohttp.ClientConnectorError as e:
            self.last_error = "Cannot connect to router"
            logger.error(f"Keenetic auth error: {type(e).__name__}: {e}")
            return False
        except TimeoutError:
            self.last_error = "Connection timeout"
            logger.error(f"Keenetic auth timeout @ {self.base_url}")
            return False
        except Exception as e:
            self.last_error = type(e).__name__
            logger.error(f"Keenetic auth error: {type(e).__name__}: {e}")
            return False

    async def rci_show(self, command: str, params: Optional[dict] = None) -> Optional[dict]:
        """GET /rci/show/<command> with optional query params."""
        if not self._authenticated:
            if not await self.authenticate():
                return None

        session = await self._get_session()
        path = command.replace(" ", "/")
        url = f"{self.base_url}/rci/show/{path}"

        try:
            async with session.get(url, params=params, ssl=False) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
                elif resp.status == 401:
                    self._authenticated = False
                    if await self.authenticate():
                        async with session.get(url, params=params, ssl=False) as resp2:
                            if resp2.status == 200:
                                return await resp2.json(content_type=None)
                logger.error(f"Keenetic RCI {command}: HTTP {resp.status}")
                return None
        except Exception as e:
            logger.error(f"Keenetic RCI error ({command}): {type(e).__name__}: {e}")
            return None

    async def rci_post(self, body: dict) -> Optional[dict]:
        """POST /rci/ with JSON body for batch commands."""
        if not self._authenticated:
            if not await self.authenticate():
                return None

        session = await self._get_session()
        url = f"{self.base_url}/rci/"

        try:
            async with session.post(url, json=body, ssl=False) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
                logger.error(f"Keenetic RCI POST: HTTP {resp.status}")
                return None
        except Exception as e:
            logger.error(f"Keenetic RCI POST error: {type(e).__name__}: {e}")
            return None

    async def collect_metrics(self, cached_info: Optional[dict] = None) -> dict:
        """Lightweight refresh: system + internet + VPN only."""
        result = {
            "online": False,
            "hostname": "",
            "model": "",
            "firmware": "",
            "cpuload": 0,
            "memtotal": 0,
            "memfree": 0,
            "mem_percent": 0,
            "uptime": 0,
            "uptime_str": "",
            "internet": False,
            "gateway_accessible": False,
            "dns_accessible": False,
            "vpn": [],
            "clients_count": 0,
            "wifi_clients": 0,
            "wired_clients": 0,
            "error": "",
        }

        if cached_info:
            result["model"] = cached_info.get("model", "")
            result["firmware"] = cached_info.get("firmware", "")

        if not await self.authenticate():
            result["error"] = self.last_error or "Authentication failed"
            return result

        result["online"] = True

        batch_cmd = {
            "show": {
                "system": {},
                "internet": {"status": {}},
                "interface": {},
            }
        }

        need_info = not result.get("model")
        if need_info:
            batch_cmd["show"]["version"] = {}
            batch_cmd["show"]["defaults"] = {}

        batch = await self.rci_post(batch_cmd)

        if not batch or not isinstance(batch, dict):
            result["error"] = "No data from router"
            result["online"] = False
            return result

        show = batch.get("show", batch)

        sys_data = show.get("system", {})
        if sys_data:
            result["hostname"] = sys_data.get("hostname", "")
            result["cpuload"] = int(sys_data.get("cpuload", 0) or 0)
            result["memtotal"] = int(sys_data.get("memtotal", 0) or 0)
            result["memfree"] = int(sys_data.get("memfree", 0) or 0)

            memtotal = result["memtotal"]
            memfree = result["memfree"]
            if memtotal > 0:
                result["mem_percent"] = round((1 - memfree / memtotal) * 100, 1)

            uptime_sec = int(sys_data.get("uptime", 0) or 0)
            result["uptime"] = uptime_sec
            if uptime_sec:
                days = uptime_sec // 86400
                hours = (uptime_sec % 86400) // 3600
                mins = (uptime_sec % 3600) // 60
                result["uptime_str"] = f"{days}d {hours}h {mins}m"

        if need_info:
            ver_data = show.get("version", {})
            if ver_data:
                result["firmware"] = ver_data.get("title", ver_data.get("release", ""))

            defaults = show.get("defaults", {})
            if defaults:
                product = defaults.get("product", "")
                hw_id = defaults.get("ndmhwid", "")
                result["model"] = f"{product} ({hw_id})" if product and hw_id else product or hw_id

        inet_block = show.get("internet", {})
        inet = inet_block.get("status", inet_block) if isinstance(inet_block, dict) else {}
        if inet:
            result["internet"] = bool(inet.get("internet"))
            result["gateway_accessible"] = bool(inet.get("gateway-accessible"))
            result["dns_accessible"] = bool(inet.get("dns-accessible"))

        VPN_TYPES = {"Wireguard", "WireGuard", "OpenVPN", "PPTP", "L2TP", "SSTP", "EoIP", "IPsec"}

        ifaces = show.get("interface", {})
        if ifaces and isinstance(ifaces, dict):
            for iface_name, iface_data in ifaces.items():
                if not isinstance(iface_data, dict):
                    continue
                itype = iface_data.get("type", "")
                if itype in VPN_TYPES:
                    result["vpn"].append({
                        "name": iface_name,
                        "type": itype,
                        "state": iface_data.get("state", ""),
                        "description": iface_data.get("description", ""),
                        "address": iface_data.get("address", ""),
                    })

        return result

    async def collect_detail(self) -> Optional[dict]:
        """Heavy detail fetch: interfaces + connected clients."""
        if not self._authenticated:
            if not await self.authenticate():
                return None

        batch = await self.rci_post({
            "show": {
                "interface": {},
                "ip": {"hotspot": {}},
            }
        })

        if not batch or not isinstance(batch, dict):
            return None

        show = batch.get("show", batch)
        detail = {"interfaces": [], "clients": []}

        VPN_TYPES = {"Wireguard", "WireGuard", "OpenVPN", "PPTP", "L2TP", "SSTP", "EoIP", "IPsec"}
        SHOW_TYPES = {"GigabitEthernet", "XGigabitEthernet", "WifiMaster", "AccessPoint",
                      "Bridge", "PPPoE"} | VPN_TYPES

        ifaces = show.get("interface", {})
        if ifaces and isinstance(ifaces, dict):
            for iface_name, iface_data in ifaces.items():
                if not isinstance(iface_data, dict):
                    continue
                itype = iface_data.get("type", "")
                if itype in SHOW_TYPES:
                    detail["interfaces"].append({
                        "id": iface_data.get("id", iface_name),
                        "type": itype,
                        "description": iface_data.get("description", ""),
                        "state": iface_data.get("state", ""),
                        "address": iface_data.get("address", ""),
                        "uptime": iface_data.get("uptime", 0),
                    })

        ip_block = show.get("ip", {})
        hotspot = ip_block.get("hotspot", ip_block) if isinstance(ip_block, dict) else {}
        if hotspot:
            hosts = hotspot.get("host", [])
            if isinstance(hosts, list):
                for h in hosts:
                    detail["clients"].append({
                        "name": h.get("name", h.get("hostname", "")),
                        "hostname": h.get("hostname", ""),
                        "ip": h.get("ip", ""),
                        "mac": h.get("mac", ""),
                        "active": h.get("active", False),
                        "speed": h.get("speed", 0),
                        "ssid": h.get("ssid", ""),
                    })

        return detail

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
