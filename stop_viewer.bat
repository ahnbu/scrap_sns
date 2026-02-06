@echo off
chcp 65001 > nul
echo 🛑 SNS Viewer 프로세스 정밀 타격 중...

:: 1. 5000번 포트(서버)를 사용하는 프로세스 찾아서 죽이기 (가장 확실함)
echo 🔍 포트 5000 점유 프로세스 검색 중...
for /f "tokens=5" %%a in ('netstat -aon ^| find ":5000" ^| find "LISTENING"') do (
    echo 🔫 발견된 PID: %%a - 강제 종료 시도
    taskkill /F /PID %%a 2>nul
)

:: 2. 혹시 모를 잔여 python.exe 정리
taskkill /F /IM python.exe /T 2>nul

echo.
echo 🧹 Invisible 모드로 실행된 잔여 프로세스(CMD)를 정리하려면...
echo 엔터를 누르면 'SNS Feed Viewer'와 관련된 모든 창을 닫습니다.
pause

:: WMIC Command
taskkill /V /FI "WINDOWTITLE eq SNS Feed Viewer Launcher*" /F 2>nul
wmic process where "CommandLine like '%run_viewer.bat%'" call terminate 2>nul
wmic process where "CommandLine like '%server.py%'" call terminate 2>nul

echo.
echo ✨ 모든 프로세스가 정리되었습니다.
pause
