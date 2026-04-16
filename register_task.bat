@echo off
schtasks /create /tn "CoupangMonitor" /tr "C:\Users\KCW\scripts\run_coupang_monitor.bat" /sc daily /st 09:00 /rl HIGHEST /f
if %errorlevel%==0 (
    echo 작업 스케줄러 등록 완료!
) else (
    echo 실패. 관리자 권한으로 다시 실행하세요.
)
pause
