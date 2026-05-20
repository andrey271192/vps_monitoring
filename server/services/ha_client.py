"""Home Assistant REST API client for monitoring."""

import logging
from typing import Optional, List, Dict, Any

import aiohttp

logger = logging.getLogger(__name__)


class HomeAssistantClient:
    """Client for Home Assistant REST API."""

    def __init__(self, url: str, token: str):
        """
        Args:
            url: HA base URL, e.g. http://192.168.1.100:8123
            token: Long-Lived Access Token (from Profile → Security → Long-Lived Access Tokens)
        """
        self.base_url = url.rstrip("/")
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def _get(self, path: str) -> Optional[Any]:
        """GET request to HA API."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api{path}",
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                    ssl=False,
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    logger.error(f"HA API {path} returned {resp.status}")
                    return None
        except Exception as e:
            logger.error(f"HA API error ({path}): {e}")
            return None

    async def check_connection(self) -> bool:
        """Check if HA is reachable."""
        data = await self._get("/")
        return data is not None and data.get("message") == "API running."

    async def get_config(self) -> Optional[dict]:
        """Get HA configuration (name, version, components, location)."""
        return await self._get("/config")

    async def get_states(self) -> Optional[List[dict]]:
        """Get all entity states."""
        return await self._get("/states")

    async def get_services(self) -> Optional[List[dict]]:
        """Get available services."""
        return await self._get("/services")

    async def collect_all_metrics(self) -> dict:
        """Collect key metrics from Home Assistant."""
        result = {
            "online": False,
            "version": "",
            "location_name": "",
            "components_count": 0,
            "entities_count": 0,
            "automations": [],
            "sensors": {
                "temperature": [],
                "humidity": [],
                "pressure": [],
                "motion": [],
                "door": [],
                "light": [],
                "battery": [],
            },
            "climate": [],
            "media_players": [],
            "persons": [],
            "updates_available": [],
            "problem_entities": [],
            "uptime": "",
        }

        # Check connection
        if not await self.check_connection():
            return result

        result["online"] = True

        # Config
        config = await self.get_config()
        if config:
            result["version"] = config.get("version", "")
            result["location_name"] = config.get("location_name", "")
            result["components_count"] = len(config.get("components", []))

        # States
        states = await self.get_states()
        if not states:
            return result

        result["entities_count"] = len(states)

        for entity in states:
            eid = entity.get("entity_id", "")
            state = entity.get("state", "")
            attrs = entity.get("attributes", {})
            friendly = attrs.get("friendly_name", eid)

            # Automations
            if eid.startswith("automation."):
                result["automations"].append({
                    "name": friendly,
                    "state": state,  # on/off
                    "last_triggered": attrs.get("last_triggered", ""),
                })

            # Temperature sensors
            elif eid.startswith("sensor.") and attrs.get("device_class") == "temperature":
                try:
                    val = float(state) if state not in ("unknown", "unavailable") else None
                    result["sensors"]["temperature"].append({
                        "name": friendly,
                        "value": val,
                        "unit": attrs.get("unit_of_measurement", "°C"),
                    })
                except (ValueError, TypeError):
                    pass

            # Humidity sensors
            elif eid.startswith("sensor.") and attrs.get("device_class") == "humidity":
                try:
                    val = float(state) if state not in ("unknown", "unavailable") else None
                    result["sensors"]["humidity"].append({
                        "name": friendly,
                        "value": val,
                        "unit": attrs.get("unit_of_measurement", "%"),
                    })
                except (ValueError, TypeError):
                    pass

            # Battery sensors
            elif eid.startswith("sensor.") and attrs.get("device_class") == "battery":
                try:
                    val = float(state) if state not in ("unknown", "unavailable") else None
                    result["sensors"]["battery"].append({
                        "name": friendly,
                        "value": val,
                        "unit": "%",
                    })
                except (ValueError, TypeError):
                    pass

            # Motion / occupancy
            elif eid.startswith("binary_sensor.") and attrs.get("device_class") in ("motion", "occupancy"):
                result["sensors"]["motion"].append({
                    "name": friendly,
                    "state": state,  # on/off
                })

            # Door / window
            elif eid.startswith("binary_sensor.") and attrs.get("device_class") in ("door", "window", "opening"):
                result["sensors"]["door"].append({
                    "name": friendly,
                    "state": state,  # on = open, off = closed
                })

            # Lights
            elif eid.startswith("light."):
                result["sensors"]["light"].append({
                    "name": friendly,
                    "state": state,
                    "brightness": attrs.get("brightness"),
                })

            # Climate
            elif eid.startswith("climate."):
                result["climate"].append({
                    "name": friendly,
                    "state": state,
                    "current_temp": attrs.get("current_temperature"),
                    "target_temp": attrs.get("temperature"),
                    "hvac_action": attrs.get("hvac_action", ""),
                })

            # Media players
            elif eid.startswith("media_player."):
                result["media_players"].append({
                    "name": friendly,
                    "state": state,
                    "source": attrs.get("source", ""),
                })

            # Person
            elif eid.startswith("person."):
                result["persons"].append({
                    "name": friendly,
                    "state": state,  # home/not_home/zone
                })

            # Updates available
            elif eid.startswith("update.") and state == "on":
                result["updates_available"].append({
                    "name": friendly,
                    "installed": attrs.get("installed_version", ""),
                    "latest": attrs.get("latest_version", ""),
                })

            # Problem entities (unavailable/unknown)
            if state in ("unavailable", "unknown") and not eid.startswith(("update.", "scene.")):
                result["problem_entities"].append({
                    "entity_id": eid,
                    "name": friendly,
                    "state": state,
                })

            # HA uptime sensor
            if eid == "sensor.uptime" or eid.endswith("_uptime"):
                if attrs.get("device_class") == "timestamp" and state not in ("unknown", "unavailable"):
                    result["uptime"] = state

        return result
