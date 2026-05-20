import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import asyncssh

from server.auth import verify_token
from server.config import load_servers

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/ssh/{server_id}")
async def ssh_websocket(websocket: WebSocket, server_id: str):
    """WebSocket SSH terminal."""
    await websocket.accept()

    # Auth check
    token = websocket.cookies.get("access_token")
    if not verify_token(token):
        await websocket.send_text("Authentication required")
        await websocket.close()
        return

    servers = load_servers()
    server = None
    for srv in servers:
        if srv.get("id") == server_id or srv["host"] == server_id:
            server = srv
            break

    if not server:
        await websocket.send_text("Server not found")
        await websocket.close()
        return

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
            process = await conn.create_process(
                term_type="xterm-256color",
                term_size=(120, 40),
            )

            async def read_output():
                try:
                    while True:
                        data = await process.stdout.read(4096)
                        if not data:
                            break
                        await websocket.send_text(data)
                except Exception:
                    pass

            read_task = asyncio.create_task(read_output())

            try:
                while True:
                    data = await websocket.receive_text()
                    process.stdin.write(data)
            except WebSocketDisconnect:
                pass
            finally:
                read_task.cancel()
                process.close()

    except Exception as e:
        await websocket.send_text(f"\r\nConnection error: {e}\r\n")
        await websocket.close()
