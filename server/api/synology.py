"""Synology NAS monitoring API endpoints."""

import json
from datetime import datetime
from typing import Dict, List

from fastapi import APIRouter, Request, Depends

from server.auth import require_auth
from server.config import DATA_DIR

router = APIRouter(prefix="/api/synology", tags=["synology"])

# In-memory cache
synology_metrics: Dict[str, dict] = {}

SYNOLOGY_FILE = DATA_DIR / "synology.json"


def _load_synology():
    if SYNOLOGY_FILE.exists():
        with open(SYNOLOGY_FILE) as f:
            return json.load(f)
    return []


def _save_synology(data):
    with open(SYNOLOGY_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


@router.get("/list")
async def synology_list(request: Request, user: str = Depends(require_auth)):
    """List all Synology NAS devices with metrics."""
    devices = _load_synology()
    # Merge with in-memory cache
    for dev in devices:
        name = dev["name"]
        if name in synology_metrics:
            dev["metrics"] = synology_metrics[name]
    return devices


@router.post("/add")
async def synology_add(request: Request, user: str = Depends(require_auth)):
    """Add a Synology NAS device."""
    body = await request.json()
    name = body.get("name", "").strip()
    host = body.get("host", "").strip()
    if not name or not host:
        return {"status": "error", "detail": "name and host required"}

    devices = _load_synology()
    device = {
        "name": name,
        "host": host,
        "port": int(body.get("port", 5000)),
        "https": body.get("https", False),
        "username": body.get("username", ""),
        "password": body.get("password", ""),
        "added": datetime.now().isoformat(),
    }
    devices.append(device)
    _save_synology(devices)

    return {"status": "ok"}


@router.delete("/{name}")
async def synology_delete(name: str, request: Request, user: str = Depends(require_auth)):
    """Remove a Synology NAS device."""
    devices = _load_synology()
    devices = [d for d in devices if d["name"] != name]
    _save_synology(devices)
    synology_metrics.pop(name, None)
    return {"status": "ok"}


@router.post("/refresh/{name}")
async def synology_refresh(name: str, request: Request, user: str = Depends(require_auth)):
    """Force refresh metrics for a Synology device."""
    from server.services.synology_client import SynologyClient

    devices = _load_synology()
    dev = next((d for d in devices if d["name"] == name), None)
    if not dev:
        return {"status": "error", "detail": "device not found"}

    client = SynologyClient(
        host=dev["host"],
        port=dev.get("port", 5000),
        https=dev.get("https", False),
        username=dev.get("username", ""),
        password=dev.get("password", ""),
    )

    try:
        metrics = await client.collect_all_metrics()
        metrics["last_updated"] = datetime.now().isoformat()
        synology_metrics[name] = metrics
        await client.logout()
        return {"status": "ok", "metrics": metrics}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.post("/refresh-all")
async def synology_refresh_all(request: Request, user: str = Depends(require_auth)):
    """Refresh metrics for all Synology devices."""
    from server.services.synology_client import SynologyClient

    devices = _load_synology()
    results = []

    for dev in devices:
        client = SynologyClient(
            host=dev["host"],
            port=dev.get("port", 5000),
            https=dev.get("https", False),
            username=dev.get("username", ""),
            password=dev.get("password", ""),
        )
        try:
            metrics = await client.collect_all_metrics()
            metrics["last_updated"] = datetime.now().isoformat()
            synology_metrics[dev["name"]] = metrics
            await client.logout()
            results.append({"name": dev["name"], "online": metrics["online"]})
        except Exception as e:
            results.append({"name": dev["name"], "online": False, "error": str(e)})

    return {"status": "ok", "results": results}
