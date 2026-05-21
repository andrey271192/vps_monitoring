#!/usr/bin/env python3
"""Fast auth-only check for all routers (no RCI batch)."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.services.keenetic_client import KeeneticClient

DATA = Path("/opt/vps-monitoring/data/keenetic.json")


async def one(dev):
    c = KeeneticClient(
        host=dev.get("host", ""),
        login=dev.get("login", "admin"),
        password=dev.get("password", ""),
        web_url=dev.get("web_url", ""),
    )
    try:
        ok = await c.authenticate()
        if ok:
            return "ONLINE"
        return f"OFFLINE: {c.last_error}"
    except Exception as e:
        return f"ERR: {e}"
    finally:
        await c.close()


async def main():
    with open(DATA) as f:
        devices = json.load(f)
    online = 0
    for d in devices:
        r = await one(d)
        if r == "ONLINE":
            online += 1
        name = d["name"]
        url = d.get("web_url", "")
        print(f"{name:28} {r:40} {url}")
        await asyncio.sleep(0.3)
    print(f"\nTotal: {online}/{len(devices)} ONLINE")


if __name__ == "__main__":
    asyncio.run(main())
