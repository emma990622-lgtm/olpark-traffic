@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PY=python
where python >nul 2>nul || set PY=py
git pull --rebase --autostash
%PY% scripts\17_check_2025.py
echo.
pause
