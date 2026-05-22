"""Keenetic router RCI API client for monitoring via KeenDNS."""

import asyncio
import hashlib
import logging
import re
from typing import Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

KEENDNS_MARKERS = (".pro", ".club", ".link", "netcraze", "keenetic")
AUTH_RETRIES = 2
DEFAULT_TIMEOUT = 25.0
RCI_TIMEOUT = 45.0
_IP_HOST_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


def normalize_web_url(url: str) -> str:
    """Ensure web UI URL has a scheme (https by default)."""
    url = (url or "").strip().rstrip("/")
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def parse_keenetic_web_url(url: str) -> tuple[str, str]:
    """Validate KeenDNS/web URL; return (web_url, host) with port in host."""
    raw = (url or "").strip()
    if not raw:
        raise ValueError("Укажите адрес KeenDNS")
    normalized = normalize_web_url(raw if "://" in raw else raw)
    parsed = urlparse(normalized)
    if not parsed.scheme or parsed.scheme not in ("http", "https"):
        raise ValueError("Адрес должен начинаться с http:// или https://")
    if not parsed.netloc or not parsed.hostname:
        raise ValueError("Некорректный формат адреса")
    return normalized, parsed.netloc


def is_public_ip_host(host: str) -> bool:
    """True when host is a bare IPv4 (optional :port), not KeenDNS."""
    if not host:
        return False
    return bool(_IP_HOST_RE.match(host.split(":")[0]))


def is_keendns_host(host: str) -> bool:
    domain = (host or "").split(":")[0].lower()
    return any(m in domain for m in KEENDNS_MARKERS)


def _default_port(scheme: str) -> int:
    return 443 if scheme == "https" else 80


