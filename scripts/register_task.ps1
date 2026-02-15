<#
.SYNOPSIS
    PC Limiterをタスクスケジューラに登録するスクリプト

.DESCRIPTION
    Windowsログオン時にPC Limiterを自動起動するタスクを登録します。
    管理者権限は不要です。

.USAGE
    PowerShellで実行:
    powershell -ExecutionPolicy Bypass -File register_task.ps1
#>

$TaskName = "PC Limiter - 使いすぎ防止"
$Description = "WSL2上のPC Limiterを自動起動し、PCの使いすぎを防止します。"

# VBSファイルのWindowsパス
$VbsPath = "\\wsl.localhost\Ubuntu-20.04\home\hiroki\Portfolio\pc_limiter\scripts\start_limiter_hidden.vbs"

# 既存タスクがあれば削除
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "[INFO] 既存のタスク '$TaskName' を削除します..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# トリガー: ログオン時
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# アクション: VBScriptを実行（ウィンドウ非表示）
$Action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$VbsPath`""

# 設定
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0)  # 無制限

# 登録
Register-ScheduledTask `
    -TaskName $TaskName `
    -Description $Description `
    -Trigger $Trigger `
    -Action $Action `
    -Settings $Settings `
    -RunLevel Limited

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  タスクの登録が完了しました！" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  タスク名: $TaskName"
Write-Host "  トリガー: ログオン時に自動起動"
Write-Host ""
Write-Host "  確認方法:"
Write-Host "    taskschd.msc を開いて '$TaskName' を検索"
Write-Host ""
Write-Host "  手動実行テスト:"
Write-Host "    schtasks /run /tn `"$TaskName`""
Write-Host ""
Write-Host "  登録解除:"
Write-Host "    schtasks /delete /tn `"$TaskName`" /f"
Write-Host ""
