@echo off
chcp 65001 >nul
title AI Orchestra - olpark-traffic
cd /d "%~dp0"
set PYTHONUTF8=1
set ORCH_PAUSE=1
where python >nul 2>nul
if %errorlevel%==0 (python orchestra\orchestra.py %*) else (py orchestra\orchestra.py %*)
if errorlevel 9009 pause
