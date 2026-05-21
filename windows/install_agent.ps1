# VPS Monitor - Windows Agent Installer
# Usage (PowerShell Admin): .\install_agent.ps1 -ServerUrl "http://IP" -AgentName "MyPC"

param(
    [Parameter(Mandatory=$true)]
    [string]$ServerUrl,

    [string]$AgentName = $env:COMPUTERNAME,

    [int]$Interval = 60
)

$InstallDir = "C:\VPS-Monitor"
$TaskName = "VPS-Monitor-Agent"

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  VPS Monitor - Agent Installer" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Server:   $ServerUrl" -ForegroundColor White
Write-Host "  Name:     $AgentName" -ForegroundColor White
Write-Host "  Interval: ${Interval}s" -ForegroundColor White
Write-Host "  Install:  $InstallDir" -ForegroundColor White
Write-Host ""

# Create install directory
if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    Write-Host "[+] Created $InstallDir" -ForegroundColor Green
}

# Download agent script
Write-Host "[*] Downloading agent..." -ForegroundColor Yellow
$AgentUrl = "$ServerUrl/static/downloads/vps_monitor_agent.ps1"
$AgentDest = "$InstallDir\vps_monitor_agent.ps1"
try {
    $wc = New-Object System.Net.WebClient
    $wc.Encoding = [System.Text.Encoding]::UTF8
    $wc.DownloadFile($AgentUrl, $AgentDest)
    Write-Host "[+] Agent downloaded" -ForegroundColor Green
} catch {
    Write-Host "[!] Download failed: $($_.Exception.Message)" -ForegroundColor Yellow
    $localAgent = Join-Path $PSScriptRoot "vps_monitor_agent.ps1"
    if (Test-Path $localAgent) {
        Copy-Item $localAgent $AgentDest
        Write-Host "[+] Local copy used" -ForegroundColor Green
    } else {
        Write-Host "[-] No agent script found!" -ForegroundColor Red
        exit 1
    }
}

# Create config
$config = @{
    server_url = $ServerUrl
    agent_name = $AgentName
    interval = $Interval
} | ConvertTo-Json

Set-Content -Path "$InstallDir\agent_config.json" -Value $config -Encoding UTF8
Write-Host "[+] Config saved" -ForegroundColor Green

# Create scheduled task
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "[*] Removed old task" -ForegroundColor Yellow
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$InstallDir\vps_monitor_agent.ps1`"" `
    -WorkingDirectory $InstallDir

$triggerStartup = New-ScheduledTaskTrigger -AtStartup

$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 365)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $triggerStartup `
    -Principal $principal `
    -Settings $settings `
    -Description "VPS Monitor PC Agent" | Out-Null

Write-Host "[+] Scheduled task created" -ForegroundColor Green

# Start now
Start-ScheduledTask -TaskName $TaskName
Write-Host "[+] Agent started!" -ForegroundColor Green

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Installation complete!" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Files:     $InstallDir" -ForegroundColor White
Write-Host "  Task:      $TaskName" -ForegroundColor White
Write-Host "  Status:    Running" -ForegroundColor White
Write-Host ""
Write-Host "  Commands:" -ForegroundColor Gray
Write-Host "    Check:   Get-ScheduledTask $TaskName" -ForegroundColor Gray
Write-Host "    Stop:    Stop-ScheduledTask $TaskName" -ForegroundColor Gray
Write-Host "    Start:   Start-ScheduledTask $TaskName" -ForegroundColor Gray
Write-Host "    Remove:  Unregister-ScheduledTask $TaskName" -ForegroundColor Gray
Write-Host "    Config:  type $InstallDir\agent_config.json" -ForegroundColor Gray
Write-Host ""
