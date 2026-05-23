"""Home Assistant monitoring API endpoints."""

from datetime import datetime
from typing import Dict

from fastapi import APIRouter, Request, Depends

from server.auth import require_auth
from server.config import DATA_DIR, load_json, save_json

router = APIRouter(prefix="/api/ha", tags=["homeassistant"])

# In-memory cache
ha_metrics: Dict[str, dict] = {}

HA_FILE = DATA_DIR / "homeassistant.json"


def _load_ha():
    return load_json(HA_FILE, [])


def _save_ha(data):
    save_json(HA_FILE, data)


@router.get("/list")
async def ha_list(request: Request, user: str = Depends(require_auth)):
    """List all Home Assistant instances with metrics."""
    instances = _load_ha()
    for inst in instances:
        name = inst["name"]
        if name in ha_metrics:
            inst["metrics"] = ha_metrics[name]
    return instances


@router.post("/add")
async def ha_add(request: Request, user: str = Depends(require_auth)):
    """Add a Home Assistant instance."""
    body = await request.json()
    name = body.get("name", "").strip()
    url = body.get("url", "").strip()
    token = body.get("token", "").strip()

    if not name or not url or not token:
        return {"status": "error", "detail": "name, url, and token required"}

    instances = _load_ha()
    instance = {
        "name": name,
        "url": url,
        "token": token,
        "added": datetime.now().isoformat(),
    }
    instances.append(instance)
    _save_ha(instances)

    return {"status": "ok"}


@router.delete("/{name}")
async def ha_delete(name: str, request: Request, user: str = Depends(require_auth)):
    """Remove a Home Assistant instance."""
    instances = _load_ha()
    instances = [i for i in instances if i["name"] != name]
    _save_ha(instances)
    ha_metrics.pop(name, None)
    return {"status": "ok"}


@router.post("/refresh/{name}")
async def ha_refresh(name: str, request: Request, user: str = Depends(require_auth)):
    """Force refresh metrics for a Home Assistant instance."""
    from server.services.ha_client import HomeAssistantClient

    instances = _load_ha()
    inst = next((i for i in instances if i["name"] == name), None)
    if not inst:
        return {"status": "error", "detail": "instance not found"}

    client = HomeAssistantClient(url=inst["url"], token=inst["token"])
    try:
        metrics = await client.collect_all_metrics()
        metrics["last_updated"] = datetime.now().isoformat()
        ha_metrics[name] = metrics
        return {"status": "ok", "metrics": metrics}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.post("/refresh-all")
async def ha_refresh_all(request: Request, user: str = Depends(require_auth)):
    """Refresh metrics for all Home Assistant instances."""
    from server.services.ha_client import HomeAssistantClient

    instances = _load_ha()
    results = []

    for inst in instances:
        client = HomeAssistantClient(url=inst["url"], token=inst["token"])
        try:
            metrics = await client.collect_all_metrics()
            metrics["last_updated"] = datetime.now().isoformat()
            ha_metrics[inst["name"]] = metrics
            results.append({"name": inst["name"], "online": metrics["online"]})
        except Exception as e:
            results.append({"name": inst["name"], "online": False, "error": str(e)})

    return {"status": "ok", "results": results}
