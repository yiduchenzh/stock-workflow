# -*- coding: utf-8 -*-
# 修复 Aurora 计划任务: Arguments 里脚本路径加引号 (2026-10-01)
$ErrorActionPreference = 'Stop'
$proj = 'D:\Hermes Agent CN Desktop\stock-workflow'
$py = "$proj\.venv\Scripts\python.exe"
$Q = [char]34   # "

function Fix-Task($name, $phase) {
    $arg = $Q + "$proj\daily_run.py" + $Q + " --phase $phase"
    $act = New-ScheduledTaskAction -Execute ($Q + $py + $Q) -Argument $arg -WorkingDirectory $proj
    Set-ScheduledTask -TaskName $name -Action $act | Out-Null
    $x = [xml](Export-ScheduledTask -TaskName $name)
    Write-Output ("FIXED {0,-22} cmd={1}" -f $name, $x.Task.Actions.Exec.Command)
    Write-Output ("      args={0}" -f $x.Task.Actions.Exec.Arguments)
}

Fix-Task 'Aurora_6Agent_Morning' 'multi_morning'
Fix-Task 'Aurora_6Agent_Monitor' 'multi_monitor'
Fix-Task 'Aurora_6Agent_Noon'    'multi_monitor'
Fix-Task 'AuroraClose'           'close'
# AuroraMorningRun 原来跑 start_multi_test.bat(=clear_all_data 清库!) -> 改为直调 python
Fix-Task 'AuroraMorningRun'      'multi_morning'
Write-Output 'DONE'
