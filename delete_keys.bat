@echo off
chcp 65001 >nul
title 저장한 인증키 지우기
reg delete HKCU\Environment /v TMAP_APP_KEY /f >nul 2>nul && echo TMAP 키 지움
reg delete HKCU\Environment /v KCISA_KEY /f >nul 2>nul && echo KCISA 키 지움
reg delete HKCU\Environment /v DATAGO_KEY /f >nul 2>nul && echo 공공데이터포털 키 지움
setx OLPARK_KEYS_CLEARED 1 >nul
reg delete HKCU\Environment /v OLPARK_KEYS_CLEARED /f >nul 2>nul
echo 끝났어요. 이제 run_*.bat을 실행하면 다시 키를 물어봐요.
pause
