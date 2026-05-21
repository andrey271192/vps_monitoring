# VPS Monitor — Synology SSH Tunnel
# Creates a reverse SSH tunnel so VPS can reach local Synology NAS
#
# Usage: .\synology_tunnel.ps1 -ServerUrl "http://IP" -LocalTarget "192.168.88.6:5000" -VpsPort 15000

param(
    [string]$ServerUrl = "",
    [string]$LocalTarget = "192.168.88.6:5000",
    [int]$VpsPort = 15000,
    [switch]$Install
)

$InstallDir = "C:\VPS-Monitor"
$TaskName = "VPS-Monitor-SynologyTunnel"
$KeyFile = "$InstallDir\synology_tunnel_key"
$ConfigFile = "$InstallDir\tunnel_config.json"

# Load config if exists
if (Test-Path $ConfigFile) {
    $config = Get-Content $ConfigFile | ConvertFrom-Json
    if (-not $ServerUrl) { $ServerUrl = $config.server_url }
    if ($config.local_target) { $LocalTarget = $config.local_target }
    if ($config.vps_port) { $VpsPort = $config.vps_port }
}

if (-not $ServerUrl) {
    Write-Host "ERROR: -ServerUrl required" -ForegroundColor Red
    exit 1
}

# Extract VPS IP from ServerUrl
$VpsHost = ($ServerUrl -replace "https?://", "") -replace ":[0-9]+$", ""

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  VPS Monitor — Synology Tunnel" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  VPS:    $VpsHost" -ForegroundColor White
Write-Host "  Target: $LocalTarget" -ForegroundColor White
Write-Host "  Port:   $VpsPort (on VPS)" -ForegroundColor White
Write-Host ""

# Ensure install directory
if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}

# Download SSH key from VPS
if (-not (Test-Path $KeyFile)) {
    Write-Host "[*] Downloading tunnel SSH key..." -ForegroundColor Yellow
    try {
        $wc = New-Object System.Net.WebClient
        $wc.DownloadFile("$ServerUrl/static/downloads/synology_tunnel_key", $KeyFile)
        Write-Host "[+] Key downloaded" -ForegroundColor Green
    } catch {
        Write-Host "[!] Key download failed: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "    Make sure you're logged into the dashboard first" -ForegroundColor Yellow
        exit 1
    }

    # Fix key permissions (Windows — icacls)
    icacls $KeyFile /inheritance:r /grant:r "${env:USERNAME}:(R)" 2>$null | Out-Null
}

# Save config
$tunnelConfig = @{
    server_url = $ServerUrl
    local_target = $LocalTarget
    vps_port = $VpsPort
    vps_host = $VpsHost
} | ConvertTo-Json
Set-Content -Path $ConfigFile -Value $tunnelConfig

# Install mode — create scheduled task
if ($Install) {
    Write-Host "[*] Creating scheduled task..." -ForegroundColor Yellow

    $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existingTask) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }

    $action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$InstallDir\synology_tunnel.ps1`"" `
        -WorkingDirectory $InstallDir

    $trigger = New-ScheduledTaskTrigger -AtStartup
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -RestartCount 999 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit (New-TimeSpan -Days 365)

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Description "VPS Monitor — SSH tunnel to Synology NAS via $VpsHost" | Out-Null

    Write-Host "[+] Scheduled task created: $TaskName" -ForegroundColor Green
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "[+] Tunnel started!" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Commands:" -ForegroundColor Gray
    Write-Host "    Check:  Get-ScheduledTask '$TaskName'" -ForegroundColor Gray
    Write-Host "    Stop:   Stop-ScheduledTask '$TaskName'" -ForegroundColor Gray
    Write-Host "    Remove: Unregister-ScheduledTask '$TaskName'" -ForegroundColor Gray
    exit 0
}

# Main loop — maintain SSH tunnel
Write-Host "[*] Starting tunnel loop..." -ForegroundColor Green
Write-Host "    VPS:$VpsPort -> Local:$LocalTarget" -ForegroundColor Gray
Write-Host ""

$LocalIP = $LocalTarget.Split(":")[0]
$LocalPort = $LocalTarget.Split(":")[1]

while ($true) {
    $ts = Get-Date -Format "HH:mm:ss"

    # Check if ssh.exe available (Windows 10+)
    $sshExe = Get-Command ssh.exe -ErrorAction SilentlyContinue

    if ($sshExe) {
        Write-Host "[$ts] Connecting via ssh.exe..." -ForegroundColor Cyan
        # ssh -N = no command, -R = reverse tunnel, -o = options for stability
        & ssh.exe -N `
            -o "StrictHostKeyChecking=no" `
            -o "ServerAliveInterval=30" `
            -o "ServerAliveCountMax=3" `
            -o "ExitOnForwardFailure=yes" `
            -o "BatchMode=yes" `
            -i $KeyFile `
            -R "127.0.0.1:${VpsPort}:${LocalIP}:${LocalPort}" `
            "root@${VpsHost}" 2>&1

        $exitCode = $LASTEXITCODE
        Write-Host "[$ts] SSH disconnected (exit: $exitCode)" -ForegroundColor Yellow
    } else {
        # Fallback to plink
        $plinkPath = "$InstallDir\plink.exe"
        if (-not (Test-Path $plinkPath)) {
            Write-Host "[$ts] No ssh.exe or plink.exe found. Install OpenSSH or download plink." -ForegroundColor Red
            Start-Sleep -Seconds 60
            continue
        }

        Write-Host "[$ts] Connecting via plink..." -ForegroundColor Cyan
        echo y | & $plinkPath -N -batch `
            -i $KeyFile `
            -R "127.0.0.1:${VpsPort}:${LocalIP}:${LocalPort}" `
            "root@${VpsHost}" 2>&1

        Write-Host "[$ts] Plink disconnected" -ForegroundColor Yellow
    }

    # Wait before reconnect
    Write-Host "[$ts] Reconnecting in 10s..." -ForegroundColor Gray
    Start-Sleep -Seconds 10
}
