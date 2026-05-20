import asyncio
import logging
from typing import Dict, Optional

import asyncssh

logger = logging.getLogger(__name__)

active_sessions: Dict[str, asyncssh.SSHClientConnection] = {}


async def create_ssh_session(server: dict) -> Optional[asyncssh.SSHClientConnection]:
    """Create SSH connection to server."""
    try:
        conn_kwargs = {
            "host": server["host"],
            "port": server.get("port", 22),
            "username": server.get("username", "root"),
            "known_hosts": None,
            "connect_timeout": 15,
        }

        if server.get("password"):
            conn_kwargs["password"] = server["password"]
        elif server.get("ssh_key"):
            conn_kwargs["client_keys"] = [server["ssh_key"]]

        conn = await asyncssh.connect(**conn_kwargs)
        active_sessions[server["host"]] = conn
        return conn

    except Exception as e:
        logger.error(f"SSH connection failed to {server['host']}: {e}")
        return None


async def execute_command(server: dict, command: str) -> dict:
    """Execute command on remote server."""
    try:
        conn_kwargs = {
            "host": server["host"],
            "port": server.get("port", 22),
            "username": server.get("username", "root"),
            "known_hosts": None,
            "connect_timeout": 15,
        }

        if server.get("password"):
            conn_kwargs["password"] = server["password"]
        elif server.get("ssh_key"):
            conn_kwargs["client_keys"] = [server["ssh_key"]]

        async with asyncssh.connect(**conn_kwargs) as conn:
            result = await conn.run(command, check=False, timeout=30)
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_status,
            }

    except Exception as e:
        return {"stdout": "", "stderr": str(e), "exit_code": -1}


async def close_session(host: str):
    """Close SSH session."""
    conn = active_sessions.pop(host, None)
    if conn:
        conn.close()
