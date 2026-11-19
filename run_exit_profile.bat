@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
where python >nul 2>nul
if %errorlevel%==0 (python scripts\09_exit_profile.py) else (py scripts\09_exit_profile.py)
echo.
pause
