@echo off
chcp 65001 >nul
title AI 오케스트라 - olpark-traffic
cd /d "%~dp0"
set PYTHONUTF8=1
where python >nul 2>nul
if %errorlevel%==0 (python orchestra\orchestra.py %*) else (py orchestra\orchestra.py %*)
echo.
echo  창을 닫아도 돼요. 문제가 있으면 위 메시지를 Claude에게 보여 주세요.
pause
