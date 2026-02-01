@echo off
chcp 65001 > nul
setlocal
title SNS Feed Viewer Launcher

echo ✨ SNS Feed Viewer를 시작합니다...

:: 1. Flask 서버를 백그라운드로 실행 (새 창에서 실행)
echo 🚀 Flask 백엔드 서버를 시작하는 중...
start /b python server.py

:: 2. 잠시 대기 (서버가 켜질 시간)
timeout /t 2 /nobreak > nul

:: 3. 기본 브라우저로 index.html 열기
echo 🌐 브라우저에서 화면을 여는 중...
start index.html

echo.
echo ✅ 실행 완료!
echo 스크래핑을 하려면 브라우저의 'Run Scraper' 버튼을 클릭하세요.
echo (이 창을 닫으면 백그라운드 서버가 종료될 수 있습니다. 최소화해두세요.)
echo.

:: 서버 로그를 볼 수 있도록 창 유지
pause
