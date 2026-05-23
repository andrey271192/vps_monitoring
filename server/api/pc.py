from datetime import datetime
from typing import Dict

from fastapi import APIRouter, Request, Depends

from server.auth import require_auth
from server.config import DATA_DIR, load_json, save_json

router = APIRouter(prefix="/api/pc", tags=["pc"])

# In-memory PC metrics cache
pc_metrics: Dict[str, dict] = {}

PC_FILE = DATA_DIR / "pc_agents.json"


def _load_pc_data():
    return load_json(PC_FILE, {})


def _save_pc_data(data):
    save_json(PC_FILE, data)


@router.post("/heartbeat")
async def pc_heartbeat(request: Request):
    """Receive metrics from Windows PC agent. No auth required (agent sends by name)."""
    body = await request.json()
    agent_name = body.get("agent_name", "")
    if not agent_name:
        return {"status": "error", "detail": "agent_name required"}

    metrics = body.get("metrics", {})
    timestamp = body.get("timestamp", datetime.now().isoformat())

    entry = {
        "agent_name": agent_name,
        "metrics": metrics,
        "timestamp": timestamp,
        "ip": request.client.host if request.client else "",
        "online": True,
        "last_seen": datetime.now().isoformat(),
    }

    pc_metrics[agent_name] = entry

    # Persist
    stored = _load_pc_data()
    stored[agent_name] = entry
    _save_pc_data(stored)

    return {"status": "ok"}


@router.get("/list")
async def pc_list(request: Request, user: str = Depends(require_auth)):
    """List all PC agents with metrics."""
    stored = _load_pc_data()

    # Merge with in-memory (fresher)
    for name, data in pc_metrics.items():
        stored[name] = data

    # Mark stale agents (no heartbeat > 3 min)
    now = datetime.now()
    result = []
    for name, data in stored.items():
        last_seen = data.get("last_seen", "")
        try:
            last_dt = datetime.fromisoformat(last_seen)
            stale = (now - last_dt).total_seconds() > 180
        except Exception:
            stale = True

        data["online"] = not stale
        result.append(data)

    return result


@router.delete("/{agent_name}")
async def pc_delete(agent_name: str, request: Request, user: str = Depends(require_auth)):
    """Remove a PC agent."""
    pc_metrics.pop(agent_name, None)

    stored = _load_pc_data()
    stored.pop(agent_name, None)
    _save_pc_data(stored)

    return {"status": "ok"}
