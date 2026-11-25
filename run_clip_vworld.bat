@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
  python scripts\35_clip_vworld_shp.py %*
) else (
  py scripts\35_clip_vworld_shp.py %*
)
echo.
pause
