#!/usr/bin/env python3
"""Check Keenetic API connectivity for all routers."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.services.keenetic_client import KeeneticClient

DATA = Path("/opt/vps-monitoring/data/keenetic.json")


async def check(dev):
    c = KeeneticClient(
        host=dev.get("host", ""),
        login=dev.get("login", "admin"),
        password=dev.get("password", ""),
        web_url=dev.get("web_url", ""),
    )
    try:
        m = await c.collect_metrics()
        if m.get("online"):
            return "online"
        err = (m.get("error") or "unknown")[:80]
        return f"offline: {err}"
    except Exception as e:
        return f"err: {str(e)[:80]}"
    finally:
        await c.close()


async def main():
    with open(DATA) as f:
        devices = json.load(f)
    for d in devices:
        r = await check(d)
        print(f"{d['name']:22} {r}")
        await asyncio.sleep(0.3)


if __name__ == "__main__":
    asyncio.run(main())