def resolve_api_base(web_url: str = "", host: str = "") -> str:
    """Build RCI base URL (scheme + host + port) — keenetic-unified rci_base_url pattern."""
    raw = (web_url or host or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        scheme = "http" if is_public_ip_host(raw.split("/")[0]) else "https"
        raw = f"{scheme}://{raw.lstrip('/')}"
    try:
        parsed = urlparse(raw)
    except Exception:
        return ""
    hostname = (parsed.hostname or "").strip()
    if not hostname:
        return ""
    scheme = (parsed.scheme or "https").lower()
    if scheme not in ("http", "https"):
        scheme = "https"
    port = parsed.port if parsed.port is not None else _default_port(scheme)
    netloc = hostname if port == _default_port(scheme) else f"{hostname}:{port}"
    return f"{scheme}://{netloc}"


def build_api_base_url(host: str, web_url: str = "") -> str:
    """Prefer scheme/host/port from web_url over bare host."""
    if web_url:
        base = resolve_api_base(web_url=web_url)
        if base:
            return base
    return resolve_api_base(host=host)


async def _authenticate(
    client: httpx.AsyncClient, base: str, login: str, password: str,
) -> tuple[bool, str]:
    """Keenetic /auth challenge-response (keenetic-unified keenetic_rci pattern)."""
    auth_url = f"{base.rstrip('/')}/auth"
    try:
        resp = await client.get(auth_url)
        if resp.status_code == 200:
            return True, ""
        if resp.status_code != 401:
            if resp.status_code in (400, 403):
                return False, "Wrong protocol or port (try http/https)"
            return False, f"Auth HTTP {resp.status_code}"

        realm = resp.headers.get("X-NDM-Realm", "")
        challenge = resp.headers.get("X-NDM-Challenge", "")
        if not realm or not challenge:
            return False, "No auth challenge from router"

        md5_hex = hashlib.md5(f"{login}:{realm}:{password}".encode()).hexdigest()
        sha_hex = hashlib.sha256(f"{challenge}{md5_hex}".encode()).hexdigest()
        resp2 = await client.post(auth_url, json={"login": login, "password": sha_hex})
        if resp2.status_code == 200:
            return True, ""
        return False, "Wrong login or password"
    except httpx.TimeoutException:
        return False, "timeout"
    except httpx.ConnectError as exc:
        err = str(exc).lower()
        if "name or service not known" in err or "nodename nor servname" in err:
            return False, "dns"
        return False, "connect"
    except Exception as exc:
        logger.warning("Keenetic auth %s: %s", base, exc)
        return False, type(exc).__name__


class KeeneticClient:
    """Async client for Keenetic router RCI API via httpx (KeenDNS relay)."""

    def __init__(self, host: str, login: str = "admin", password: str = "",
                 web_url: str = ""):
        base = build_api_base_url(host, web_url)
        if not base:
            raise ValueError("host or web_url required")
        self.base_url = base
        parsed = urlparse(base)
        self._host_key = parsed.netloc or host
        self.login = login
        self.password = password
        self._client: Optional[httpx.AsyncClient] = None
        self.last_error = ""

    async def _get_client(self, timeout: float = DEFAULT_TIMEOUT) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=timeout,
                verify=False,
                follow_redirects=True,
                headers={"User-Agent": "VPS-Monitoring/1.0"},
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    def _timeout_error_message(self) -> str:
        if is_public_ip_host(self._host_key):
            return (
                "HTTP API не отвечает с VPS (прямой IP). "
                "Нужен KeenDNS или удалённый доступ Keenetic."
            )
        return "Connection timeout"

    async def authenticate(self) -> bool:
        """Perform challenge-response authentication with retries."""
        self.last_error = ""
        for attempt in range(AUTH_RETRIES):
            client = await self._get_client()
            ok, err = await _authenticate(client, self.base_url, self.login, self.password)
            if ok:
                return True
            if err == "dns":
                self.last_error = "DNS не резолвится с VPS"
                return False
            if err == "Wrong login or password":
                self.last_error = err
                return False
            if err in ("Wrong protocol or port (try http/https)",) or err.startswith("Auth HTTP"):
                self.last_error = err
                return False
            if err == "No auth challenge from router":
                self.last_error = err
                return False
            if err == "connect":
                self.last_error = "Cannot connect to router"
                return False
            if err == "timeout":
                self.last_error = self._timeout_error_message()
            else:
                self.last_error = err or self._timeout_error_message()

            if attempt + 1 < AUTH_RETRIES:
                logger.warning(
                    f"Keenetic auth retry ({attempt + 1}/{AUTH_RETRIES}) "
                    f"@ {self.base_url}: {self.last_error}"
                )
                await self.close()
                await asyncio.sleep(1.5 * (attempt + 1))
        return False

    async def rci_show(self, command: str, params: Optional[dict] = None) -> Optional[dict]:
        """GET /rci/show/<command> with optional query params."""
        if not await self.authenticate():
            return None

        client = await self._get_client(timeout=RCI_TIMEOUT)
        path = command.replace(" ", "/")
        url = f"{self.base_url}/rci/show/{path}"

        try:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 401 and await self.authenticate():
                resp = await client.get(url, params=params)
                if resp.status_code == 200:
                    return resp.json()
            logger.error(f"Keenetic RCI {command}: HTTP {resp.status_code}")
            return None
        except Exception as e:
            logger.error(f"Keenetic RCI error ({command}): {type(e).__name__}: {e}")
            return None

    async def rci_post(self, body: dict) -> Optional[dict]:
        """POST /rci/ with JSON body for batch commands."""
        if not await self.authenticate():
            return None

        url = f"{self.base_url}/rci/"
        for attempt in range(AUTH_RETRIES):
            try:
                client = await self._get_client(timeout=RCI_TIMEOUT)
                resp = await client.post(url, json=body)
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code == 401:
                    await self.close()
                    if not await self.authenticate():
                        return None
                    continue
                logger.error(f"Keenetic RCI POST: HTTP {resp.status_code}")
                return None
            except httpx.TimeoutException:
                logger.warning(
                    f"Keenetic RCI POST timeout ({attempt + 1}/{AUTH_RETRIES}) @ {self.base_url}"
                )
                await self.close()
                if not await self.authenticate():
                    return None
                if attempt + 1 < AUTH_RETRIES:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                return None
            except Exception as e:
                logger.error(f"Keenetic RCI POST error: {type(e).__name__}: {e}")
                return None
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
