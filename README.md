# olpark-traffic

KSPO DOME·올림픽공원 공연 후 도로 혼잡 데이터 프로젝트
(한국체육산업개발 2026 공공데이터 활용 경진대회 출품용)

## 같이 작업하기
- 팀 작업 순서: [`docs/팀_작업법.md`](docs/팀_작업법.md) (각자 AI로 고치고 PR로 인수인계)
- 모든 AI 공통 규칙: [`AGENTS.md`](AGENTS.md), 프로젝트 배경: [`docs/context.md`](docs/context.md)

## 폴더
- `data/raw/` 원본 자료 (입출차, 행사 일정, 도로 58구간 목록)
- `data/processed/` 정리된 표 (일별 요약, 공연일 표)
- `scripts/` 처리 코드
  - `01_inspect_inout.py` 2024-07 입출차 점검 + 일별 요약
  - `02_build_events.py` 공식 행사 일정 → 공연일 표
  - `03_fetch_kcisa_2025.py` 2025 입출차·연계 데이터 내려받기 (키 필요)
  - `04_build_web_data.py` 웹앱용 데이터(web/data/*.json) 만들기
- `web/` 웹앱 1차 (관객·운영자 화면). 실행: `web\run_web.bat`
- `docs/data_scope.md` 사용할 데이터·기간·한계 정리 (4단계 결과)

## 실행 (윈도우)
```
python scripts\01_inspect_inout.py
python scripts\02_build_events.py
set KCISA_KEY=발급받은키
python scripts\03_fetch_kcisa_2025.py linked
python scripts\03_fetch_kcisa_2025.py inout
```
01·02는 pandas가 필요합니다 (`pip install pandas`). 03은 설치 없이 실행됩니다.

## 주의
- 인증키(서울시, 문화공공데이터광장)는 코드·파일에 적지 않습니다.
- `parking_inout_202407.csv`는 cp949(한글 윈도우) 인코딩입니다.
