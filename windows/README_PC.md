# VPS Monitor — Windows PC Agent

## Quick Install (one command)

Run in PowerShell as Administrator:

```powershell
irm https://77.239.126.123.nip.io/static/downloads/install_agent.ps1 | iex -ServerUrl "http://77.239.126.123:7272" -AgentName "MyPC"
```

Or download and run:
```powershell
Invoke-WebRequest -Uri "http://77.239.126.123:7272/static/downloads/install_agent.ps1" -OutFile install_agent.ps1
powershell -ExecutionPolicy Bypass -File install_agent.ps1 -ServerUrl "http://77.239.126.123:7272" -AgentName "Office-PC"
```

## What it monitors

- CPU usage (%)
- RAM usage (total, used, %)
- Disk usage (all drives)
- Network adapters (speed, traffic)
- GPU info
- Uptime
- Top 5 processes by CPU

## Files

| File | Purpose |
|------|---------|
| `install_agent.ps1` | Installer (creates task, config) |
| `vps_monitor_agent.ps1` | Agent (collects & sends metrics) |
| `C:\VPS-Monitor\agent_config.json` | Config (server URL, name) |

## Management

```powershell
# Check status
Get-ScheduledTask 'VPS-Monitor-Agent'

# Stop
Stop-ScheduledTask 'VPS-Monitor-Agent'

# Start
Start-ScheduledTask 'VPS-Monitor-Agent'

# Uninstall
Unregister-ScheduledTask 'VPS-Monitor-Agent' -Confirm:$false
Remove-Item -Recurse C:\VPS-Monitor
```
