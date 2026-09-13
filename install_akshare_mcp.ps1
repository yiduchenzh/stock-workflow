# quanters-akshare-mcp 安装脚本
# 运行: PowerShell -ExecutionPolicy Bypass .\install_akshare_mcp.ps1

Write-Host "=== 安装 quanters-akshare-mcp MCP 服务器 ===" -ForegroundColor Cyan

# 1. 检查 Node.js
$nodeVer = node --version
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Node.js 未安装，请先安装 Node.js" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Node.js $nodeVer"

# 2. 测试 npx 安装
Write-Host "`n🔄 测试安装 quanters-akshare-mcp..." -ForegroundColor Yellow
$testResult = npx -y quanters-akshare-mcp --help 2>&1
if ($LASTEXITCODE -ne 0 -and $testResult -notmatch "Usage|help|quanters") {
    Write-Host "⚠️ 测试运行异常，请确认网络能访问 npmjs.org" -ForegroundColor Yellow
    Write-Host $testResult
} else {
    Write-Host "✅ npx 安装成功"
}

# 3. 修改 Hermes 配置
$configPath = "$env:APPDATA\cn.org.hermesagent.desktop\runtime\hermes-home\config.yaml"
if (-not (Test-Path $configPath)) {
    Write-Host "❌ 未找到 Hermes 配置文件: $configPath" -ForegroundColor Red
    exit 1
}

$content = Get-Content $configPath -Raw

# 检查是否已存在
if ($content -match "quanters-akshare") {
    Write-Host "✅ quanters-akshare MCP 服务器已配置" -ForegroundColor Green
} else {
    # 在 agent-browser 后追加
    $search = "  agent-browser:`r`n    command: agent-browser`r`n    args:`r`n      - mcp`r`n      - --tools`r`n      - all`r`n    timeout: 120"
    $replace = "  agent-browser:`r`n    command: agent-browser`r`n    args:`r`n      - mcp`r`n      - --tools`r`n      - all`r`n    timeout: 120`r`n  quanters-akshare:`r`n    command: npx`r`n    args:`r`n      - -y`r`n      - quanters-akshare-mcp`r`n    env:`r`n      QUANTERS_USE_AKTOOLS: `"0`"`r`n      AKSHARE_MAX_ROWS: `"500`"`r`n    timeout: 120`r`n    connect_timeout: 60"
    
    if ($content -match $search) {
        $content = $content -replace [regex]::Escape($search), $replace
        Set-Content $configPath -Value $content -Encoding UTF8
        Write-Host "✅ 已添加 quanters-akshare 到 mcp_servers" -ForegroundColor Green
    } else {
        Write-Host "⚠️ 未找到 agent-browser 配置段，手动追加到 mcp_servers:" -ForegroundColor Yellow
        Write-Host @'

mcp_servers:
  agent-browser:
    command: agent-browser
    args:
      - mcp
      - --tools
      - all
    timeout: 120
  quanters-akshare:
    command: npx
    args:
      - -y
      - quanters-akshare-mcp
    env:
      QUANTERS_USE_AKTOOLS: "0"
      AKSHARE_MAX_ROWS: "500"
    timeout: 120
    connect_timeout: 60
'@ -ForegroundColor Cyan
    }
}

# 4. 验证
Write-Host "`n=== 验证配置 ===" -ForegroundColor Cyan
$finalContent = Get-Content $configPath -Raw
if ($finalContent -match "quanters-akshare") {
    Write-Host "✅ 配置添加成功" -ForegroundColor Green
    Write-Host "`n📋 配置内容:" -ForegroundColor Cyan
    $finalContent | Select-String -Pattern "quanters-akshare" -Context 0,6 | ForEach-Object { $_.Line; $_.Context.PostContext }
} else {
    Write-Host "⚠️ 配置未生效，请手动编辑 $configPath" -ForegroundColor Yellow
}

Write-Host "`n=== 完成 ===" -ForegroundColor Green
Write-Host "`n🔄 重启 Hermes Desktop / TUI 后生效" -ForegroundColor Cyan
Write-Host "   MCP 工具将自动以前缀 mcp_quanters_akshare_* 注册" -ForegroundColor Cyan
