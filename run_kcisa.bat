@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
  python scripts\03_fetch_kcisa_2025.py
) else (
  py scripts\03_fetch_kcisa_2025.py
)
echo.
pause
