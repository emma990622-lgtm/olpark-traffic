@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PY=python
git pull --rebase --autostash
where python >nul 2>nul || set PY=py
echo [1/10] park_profile
%PY% scripts\11_park_profile.py
echo [2/10] kspo_waves
%PY% scripts\16_kspo_waves.py
echo [3/10] exit_profile
%PY% scripts\09_exit_profile.py
echo [4/10] live_exit
%PY% scripts\14_live_exit_calib.py
echo [5/10] audience_car
%PY% scripts\15_audience_car_model.py
echo [6/10] exit_curves
%PY% scripts\18_exit_curves.py
echo [7/10] check_2025
%PY% scripts\17_check_2025.py
echo [8/10] data_quality
%PY% scripts\19_data_quality.py
echo [9/10] visitor_weather
%PY% scripts\21_get_visitor_weather.py
echo [10/10] visitor_hourly
%PY% scripts\22_build_visitor_dataset.py
echo.
%PY% scripts\push_results.py web/data/park_profile.json web/data/kspo_waves.json web/data/exit_profile.json web/data/live_exit.json web/data/audience_car.json web/data/exit_curves.json web/data/data_quality.json data/processed/kcisa_2025_check.json data/processed/visitor_hourly.csv
echo.
pause
