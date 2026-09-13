# 迁移 SOUL.md + 合并 memories（用脚本文件避免 $HOME 保留变量问题）
$ErrorActionPreference = "Stop"
$hh = "C:\Users\User871619\AppData\Roaming\cn.org.hermesagent.desktop\runtime\hermes-home"
$arch = Join-Path $hh ".archive"
New-Item -ItemType Directory -Force -Path $arch | Out-Null

# 1. SOUL.md：备份默认版 -> 替换为金融事业部总经理版
Copy-Item (Join-Path $hh "SOUL.md") (Join-Path $arch "SOUL.md.default.bak-20260809") -Force
Copy-Item "C:\Users\User871619\Desktop\hermes-trading-pack\SOUL.md" (Join-Path $hh "SOUL.md") -Force
Write-Host ("SOUL.md replaced: {0} bytes" -f (Get-Item (Join-Path $hh 'SOUL.md')).Length)

# 2. MEMORY.md 合并（本机现有 + pack 追加，§ 分隔）
$cur = Get-Content (Join-Path $hh "memories\MEMORY.md") -Raw -Encoding UTF8
$pkg = Get-Content "C:\Users\User871619\Desktop\hermes-trading-pack\memories\MEMORY.md" -Raw -Encoding UTF8
Copy-Item (Join-Path $hh "memories\MEMORY.md") (Join-Path $arch "MEMORY.md.bak-20260809") -Force
$sep = if ($cur.TrimEnd().EndsWith("§")) { "" } else { "§`r`n" }
$merged = $cur.TrimEnd() + "`r`n" + $sep + $pkg.TrimStart()
[System.IO.File]::WriteAllText((Join-Path $hh "memories\MEMORY.md"), $merged, (New-Object System.Text.UTF8Encoding($false)))
Write-Host ("MEMORY.md merged: {0} bytes" -f (Get-Item (Join-Path $hh 'memories\MEMORY.md')).Length)

# 3. USER.md 合并
$curu = Get-Content (Join-Path $hh "memories\USER.md") -Raw -Encoding UTF8
$pku = Get-Content "C:\Users\User871619\Desktop\hermes-trading-pack\memories\USER.md" -Raw -Encoding UTF8
Copy-Item (Join-Path $hh "memories\USER.md") (Join-Path $arch "USER.md.bak-20260809") -Force
$sepu = if ($curu.TrimEnd().EndsWith("§")) { "" } else { "§`r`n" }
$mergedu = $curu.TrimEnd() + "`r`n" + $sepu + $pku.TrimStart()
[System.IO.File]::WriteAllText((Join-Path $hh "memories\USER.md"), $mergedu, (New-Object System.Text.UTF8Encoding($false)))
Write-Host ("USER.md merged: {0} bytes" -f (Get-Item (Join-Path $hh 'memories\USER.md')).Length)

Write-Host "DONE"
