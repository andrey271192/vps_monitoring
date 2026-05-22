"""Keenetic router RCI API client for monitoring via KeenDNS."""

import asyncio
import hashlib
import logging
import re
import socket
from typing import Optional
from urllib.parse import urlparse

import aiohttp

logger = logging.getLogger(__name__)

KEENDNS_MARKERS = (".pro", ".club", ".link", "netcraze", "keenetic")
AUTH_RETRIES = 2
BLOCKED_IPS = frozenset({"0.0.0.0", "127.0.0.1"})
_IP_HOST_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


def normalize_web_url(url: str) -> str:
    """Ensure web UI URL has a scheme (https by default)."""
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    return url.rstrip("/")


def parse_keenetic_web_url(url: str) -> tuple[str, str]:
    """Validate KeenDNS/web URL; return (web_url, host) with port in host."""
    raw = (url or "").strip()
    if not raw:
        raise ValueError("Укажите адрес KeenDNS")
    if "://" in raw:
        normalized = raw.rstrip("/")
    else:
        normalized = f"https://{raw}".rstrip("/")
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


def client_timeout_for(host: str, *, probing: bool = False) -> aiohttp.ClientTimeout:
    """Timeouts tuned for KeenDNS vs direct IP."""
    if probing:
        return aiohttp.ClientTimeout(total=15, connect=4, sock_read=10)
    if is_public_ip_host(host):
        return aiohttp.ClientTimeout(total=20, connect=8, sock_read=12)
    return aiohttp.ClientTimeout(total=45, connect=12, sock_read=30)


async def resolve_ipv4_addresses(hostname: str) -> list[str]:
    """Resolve KeenDNS A records, skipping placeholder/blocked addresses."""
    if not hostname or is_public_ip_host(hostname.split(":")[0]):
        return []
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(
            hostname, None, family=socket.AF_INET, type=socket.SOCK_STREAM,
        )
    except socket.gaierror:
        return []
    result, seen = [], set()
    for info in infos:
        ip = info[4][0]
        if ip in BLOCKED_IPS or ip in seen:
            continue
        seen.add(ip)
        result.append(ip)
    return result


def build_api_base_url(host: str, web_url: str = "") -> str:
    """Build RCI API base URL — prefer scheme/host/port from web_url."""
    if web_url:
        parsed = urlparse(normalize_web_url(web_url))
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")

    raw = (host or "").strip()
    if not raw:
        return ""

    if raw.startswith("http://") or raw.startswith("https://"):
        return raw.rstrip("/")

    scheme = "https" if is_keendns_host(raw) else "http"
    return f"{scheme}://{raw}".rstrip("/")


