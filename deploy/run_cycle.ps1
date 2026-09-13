# Aurora Trading 全天自动循环脚本
# 在Windows终端后台运行, 实现7*24无人值守
param(
    [switch]$Foreground,
    [int]$MonitorInterval = 600  # 监控间隔(秒), 默认10分钟
)

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path | Split-Path -Parent
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$DailyRun = Join-Path $ProjectRoot "daily_run.py"
$DotEnv = Join-Path $ProjectRoot ".env"

# 从.env加载WZ_TOKEN
if (Test-Path $DotEnv) {
    Get-Content $DotEnv | ForEach-Object {
        if ($_ -match "^(WZ_TOKEN)=(.+)$") {
            $env:WZ_TOKEN = $matches[2]
            Write-Host "[Aurora] 已加载WZ_TOKEN" -ForegroundColor Green
        }
    }
}

if (-not (Test-Path $PythonExe)) {
    Write-Host "[错误] 未找到 .venv\Scripts\python.exe" -ForegroundColor Red
    exit 1
}

function Run-Phase($phase) {
    $timestamp = Get-Date -Format "HH:mm:ss"
    Write-Host "[$timestamp] 运行阶段: $phase" -ForegroundColor Cyan
    & $PythonExe $DailyRun "--phase" $phase 2>&1 | ForEach-Object { Write-Host $_ }
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        Write-Host "[$timestamp] ⚠️ $phase 返回代码 $exitCode" -ForegroundColor Yellow
    }
    return $exitCode
}

function Is-TradingHours {
    $now = Get-Date
    # 周末跳过
    if ($now.DayOfWeek -eq [DayOfWeek]::Saturday -or $now.DayOfWeek -eq [DayOfWeek]::Sunday) {
        return $false
    }
    $time = $now.TimeOfDay
    $morningStart = [TimeSpan]::FromHours(9.25)  # 09:15
    $morningEnd = [TimeSpan]::FromHours(11.5)     # 11:30
    $afternoonStart = [TimeSpan]::FromHours(13.0) # 13:00
    $afternoonEnd = [TimeSpan]::FromHours(15.1)   # 15:06
    return ($time -ge $morningStart -and $time -le $morningEnd) -or
           ($time -ge $afternoonStart -and $time -le $afternoonEnd)
}

function Is-ReviewTime {
    $now = Get-Date
    if ($now.DayOfWeek -eq [DayOfWeek]::Saturday -or $now.DayOfWeek -eq [DayOfWeek]::Sunday) {
        return $false
    }
    $time = $now.TimeOfDay
    return $time -ge [TimeSpan]::FromHours(15.05) -and $time -le [TimeSpan]::FromHours(15.15)
}

function Is-MorningTime {
    $now = Get-Date
    if ($now.DayOfWeek -eq [DayOfWeek]::Saturday -or $now.DayOfWeek -eq [DayOfWeek]::Sunday) {
        return $false
    }
    $time = $now.TimeOfDay
    return $time -ge [TimeSpan]::FromHours(9.25) -and $time -le [TimeSpan]::FromHours(9.35)
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Aurora Trading — 全天自动循环" -ForegroundColor Cyan
Write-Host " 项目: $ProjectRoot" -ForegroundColor Cyan
Write-Host " 监控间隔: $MonitorInterval 秒" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if ($Foreground) {
    # 前台模式: 持续循环
    $lastMorningRun = $null
    $lastReviewRun = $null

    while ($true) {
        $now = Get-Date
        $today = $now.ToString("yyyy-MM-dd")

        # 早晨: 先跑一次morning(含竞价选股), 然后进入监控循环
        if (Is-MorningTime -and $lastMorningRun -ne $today) {
            Run-Phase "morning"
            $lastMorningRun = $today
        }

        # 交易时间: 盘中监控
        if (Is-TradingHours) {
            Run-Phase "monitor"
        }

        # 收盘: 复盘
        if (Is-ReviewTime -and $lastReviewRun -ne $today) {
            Run-Phase "review"
            $lastReviewRun = $today
        }

        # 非交易时间: 降低检查频率
        if (-not (Is-TradingHours)) {
            $MonitorInterval = 300  # 5分钟
        } else {
            $MonitorInterval = 600  # 10分钟
        }

        $nextTime = (Get-Date).AddSeconds($MonitorInterval)
        $nextStr = $nextTime.ToString("HH:mm:ss")
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] 下次检查: $nextStr" -ForegroundColor DarkGray
        Start-Sleep -Seconds $MonitorInterval
    }
} else {
    # 后台模式: 使用 register-scheduledjob (需管理员权限)
    Write-Host "后台模式: 请使用 deploy\setup_tasks.bat 注册定时任务" -ForegroundColor Yellow
    Write-Host "或在PowerShell管理员中运行:" -ForegroundColor Yellow
    Write-Host "  .venv\Scripts\python daily_run.py --phase morning  (09:25)" -ForegroundColor Yellow
    Write-Host "  .venv\Scripts\python daily_run.py --phase monitor  (盘中每10分钟)" -ForegroundColor Yellow
    Write-Host "  .venv\Scripts\python daily_run.py --phase review   (15:05)" -ForegroundColor Yellow
}