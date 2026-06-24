# Aurora Trading — .venv启动脚本
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    Write-Host "[错误] 未找到 .venv\Scripts\python.exe — 请先创建虚拟环境" -ForegroundColor Red
    exit 1
}

Write-Host "[Aurora Trading] 启动中..." -ForegroundColor Cyan
& $PythonExe (Join-Path $ProjectRoot "daily_run.py") $args