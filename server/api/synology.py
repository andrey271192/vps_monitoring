"""Synology NAS monitoring API endpoints."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from fastapi import APIRouter, Request, Depends
from fastapi.responses import PlainTextResponse

from server.auth import require_auth
from server.config import DATA_DIR, BASE_DIR

router = APIRouter(prefix="/api/synology", tags=["synology"])

# Tunnel config
TUNNEL_KEY_DIR = Path(BASE_DIR) / "tunnel_keys"
TUNNEL_VPS_PORT = 15000  # VPS listens on this port, tunneled to Synology

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
        if not metrics["online"] and metrics.get("error"):
            return {"status": "error", "detail": metrics["error"], "metrics": metrics}
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


@router.post("/tunnel/enable/{name}")
async def synology_enable_tunnel(name: str, request: Request, user: str = Depends(require_auth)):
    """Enable tunnel mode for a Synology device — VPS connects via localhost tunnel."""
    body = await request.json()
    local_ip = body.get("local_ip", "192.168.88.6")
    local_port = body.get("local_port", 5000)

    devices = _load_synology()
    dev = next((d for d in devices if d["name"] == name), None)
    if not dev:
        return {"status": "error", "detail": "device not found"}

    # Save original host and switch to tunnel
    dev["original_host"] = dev.get("original_host", dev["host"])
    dev["host"] = "127.0.0.1"
    dev["port"] = TUNNEL_VPS_PORT
    dev["https"] = False
    dev["tunnel"] = {
        "enabled": True,
        "local_ip": local_ip,
        "local_port": local_port,
        "vps_port": TUNNEL_VPS_PORT,
    }
    _save_synology(devices)

    return {"status": "ok", "vps_port": TUNNEL_VPS_PORT}


@router.post("/tunnel/disable/{name}")
async def synology_disable_tunnel(name: str, request: Request, user: str = Depends(require_auth)):
    """Disable tunnel mode, revert to direct host."""
    devices = _load_synology()
    dev = next((d for d in devices if d["name"] == name), None)
    if not dev:
        return {"status": "error", "detail": "device not found"}

    if dev.get("original_host"):
        dev["host"] = dev["original_host"]
        dev["port"] = dev.get("tunnel", {}).get("local_port", 5000)
    dev.pop("tunnel", None)
    dev.pop("original_host", None)
    _save_synology(devices)

    return {"status": "ok"}


@router.get("/tunnel/key")
async def get_tunnel_key(request: Request, user: str = Depends(require_auth)):
    """Download SSH private key for tunnel setup."""
    key_file = TUNNEL_KEY_DIR / "synology_tunnel"
    if not key_file.exists():
        return {"status": "error", "detail": "tunnel key not generated"}

    key_content = key_file.read_text()
    return PlainTextResponse(content=key_content, media_type="application/octet-stream",
                             headers={"Content-Disposition": "attachment; filename=synology_tunnel"})


@router.get("/tunnel/setup-command")
async def get_tunnel_setup_command(name: str, request: Request, user: str = Depends(require_auth)):
    """Generate PowerShell command to set up Synology tunnel on Windows PC."""
    devices = _load_synology()
    dev = next((d for d in devices if d["name"] == name), None)

    tunnel = dev.get("tunnel", {}) if dev else {}
    local_ip = tunnel.get("local_ip", "192.168.88.6")
    local_port = tunnel.get("local_port", 5000)
    vps_port = tunnel.get("vps_port", TUNNEL_VPS_PORT)

    host = request.headers.get("host", "77.239.126.123").split(":")[0]
    server_url = f"http://{host}"

    ps_cmd = (
        f"Set-ExecutionPolicy Bypass -Scope Process -Force; "
        f"$ProgressPreference = 'SilentlyContinue'; "
        f"(New-Object Net.WebClient).DownloadFile('{server_url}/static/downloads/synology_tunnel.ps1', "
        f"\"$PWD\\synology_tunnel.ps1\"); "
        f"& \"$PWD\\synology_tunnel.ps1\" -ServerUrl '{server_url}' "
        f"-LocalTarget '{local_ip}:{local_port}' -VpsPort {vps_port}"
    )

    return {"status": "ok", "command": ps_cmd, "local_ip": local_ip,
            "local_port": local_port, "vps_port": vps_port}
