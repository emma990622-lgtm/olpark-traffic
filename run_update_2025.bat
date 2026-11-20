@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PY=python
git pull --rebase --autostash
where python >nul 2>nul || set PY=py
echo [1/6] park_profile
%PY% scripts\11_park_profile.py
echo [2/6] kspo_waves
%PY% scripts\16_kspo_waves.py
echo [3/6] exit_profile
%PY% scripts\09_exit_profile.py
echo [4/6] live_exit
%PY% scripts\14_live_exit_calib.py
echo [5/6] audience_car
%PY% scripts\15_audience_car_model.py
echo [6/6] exit_curves
%PY% scripts\18_exit_curves.py
echo.
%PY% scripts\push_results.py web/data/park_profile.json web/data/kspo_waves.json web/data/exit_profile.json web/data/live_exit.json web/data/audience_car.json web/data/exit_curves.json
echo.
pause
