@echo off
chcp 65001 > nul
echo 🛑 SNS Viewer 프로세스 정리 중...

:: scrap_sns 서버 파일명으로 실행된 프로세스만 종료
wmic process where "CommandLine like '%scrap_sns_server.py%'" call terminate 2>nul

echo.
echo 🧹 Invisible 모드로 실행된 잔여 프로세스(CMD)를 정리하려면...
echo 엔터를 누르면 'SNS Feed Viewer'와 관련된 모든 창을 닫습니다.
pause

:: WMIC Command
taskkill /V /FI "WINDOWTITLE eq SNS Feed Viewer Launcher*" /F 2>nul
wmic process where "CommandLine like '%run_viewer.bat%'" call terminate 2>nul
wmic process where "CommandLine like '%scrap_sns_server.py%'" call terminate 2>nul

echo.
echo ✨ scrap_sns_server.py 프로세스 정리가 완료되었습니다.
echo 5000번 포트를 다른 프로세스나 구버전 server.py가 사용 중이면 별도로 종료해야 합니다.
pause
