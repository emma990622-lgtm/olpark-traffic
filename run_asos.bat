@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PY=python
where python >nul 2>nul || set PY=py
git pull --rebase --autostash
echo [1/2] 기상청 ASOS 시간자료(서울) 받기
%PY% scripts\26_get_asos.py
if errorlevel 1 goto end
echo [2/2] 빠른 출구·날씨 분석 다시 계산
if not exist data\raw\vhcle_use mkdir data\raw\vhcle_use
if exist "%USERPROFILE%\Downloads\KS_OLPARK_VHCLE_USE_STTUS_*.csv" copy /Y "%USERPROFILE%\Downloads\KS_OLPARK_VHCLE_USE_STTUS_*.csv" data\raw\vhcle_use\ >nul
if not exist data\raw\vhcle_use\*.csv (
  echo data\raw\vhcle_use 폴더에 차량 이용현황 CSV를 넣은 뒤 다시 실행해 주세요.
  goto end
)
%PY% scripts\25_exit_gate_weather.py
echo.
%PY% scripts\push_results.py data/raw/weather_asos_108.csv web/data/exit_gate.json data/processed/exit_gate_pairs.csv data/processed/exit_weather_shows.csv
:end
echo.
pause
