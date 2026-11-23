# olpark-traffic

KSPO DOME·올림픽공원 공연 후 도로 혼잡 데이터 프로젝트
(2026 공공데이터 활용 경진대회 출품용)

## 같이 작업하기
- 누구든 어떤 AI로든 고치고 `main`에 올리면 바로 https://olpark-traffic.vercel.app 에 반영돼요. 순서: [`docs/팀_작업법.md`](docs/팀_작업법.md)
- 모든 AI 공통 규칙: [`AGENTS.md`](AGENTS.md) · 프로젝트 배경·진행 상황: [`docs/context.md`](docs/context.md) · 인수인계 노트: [`docs/handoff/`](docs/handoff/)
- 올리기 전 점검: `python scripts/check_all.py`

## 사용 데이터 목록 · 출처
- 프로젝트에 사용된 **전체 데이터(20종)의 공식 제목·제공 기관·출처·검수 및 보강 내역**: [`docs/data_scope.md`](docs/data_scope.md)
- 시간별 방문객·기상·입출차 연계표(`visitor_hourly.csv`) 칸별 설명: [`docs/visitor_dataset.md`](docs/visitor_dataset.md)
- 웹사이트 결과 데이터(JSON) 명세서: https://olpark-traffic.vercel.app/data-guide.html (`web/data-guide.html`)

## 폴더
- `data/raw/` 원본 자료 (입출차, 대관 정산 인원, 주차장 혼잡도, 기상청 ASOS, 생활인구·지하철·기상, 행사 일정, 도로 58구간 목록)
- `data/processed/` 정리·검수된 표 (공연일 표, 출구·날씨 집계, 종료 시각 확인 회차표, 시간별 방문객 연계표, 2025 입출차 점검표)
- `scripts/` 데이터 수집·검수·가공 코드 (`01`~`32`, 올리기 전 전체 점검 `check_all.py`)
- `web/` 관객용 웹앱(`index.html`) · 결과 데이터 설명서(`data-guide.html`). 실행: `web\run_web.bat` (이전 운영자 화면은 `archive/operator/` 보관)
- `api/` Vercel 서버 함수 (실시간 주차·도로 소통·24시간 기상예보·지하철 운행시간·3D 건물 중계)

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
