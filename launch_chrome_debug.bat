@echo off
chcp 65001 > nul
REM Chrome Debugging Mode Launcher

echo ========================================
echo Chrome Debug Mode Launcher
echo ========================================
echo.

start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%LOCALAPPDATA%\Google\Chrome\User Data" --excludeSwitches=enable-automation --disable-blink-features=AutomationControlled --disable-infobars --no-first-run --no-default-browser-check

echo Chrome started in debug mode (port 9222)
echo You can now run the scraper script.
echo.
timeout /t 3 > nul
