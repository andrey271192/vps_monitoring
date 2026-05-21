# VPS Monitor - Windows PC Agent
# Sends system metrics to VPS Monitoring server
#
# Install: Run install_agent.ps1
# Manual:  powershell -ExecutionPolicy Bypass -File vps_monitor_agent.ps1

param(
    [string]$ServerUrl = "",
    [string]$AgentName = "",
    [int]$Interval = 60
)

# Load config
$ConfigPath = Join-Path $PSScriptRoot "agent_config.json"
if (Test-Path $ConfigPath) {
    $config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
    if (-not $ServerUrl) { $ServerUrl = $config.server_url }
    if (-not $AgentName) { $AgentName = $config.agent_name }
    if ($config.interval) { $Interval = $config.interval }
}

if (-not $ServerUrl -or -not $AgentName) {
    Write-Host "ERROR: server_url and agent_name required" -ForegroundColor Red
    Write-Host "Edit agent_config.json or pass -ServerUrl and -AgentName"
    exit 1
}

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  VPS Monitor - PC Agent" -ForegroundColor Cyan
Write-Host "  Server: $ServerUrl" -ForegroundColor Gray
Write-Host "  Name:   $AgentName" -ForegroundColor Gray
Write-Host "  Interval: ${Interval}s" -ForegroundColor Gray
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

function Get-SystemMetrics {
    $metrics = @{}

    # Hostname
    $metrics["hostname"] = $env:COMPUTERNAME

    # OS
    $os = Get-CimInstance Win32_OperatingSystem
    $metrics["os"] = "$($os.Caption) $($os.Version)"

    # CPU
    try {
        $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
        $metrics["cpu_name"] = $cpu.Name
        $counter = Get-Counter '\Processor(_Total)\% Processor Time' -ErrorAction SilentlyContinue
        if ($counter) {
            $metrics["cpu_percent"] = [math]::Round($counter.CounterSamples[0].CookedValue, 1)
        } else {
            $metrics["cpu_percent"] = 0
        }
    } catch {
        $metrics["cpu_percent"] = 0
        $metrics["cpu_name"] = "Unknown"
    }

    # RAM
    $totalRam = [math]::Round($os.TotalVisibleMemorySize / 1024, 0)
    $freeRam = [math]::Round($os.FreePhysicalMemory / 1024, 0)
    $usedRam = $totalRam - $freeRam
    $metrics["ram_total_mb"] = $totalRam
    $metrics["ram_used_mb"] = $usedRam
    $metrics["ram_percent"] = [math]::Round(($usedRam / $totalRam) * 100, 1)

    # Disk (all drives)
    $disks = @()
    Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | ForEach-Object {
        $totalGb = [math]::Round($_.Size / 1GB, 1)
        $freeGb = [math]::Round($_.FreeSpace / 1GB, 1)
        $usedGb = $totalGb - $freeGb
        $pct = if ($totalGb -gt 0) { [math]::Round(($usedGb / $totalGb) * 100, 1) } else { 0 }
        $disks += @{
            drive = $_.DeviceID
            total_gb = $totalGb
            used_gb = $usedGb
            free_gb = $freeGb
            percent = $pct
        }
    }
    $metrics["disks"] = $disks

    # Primary disk summary
    $primary = $disks | Where-Object { $_.drive -eq "C:" } | Select-Object -First 1
    if ($primary) {
        $metrics["disk_total_gb"] = $primary.total_gb
        $metrics["disk_used_gb"] = $primary.used_gb
        $metrics["disk_percent"] = $primary.percent
    }

    # Network
    try {
        $adapters = Get-NetAdapter -Physical -ErrorAction SilentlyContinue | Where-Object { $_.Status -eq "Up" }
        $netInfo = @()
        foreach ($a in $adapters) {
            $stats = Get-NetAdapterStatistics -Name $a.Name -ErrorAction SilentlyContinue
            $speed = 0
            try { $speed = [math]::Round($a.LinkSpeed.Replace(" Gbps","000").Replace(" Mbps","") -as [double], 0) } catch {}
            $netInfo += @{
                name = $a.Name
                speed_mbps = $speed
                sent_mb = if ($stats) { [math]::Round($stats.SentBytes / 1MB, 0) } else { 0 }
                received_mb = if ($stats) { [math]::Round($stats.ReceivedBytes / 1MB, 0) } else { 0 }
            }
        }
        $metrics["network"] = $netInfo
    } catch {
        $metrics["network"] = @()
    }

    # Uptime
    $uptime = (Get-Date) - $os.LastBootUpTime
    $metrics["uptime"] = "up $($uptime.Days)d $($uptime.Hours)h $($uptime.Minutes)m"
    $metrics["uptime_seconds"] = [math]::Round($uptime.TotalSeconds, 0)

    # GPU (if available)
    try {
        $gpu = Get-CimInstance Win32_VideoController | Select-Object -First 1
        if ($gpu) {
            $metrics["gpu_name"] = $gpu.Name
            $metrics["gpu_ram_mb"] = [math]::Round($gpu.AdapterRAM / 1MB, 0)
        }
    } catch {}

    # Top processes by CPU
    try {
        $topProcs = Get-Process | Sort-Object CPU -Descending | Select-Object -First 5 |
            ForEach-Object { @{ name = $_.ProcessName; cpu = [math]::Round($_.CPU, 1); ram_mb = [math]::Round($_.WorkingSet64 / 1MB, 0) } }
        $metrics["top_processes"] = $topProcs
    } catch {
        $metrics["top_processes"] = @()
    }

    return $metrics
}

function Send-Metrics($metrics) {
    $body = @{
        agent_name = $AgentName
        timestamp = (Get-Date).ToString("o")
        metrics = $metrics
    } | ConvertTo-Json -Depth 5

    try {
        $wc = New-Object System.Net.WebClient
        $wc.Headers.Add("Content-Type", "application/json")
        $wc.Encoding = [System.Text.Encoding]::UTF8
        $null = $wc.UploadString("$ServerUrl/api/pc/heartbeat", "POST", $body)
        return $true
    } catch {
        Write-Host "  [!] Send failed: $($_.Exception.Message)" -ForegroundColor Yellow
        return $false
    }
}

# Main loop
Write-Host "Agent started. Press Ctrl+C to stop." -ForegroundColor Green
Write-Host ""

while ($true) {
    $ts = Get-Date -Format "HH:mm:ss"

    try {
        $metrics = Get-SystemMetrics
        $ok = Send-Metrics $metrics

        if ($ok) {
            Write-Host "[$ts] OK - CPU: $($metrics.cpu_percent)% RAM: $($metrics.ram_percent)% Disk: $($metrics.disk_percent)%" -ForegroundColor Green
        }
    } catch {
        Write-Host "[$ts] ERROR: $($_.Exception.Message)" -ForegroundColor Red
    }

    Start-Sleep -Seconds $Interval
}
