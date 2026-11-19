@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
where python >nul 2>nul
if %errorlevel%==0 (python scripts\14_live_exit_calib.py --ask-push) else (py scripts\14_live_exit_calib.py --ask-push)
echo.
pause
