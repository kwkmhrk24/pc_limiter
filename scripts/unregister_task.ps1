<#
.SYNOPSIS
    PC Limiterのタスクスケジューラ登録を解除するスクリプト
#>

$TaskName = "PC Limiter - 使いすぎ防止"

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "タスク '$TaskName' を解除しました。" -ForegroundColor Green
} else {
    Write-Host "タスク '$TaskName' は登録されていません。" -ForegroundColor Yellow
}
