@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (python scripts\12_fetch_congestion.py) else (py scripts\12_fetch_congestion.py)
echo.
pause
