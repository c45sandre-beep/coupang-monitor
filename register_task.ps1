# 쿠팡 모니터링 작업 스케줄러 등록 스크립트
# 반드시 PowerShell을 관리자 권한으로 실행하세요!

$TaskName = "CoupangMonitor"
$ScriptPath = "C:\Users\KCW\scripts\run_coupang_monitor.bat"

# 기존 작업 제거 (있다면)
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$action   = New-ScheduledTaskAction -Execute $ScriptPath
$trigger  = New-ScheduledTaskTrigger -Daily -At "09:00AM"
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -StartWhenAvailable `
    -WakeToRun $false

$principal = New-ScheduledTaskPrincipal `
    -UserId "KCW" `
    -LogonType Interactive `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action   $action `
    -Trigger  $trigger `
    -Settings $settings `
    -Principal $principal `
    -Force

Write-Host "✅ 작업 스케줄러 등록 완료!" -ForegroundColor Green
Write-Host "   작업 이름: $TaskName"
Write-Host "   실행 시각: 매일 오전 9시"
Write-Host ""
Write-Host "확인하려면: schtasks /query /tn CoupangMonitor /fo LIST"
