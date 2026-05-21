"""Keenetic router monitoring API endpoints."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List
from urllib.parse import urlparse

from fastapi import APIRouter, Request, Depends

from server.auth import require_auth
from server.config import DATA_DIR, load_settings
from server.services.keenetic_client import (
    KeeneticClient,
    normalize_web_url,
    parse_keenetic_web_url,
    build_api_base_url,
)

router = APIRouter(prefix="/api/keenetic", tags=["keenetic"])
logger = logging.getLogger(__name__)

keenetic_metrics: Dict[str, dict] = {}
_refresh_all_running = False

KEENETIC_FILE = DATA_DIR / "keenetic.json"
DEVICE_REFRESH_TIMEOUT = 75
REFRESH_ALL_GAP_SEC = 2


def _load_keenetic():
    if KEENETIC_FILE.exists():
        with open(KEENETIC_FILE) as f:
            return json.load(f)
    return []


def _save_keenetic(data):
    with open(KEENETIC_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _host_from_url(url: str) -> str:
    """host:port for API from Keenetic web URL."""
    parsed = urlparse(normalize_web_url(url))
    return parsed.netloc or url.replace("https://", "").replace("http://", "").rstrip("/")


def _make_device(name: str, keenetic_url: str, login: str, password: str,
                 anydesk: str = "") -> dict:
    keenetic_url = (keenetic_url or "").strip()
    host = _host_from_url(keenetic_url) if keenetic_url else ""
    return {
        "name": name,
        "host": host,
        "web_url": normalize_web_url(keenetic_url) if keenetic_url else "",
        "anydesk": (anydesk or "").strip(),
        "login": login,
        "password": password,
        "added": datetime.now().isoformat(),
    }


def _client_for_device(dev: dict) -> KeeneticClient:
    return KeeneticClient(
        host=dev.get("host", ""),
        login=dev.get("login", "admin"),
        password=dev.get("password", ""),
        web_url=dev.get("web_url", ""),
    )


async def _refresh_device(dev: dict) -> dict:
    name = dev["name"]
    client = _client_for_device(dev)
    try:
        cached = keenetic_metrics.get(name)
        try:
            metrics = await asyncio.wait_for(
                client.collect_metrics(cached_info=cached),
                timeout=DEVICE_REFRESH_TIMEOUT,
            )
        except asyncio.TimeoutError:
            metrics = {
                "online": False,
                "error": "Poll timeout",
                "last_updated": datetime.now().isoformat(),
            }
        else:
            metrics["last_updated"] = datetime.now().isoformat()
        keenetic_metrics[name] = metrics
        return metrics
    finally:
        await client.close()


@router.get("/list")
async def keenetic_list(request: Request, user: str = Depends(require_auth)):
    devices = _load_keenetic()
    for dev in devices:
        name = dev["name"]
        if name in keenetic_metrics:
            dev["metrics"] = keenetic_metrics[name]
    return devices


@router.post("/add")
async def keenetic_add(request: Request, user: str = Depends(require_auth)):
    body = await request.json()
    name = body.get("name", "").strip()
    host = body.get("host", "").strip()
    web_url = body.get("web_url", "").strip()
    if not name or (not host and not web_url):
        return {"status": "error", "detail": "name and host (or web_url) required"}

    if not host and web_url:
        host = _host_from_url(web_url)

    devices = _load_keenetic()
    device = {
        "name": name,
        "host": host,
        "web_url": normalize_web_url(web_url or host),
        "anydesk": body.get("anydesk", "").strip(),
        "login": body.get("login", "admin"),
        "password": body.get("password", ""),
        "added": datetime.now().isoformat(),
    }
    devices.append(device)
    _save_keenetic(devices)
    return {"status": "ok"}


@router.post("/import")
async def keenetic_import(request: Request, user: str = Depends(require_auth)):
    """Import routers from spreadsheet columns: Address, Keenetic, AnyDesk."""
    body = await request.json()
    login = body.get("login", "admin").strip()
    password = body.get("password", "")
    rows = body.get("rows")
    tsv = body.get("tsv", "").strip()

    parsed: List[dict] = []
    if tsv:
        lines = [l for l in tsv.splitlines() if l.strip()]
        if not lines:
            return {"status": "error", "detail": "Empty import"}
        header = [c.strip().lower() for c in lines[0].split("\t")]
        if len(header) < 2:
            header = [c.strip().lower() for c in lines[0].split(",")]
        start = 1 if any(h in ("address", "keenetic", "anydesk", "имя") for h in header) else 0
        if start == 0:
            header = ["address", "keenetic", "anydesk"]
        col = {h: i for i, h in enumerate(header)}

        def col_val(parts, *keys):
            for k in keys:
                if k in col and col[k] < len(parts):
                    return parts[col[k]].strip()
            return ""

        for line in lines[start:]:
            parts = line.split("\t") if "\t" in line else line.split(",")
            addr = col_val(parts, "address", "имя", "name")
            keen = col_val(parts, "keenetic", "url", "веб")
            ad = col_val(parts, "anydesk", "any desk")
            if keen or addr:
                parsed.append({"address": addr, "keenetic": keen, "anydesk": ad})
    elif rows:
        parsed = rows
    else:
        return {"status": "error", "detail": "Provide rows or tsv"}

    devices = _load_keenetic()
    existing_hosts = {d.get("host") for d in devices}
    existing_names = {d["name"] for d in devices}
    added, skipped = [], []

    for row in parsed:
        keen_url = (row.get("keenetic") or row.get("url") or "").strip()
        if not keen_url:
            continue
        host = _host_from_url(keen_url)
        addr = (row.get("address") or row.get("name") or "").strip()
        name = addr.capitalize() if addr else host.split(".")[0].capitalize()
        base_name, counter = name, 2
        while name in existing_names:
            name = f"{base_name}_{counter}"
            counter += 1
        if host in existing_hosts:
            skipped.append(host)
            continue
        device = _make_device(name, keen_url, login, password, row.get("anydesk", ""))
        devices.append(device)
        existing_hosts.add(host)
        existing_names.add(name)
        added.append(name)

    _save_keenetic(devices)
    return {"status": "ok", "added": added, "skipped": skipped}


@router.post("/add-bulk")
async def keenetic_add_bulk(request: Request, user: str = Depends(require_auth)):
    body = await request.json()
    domains_raw = body.get("domains", "")
    login = body.get("login", "admin").strip()
    password = body.get("password", "")

    lines = [l.strip() for l in domains_raw.strip().splitlines() if l.strip()]
    if not lines:
        return {"status": "error", "detail": "No domains provided"}

    devices = _load_keenetic()
    existing = {d["name"] for d in devices}
    existing_hosts = {d.get("host") for d in devices}
    added, skipped = [], []

    for raw in lines:
        keen_url = raw if "://" in raw else f"https://{raw}"
        host = _host_from_url(keen_url)
        name = host.split(".")[0].capitalize() if "." in host else host
        base_name, counter = name, 2
        while name in existing:
            name = f"{base_name}_{counter}"
            counter += 1
        if host in existing_hosts:
            skipped.append(host)
            continue
        device = _make_device(name, keen_url, login, password)
        devices.append(device)
        existing.add(name)
        existing_hosts.add(host)
        added.append(name)

    _save_keenetic(devices)
    return {"status": "ok", "added": added, "skipped": skipped}


@router.patch("/{name}")
async def keenetic_update(name: str, request: Request, user: str = Depends(require_auth)):
    """Update KeenDNS/web URL for a router (web_url + host)."""
    body = await request.json()
    web_url_raw = (body.get("web_url") or body.get("url") or "").strip()
    if not web_url_raw:
        return {"status": "error", "detail": "web_url required"}

    try:
        web_url, host = parse_keenetic_web_url(web_url_raw)
    except ValueError as e:
        return {"status": "error", "detail": str(e)}

    devices = _load_keenetic()
    idx = next((i for i, d in enumerate(devices) if d["name"] == name), None)
    if idx is None:
        return {"status": "error", "detail": "router not found"}

    devices[idx]["web_url"] = web_url
    devices[idx]["host"] = host
    _save_keenetic(devices)
    keenetic_metrics.pop(name, None)

    result = {"status": "ok", "web_url": web_url, "host": host}
    if body.get("refresh", True):
        try:
            metrics = await _refresh_device(devices[idx])
            result["metrics"] = metrics
        except Exception as e:
            result["refresh_error"] = str(e)

    return result


@router.delete("/{name}")
async def keenetic_delete(name: str, request: Request, user: str = Depends(require_auth)):
    devices = _load_keenetic()
    devices = [d for d in devices if d["name"] != name]
    _save_keenetic(devices)
    keenetic_metrics.pop(name, None)
    return {"status": "ok"}


@router.post("/refresh/{name}")
async def keenetic_refresh(name: str, request: Request, user: str = Depends(require_auth)):
    devices = _load_keenetic()
    dev = next((d for d in devices if d["name"] == name), None)
    if not dev:
        return {"status": "error", "detail": "router not found"}

    try:
        metrics = await _refresh_device(dev)
        if not metrics["online"] and metrics.get("error"):
            return {"status": "error", "detail": metrics["error"], "metrics": metrics}
        return {"status": "ok", "metrics": metrics}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


async def _refresh_all_devices() -> list:
    global _refresh_all_running
    devices = _load_keenetic()
    results = []
    try:
        for i, dev in enumerate(devices):
            try:
                metrics = await _refresh_device(dev)
                results.append({
                    "name": dev["name"],
                    "online": metrics["online"],
                    "error": metrics.get("error", ""),
                })
            except Exception as e:
                results.append({"name": dev["name"], "online": False, "error": str(e)})
            if i + 1 < len(devices):
                await asyncio.sleep(REFRESH_ALL_GAP_SEC)
    finally:
        _refresh_all_running = False
    return results


@router.post("/refresh-all")
async def keenetic_refresh_all(request: Request, user: str = Depends(require_auth)):
    global _refresh_all_running
    if _refresh_all_running:
        return {"status": "ok", "message": "refresh already running"}

    devices = _load_keenetic()
    if not devices:
        return {"status": "ok", "results": []}

    _refresh_all_running = True
    asyncio.create_task(_refresh_all_devices())
    return {
        "status": "ok",
        "message": f"refresh started for {len(devices)} routers",
        "count": len(devices),
    }


@router.get("/detail/{name}")
async def keenetic_detail(name: str, request: Request, user: str = Depends(require_auth)):
    devices = _load_keenetic()
    dev = next((d for d in devices if d["name"] == name), None)
    if not dev:
        return {"status": "error", "detail": "router not found"}

    client = _client_for_device(dev)
    try:
        detail = await client.collect_detail()
        if detail:
            return {"status": "ok", **detail}
        return {"status": "error", "detail": client.last_error or "No data"}
    finally:
        await client.close()


@router.post("/reboot/{name}")
async def keenetic_reboot(name: str, request: Request, user: str = Depends(require_auth)):
    devices = _load_keenetic()
    dev = next((d for d in devices if d["name"] == name), None)
    if not dev:
        return {"status": "error", "detail": "router not found"}

    client = _client_for_device(dev)
    try:
        if not await client.authenticate():
            return {"status": "error", "detail": client.last_error or "Authentication failed"}
        await client.rci_post({"system": {"reboot": {}}})
        return {"status": "ok", "detail": f"Reboot command sent to {name}"}
    finally:
        await client.close()


async def keenetic_monitor_loop():
    """Background polling for all Keenetic routers."""
    await asyncio.sleep(15)
    while True:
        try:
            devices = _load_keenetic()
            if devices:
                logger.info(f"Keenetic monitor: refreshing {len(devices)} routers")
                for dev in devices:
                    try:
                        await _refresh_device(dev)
                    except Exception as e:
                        logger.error(f"Keenetic refresh {dev['name']}: {e}")
                    await asyncio.sleep(3)
        except Exception as e:
            logger.error(f"Keenetic monitor loop error: {e}")

        settings = load_settings()
        interval = int(settings.get("keenetic_interval", 60))
        await asyncio.sleep(max(interval, 30))
