@echo off
chcp 65001 >nul
title 인증키 한 번만 저장하기
echo ============================================================
echo  인증키를 이 컴퓨터(내 윈도우 계정)에 한 번만 저장합니다.
echo  저장하면 run_*.bat 파일들이 키를 묻지 않고 바로 실행돼요.
echo  키는 GitHub 폴더가 아니라 윈도우 사용자 환경변수에 저장되므로
echo  Push해도 올라가지 않아요.
echo  바꾸지 않을 키는 그냥 Enter를 누르세요.
echo ============================================================
echo.
set "K="
set /p K=TMAP(SK 오픈API) 앱키: 
if defined K (setx TMAP_APP_KEY "%K%" >nul && echo   - TMAP 키 저장됨) else (echo   - TMAP 키 건너뜀)
set "K="
set /p K=문화공공데이터광장 "2025 입출차정보" 서비스키: 
if defined K (setx KCISA_KEY "%K%" >nul && echo   - KCISA 키 저장됨) else (echo   - KCISA 키 건너뜀)
set "K="
echo.
echo 끝났어요. 이미 열려 있는 검은 창은 닫고, run_*.bat을 새로 더블클릭하세요.
echo 키를 지우려면 delete_keys.bat을 실행하세요.
pause
