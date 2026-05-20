import uuid
from fastapi import APIRouter, HTTPException, Depends, Request

from server.auth import require_auth
from server.config import load_servers, save_servers
from server.models import ServerCreate, ServerUpdate
from server.services.monitor import get_metrics, get_all_metrics

router = APIRouter(prefix="/api/servers", tags=["servers"])


@router.get("")
async def list_servers(request: Request, user: str = Depends(require_auth)):
    servers = load_servers()
    metrics = get_all_metrics()
    result = []
    for srv in servers:
        srv_data = {**srv}
        srv_data["metrics"] = metrics.get(srv["host"], {})
        if "password" in srv_data:
            srv_data["password"] = "***"
        result.append(srv_data)
    return result


@router.post("")
async def add_server(server: ServerCreate, user: str = Depends(require_auth)):
    servers = load_servers()

    # Check duplicate
    for s in servers:
        if s["host"] == server.host:
            raise HTTPException(400, f"Server {server.host} already exists")

    new_server = {
        "id": str(uuid.uuid4())[:8],
        "name": server.name,
        "host": server.host,
        "port": server.port,
        "username": server.username,
        "password": server.password,
        "ssh_key": server.ssh_key,
        "description": server.description,
    }
    servers.append(new_server)
    save_servers(servers)
    return {"status": "ok", "server": {**new_server, "password": "***"}}


@router.put("/{server_id}")
async def update_server(server_id: str, update: ServerUpdate, user: str = Depends(require_auth)):
    servers = load_servers()
    for i, srv in enumerate(servers):
        if srv.get("id") == server_id or srv["host"] == server_id:
            for key, val in update.model_dump(exclude_unset=True).items():
                servers[i][key] = val
            save_servers(servers)
            return {"status": "ok"}
    raise HTTPException(404, "Server not found")


@router.delete("/{server_id}")
async def delete_server(server_id: str, user: str = Depends(require_auth)):
    servers = load_servers()
    servers = [s for s in servers if s.get("id") != server_id and s["host"] != server_id]
    save_servers(servers)
    return {"status": "ok"}


@router.get("/{server_id}/metrics")
async def server_metrics(server_id: str, user: str = Depends(require_auth)):
    servers = load_servers()
    for srv in servers:
        if srv.get("id") == server_id or srv["host"] == server_id:
            return get_metrics(srv["host"])
    raise HTTPException(404, "Server not found")


@router.post("/{server_id}/reboot")
async def reboot_server(server_id: str, user: str = Depends(require_auth)):
    from server.services.ssh_manager import execute_command

    servers = load_servers()
    for srv in servers:
        if srv.get("id") == server_id or srv["host"] == server_id:
            result = await execute_command(srv, "reboot")
            return {"status": "ok", "result": result}
    raise HTTPException(404, "Server not found")


@router.post("/{server_id}/exec")
async def exec_command(server_id: str, request: Request, user: str = Depends(require_auth)):
    from server.services.ssh_manager import execute_command

    body = await request.json()
    command = body.get("command", "")
    if not command:
        raise HTTPException(400, "Command required")

    servers = load_servers()
    for srv in servers:
        if srv.get("id") == server_id or srv["host"] == server_id:
            result = await execute_command(srv, command)
            return result
    raise HTTPException(404, "Server not found")
