@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (python scripts\10_verify_roads_tmap.py) else (py scripts\10_verify_roads_tmap.py)
echo.
pause
