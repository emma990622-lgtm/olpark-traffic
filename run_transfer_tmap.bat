@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >/dev/null 2>nul
if %errorlevel%==0 (python scripts\06_transfer_routes_tmap.py) else (py scripts\06_transfer_routes_tmap.py)
echo.
pause