def _make_connector() -> aiohttp.TCPConnector:
    """IPv4-only: avoids aiohttp hanging on broken IPv6 for KeenDNS multi-A records."""
    return aiohttp.TCPConnector(
        family=socket.AF_INET,
        force_close=True,
        enable_cleanup_closed=True,
        ttl_dns_cache=30,
    )


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
        parsed = urlparse(base)
        self._host_key = parsed.netloc or host
        self._hostname = parsed.hostname or ""
        self._port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self._scheme = parsed.scheme or "https"
        self._netloc = parsed.netloc or host
        self._active_target: Optional[str] = None
        self._resolved_ips: list[str] = []
        self.login = login
        self.password = password
        self._session: Optional[aiohttp.ClientSession] = None
        self._authenticated = False
        self.last_error = ""

    def _effective_base(self) -> str:
        if self._active_target:
            port = f":{self._port}" if self._port not in (80, 443) else ""
            return f"{self._scheme}://{self._active_target}{port}"
        return self.base_url.rstrip("/")

    def _request_headers(self) -> dict:
        headers = {"User-Agent": "VPS-Monitoring/1.0"}
        if self._active_target:
            headers["Host"] = self._netloc
        return headers

    async def _connection_targets(self) -> list[str]:
        if is_public_ip_host(self._hostname):
            return [self._hostname]
        if not self._resolved_ips:
            self._resolved_ips = await resolve_ipv4_addresses(self._hostname)
        return self._resolved_ips + [self._hostname]

    async def _get_session(self, *, probing: bool = False) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = client_timeout_for(self._host_key, probing=probing)
            jar = aiohttp.CookieJar(unsafe=True)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                cookie_jar=jar,
                connector=_make_connector(),
                version=aiohttp.HttpVersion11,
                headers=self._request_headers(),
            )
        return self._session

    async def _reset_session(self, *, keep_auth: bool = False):
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None
        if not keep_auth:
            self._authenticated = False

    def _timeout_error_message(self) -> str:
        if is_public_ip_host(self._host_key):
            return (
                "HTTP API не отвечает с VPS (прямой IP). "
                "Нужен KeenDNS или удалённый доступ Keenetic."
            )
        return "Connection timeout"

    async def _authenticate_once(self) -> bool:
        """Single auth attempt; tries each KeenDNS A record before giving up."""
        self.last_error = ""
        retryable = (
            aiohttp.ServerTimeoutError,
            aiohttp.ClientOSError,
            asyncio.TimeoutError,
            TimeoutError,
        )
        targets = await self._connection_targets()
        last_err: Optional[Exception] = None

        for target in targets:
            await self._reset_session()
            self._active_target = target if is_public_ip_host(target) else None
            auth_url = f"{self._effective_base()}/auth"

            try:
                session = await self._get_session(probing=True)
                async with session.get(auth_url, ssl=False) as resp:
                    if resp.status == 200:
                        self._authenticated = True
                        await self._reset_session(keep_auth=True)
                        return True

                    if resp.status != 401:
                        if resp.status in (400, 403):
                            self.last_error = "Wrong protocol or port (try http/https)"
                            return False
                        if resp.status in (502, 503, 504):
                            continue
                        self.last_error = f"Auth HTTP {resp.status}"
                        logger.error(
                            f"Keenetic auth unexpected status: {resp.status} @ {auth_url}"
                        )
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

                session = await self._get_session()
                async with session.post(
                    auth_url,
                    json={"login": self.login, "password": sha_hex},
                    ssl=False,
                ) as resp:
                    if resp.status == 200:
                        self._authenticated = True
                        await self._reset_session(keep_auth=True)
                        return True
                    self.last_error = "Wrong login or password"
                    logger.error(f"Keenetic auth failed: {resp.status} @ {auth_url}")
                    return False
            except aiohttp.ClientConnectorError as e:
                last_err = e
                err = str(e).lower()
                if "name or service not known" in err or "nodename nor servname" in err:
                    self.last_error = "DNS не резолвится с VPS"
                    return False
                continue
            except retryable as e:
                last_err = e
                logger.debug(
                    f"Keenetic auth try failed @ {auth_url}: {type(e).__name__}"
                )
                continue

        if last_err:
            if isinstance(last_err, aiohttp.ClientConnectorError):
                self.last_error = "Cannot connect to router"
            else:
                self.last_error = self._timeout_error_message()
        else:
            self.last_error = self._timeout_error_message()
        return False

    async def authenticate(self) -> bool:
        """Perform challenge-response authentication with retries."""
        for attempt in range(AUTH_RETRIES):
            if attempt:
                self._resolved_ips = await resolve_ipv4_addresses(self._hostname)
                await self._reset_session()
            if await self._authenticate_once():
                return True
            if self.last_error == "DNS не резолвится с VPS":
                return False
            if attempt + 1 < AUTH_RETRIES:
                logger.warning(
                    f"Keenetic auth retry ({attempt + 1}/{AUTH_RETRIES}) "
                    f"@ {self.base_url}: {self.last_error}"
                )
                await asyncio.sleep(1.5 * (attempt + 1))
        return False

    async def rci_show(self, command: str, params: Optional[dict] = None) -> Optional[dict]:
        """GET /rci/show/<command> with optional query params."""
        if not self._authenticated:
            if not await self.authenticate():
                return None

        session = await self._get_session()
        path = command.replace(" ", "/")
        url = f"{self._effective_base()}/rci/show/{path}"

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

        retryable = (
            aiohttp.ServerTimeoutError,
            aiohttp.ClientOSError,
            asyncio.TimeoutError,
            TimeoutError,
        )
        url = f"{self._effective_base()}/rci/"
        for attempt in range(AUTH_RETRIES):
            try:
                session = await self._get_session()
                async with session.post(url, json=body, ssl=False) as resp:
                    if resp.status == 200:
                        return await resp.json(content_type=None)
                    if resp.status == 401:
                        self._authenticated = False
                        if await self.authenticate():
                            continue
                    logger.error(f"Keenetic RCI POST: HTTP {resp.status}")
                    return None
            except retryable as e:
                logger.warning(
                    f"Keenetic RCI POST timeout ({attempt + 1}/{AUTH_RETRIES}) "
                    f"@ {self.base_url}: {type(e).__name__}"
                )
                await self._reset_session()
                if not await self.authenticate():
                    return None
                if attempt + 1 < AUTH_RETRIES:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                logger.error(f"Keenetic RCI POST error: {type(e).__name__}: {e}")
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
