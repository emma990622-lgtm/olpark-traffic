@echo off
chcp 65001 >nul
title 올팍 웹앱 서버 - 이 창을 닫으면 웹앱이 꺼져요
cd /d "%~dp0"
echo.
echo  ==========================================================
echo   올팍 웹앱 서버가 켜졌어요:  http://127.0.0.1:8000
echo   웹앱을 보는 동안 이 창을 닫지 마세요. (최소화는 괜찮아요)
echo   다 봤으면 이 창을 닫으면 돼요.
echo  ==========================================================
echo.
start "" http://127.0.0.1:8000
where python >nul 2>nul
if %errorlevel%==0 (python -m http.server 8000 --bind 127.0.0.1) else (py -m http.server 8000 --bind 127.0.0.1)
echo.
echo  서버가 멈췄어요. 위에 나온 오류 메시지를 Claude에게 보여 주세요.
pause
