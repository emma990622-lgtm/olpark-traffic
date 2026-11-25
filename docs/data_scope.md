# 사용 데이터 목록·출처 및 검수 내역 (`olpark-traffic`)

> **최종 갱신**: 2026-11-24  
> **대상 서비스**: KSPO DOME·올림픽공원 공연 전후 주차·교통·도착 시간 안내 웹앱 (https://olpark-traffic.vercel.app)  
> **원칙**: 화면과 분석에 쓰이는 모든 수치는 원천 데이터의 **공식 제목·제공 기관·식별 코드·기간·산출 방법**을 함께 밝히며, 원본 결측·오류는 임의로 메우지 않고 검수 기준에 따라 보정하거나 제외 사유를 공개합니다(`web/data/data_quality.json`, `web/data-guide.html`).

---

## 1. 사용 데이터 전체 목록 (총 21종 — 제목 및 출처)

### 1-1. 한국체육산업개발(KSPO&CO) 공공데이터 (8종)

| # | 데이터 제목 (식별코드·API) | 제공 기관 · 출처 플랫폼 | 기간 · 규모 | 단위 · 주요 항목 | 확보 · 갱신 상태 | 프로젝트 활용처 |
|---|---|---|---|---|---|---|
| A1 | **올림픽공원 차량 이용현황** (`KS_OLPARK_VHCLE_USE_STTUS`) | 한국체육산업개발(주) · [문화 빅데이터 플랫폼](https://www.bigdata-culture.kr) | 2024-03 ~ 2025-12 (22개월, 약 606만 건) | 차량 입출차 1건 = 1행(분 단위) · 일자, 암호화 차량식별값, 입차시각, 입구명(7개 문 전체), 출차시각, 출구명 | ✅ 확보 (주인 PC `data/raw/vhcle_use/*.csv`, 가공본 저장소 수록) | **핵심.** 주차 구역(들어온 문)·날씨별 빠른 출구 비교(`scripts/25` → `exit_gate.json`), 15분 최대 출차 파동(`scripts/16` → `kspo_waves.json`), 대관 인원 대비 관객 차 분석(`scripts/24` → `show_cars_vhcle.csv`, `aud_cars.csv`) |
| A2 | **올림픽공원 주차장 입출차 정보 (2025년)** (`API_CPM_008`) | 한국체육산업개발(주) · [문화공공데이터광장](https://www.culture.go.kr/data) | 2025-01 ~ 2025-12 (총 2,411,225행 중 2,411,135행 수집 · 중복 제거 유효 2,083,451행) | 차량 1대 = 1행(초 단위) · 기록번호(`LOCAL_ID`), 입구, 입차시간, 출구, 출차시간 | ✅ 수집 완료 (`scripts/03`, `data/processed/kcisa_2025_check.json`, 미수신 90행 `kcisa_inout_2025.gaps.txt` 기록) | 공연 후 출차 곡선·출구 비중(`scripts/09` → `exit_profile.json`), 주차 대수 곡선(`scripts/11` → `park_profile.json`), 당일 출차 감지·입차 시각(`scripts/14` → `live_exit.json`), 시작 시각별 입출차 곡선(`scripts/18` → `exit_curves.json`), 관객 성향 회귀(`scripts/15` → `audience_car.json`) |
| A3 | **올림픽공원 주차장 입출차 정보 (2024년 7월)** | 한국체육산업개발(주) · [공공데이터포털](https://www.data.go.kr) | 2024-07-01 ~ 2024-07-31 (215,528행) | 차량 1대 = 1행(분 단위) · 일자, 입차일시, 출차일시 (동2·남2·북2문 구역 합계) | ✅ 확보 (`data/raw/parking_inout_202407.csv`) | 2024년 7월 일별·15분 입출차 기준선(`scripts/01, 04` → `exits_2024_07.json`, `daily_summary_202407.csv`) 및 A2(2025년)와 결합한 다년도 입출차 분석 |
| A4 | **올림픽공원 대관 데이터** (`2026-07` 개방판) | 한국체육산업개발(주) · [문화 빅데이터 플랫폼](https://www.bigdata-culture.kr) | 2008 ~ 2026-07 (5,482건, KSPO DOME 정산 인원 보유 공연 168회 매칭) | 대관 1건 = 1행 · 시설명, 행사명, 대관 시작·종료일, 신청 인원, **정산 인원(실제 관람객 수)** | ✅ 확보 (`data/raw/kspo_rent_info.csv`) | 회당 실제 관객 수 산출 및 관객 규모↔관객 차 대수 상관 검증(`scripts/24, 32` → `aud_cars.csv`) |
| A5 | **한국체육산업개발_주차장 혼잡도 정보** (`15164156`) | 한국체육산업개발(주) · [공공데이터포털](https://www.data.go.kr/data/15164156/openapi.do) | 2025-02-22 ~ 2026-08-29 (92일, 699건) | 구역·시각 1건 = 1행 · 주차구역(`P1A`~`P11` 등), 총 주차면수, 혼잡도(원활·혼잡·만차), 등록시간 | ✅ 확보 (`scripts/12` → `data/raw/kspo_parking_congestion.csv`) | 공연일 구역별 만차 발생 빈도 및 공연 시작 전 만차 시각 요약(`scripts/13` → `congestion_summary.json`) |
| A6 | **올림픽공원 실시간 주차현황 API 및 공식 주차시설 안내** (`parkingorsApi.do`, `parking.do`) | 한국체육산업개발(주) · [올림픽공원 온라인 주차 안내](https://www.ksponco.or.kr/online/main/parking.do) | 실시간 (현재 시점 + 수집기 누적 기록 2026-11-18~) | 공원 전체 합계(`parking_sum`) 및 문별 주차구역·면수(`parking_zones.csv`: 동2·남2·북2문 2,120면 등) | ✅ 실시간 연동 (`api/parking.js`) 및 새벽 기준값 자동 기록 (`olpark-collector/night_parking.py`) | 실시간 주차 대수 표시(`parkActual()` 새벽 미종료 차량 보정 반영) 및 문별 주차구역 매핑(`data/processed/parking_zones.csv`) |
| A7 | **올림픽공원 공식 공연·행사 일정 안내** (`eventInfoListAjax.es`) | 한국체육산업개발(주) · [올림픽공원 누리집](https://www.ksponco.or.kr/olympicpark) | 2022-11 ~ 2027-07 (행사 500여 건 → 일자·공연장별 2,043행) | 행사 1건 → 날짜×공연장 1행 · 공연명, 공연장, 기간, 시작시각 원문, 관람시간(`ndTm`), 예매처 링크(`evtLink`) | ✅ 매일 2회 자동 갱신 (`.github/workflows/update_shows.yml`, `scripts/28, 02`) | 관객 화면 1단계 공연 선택(`web/data/events.json`) 및 전 분석 스크립트의 공연일·비공연일 구분 기준(`data/processed/event_days.csv`) |
| A8 | *(검수 후 미사용·대체)* **2025 차량입출차·공연·날씨 연계 데이터** (`API_CPM_009`) | 한국체육산업개발(주) · [문화공공데이터광장](https://www.culture.go.kr/data) | 2025년 (약 7,803~8,000행) | 1시간 단위 · 주차대수, 방문객, 기온, 강수량, 휴일, 공연명, 공연관람객수 | ⚠ 검수 결과 핵심 수치·공연명 칸이 모두 빈칸으로 확인됨 (`2026-11-21` 점검) | 직접 쓰지 않고 공개 원천(A2·A3·A7·B2·B3·C3·D1)을 결합해 동일 구성의 **`data/processed/visitor_hourly.csv`** 를 자체 구축해 대체(관람객 수는 A4 대관 데이터로 보완) |

---

### 1-2. 서울특별시 공공데이터 (6종 — 서울 열린데이터광장 · TOPIS)

| # | 데이터 제목 (식별코드·서비스명) | 제공 기관 · 출처 플랫폼 | 기간 · 규모 | 단위 · 주요 항목 | 확보 · 갱신 상태 | 프로젝트 활용처 |
|---|---|---|---|---|---|---|
| B1 | **서울시 실시간 도시데이터 — 올림픽공원** (`OA-21285`, `citydata`) | 서울특별시 · [서울 열린데이터광장](https://data.seoul.go.kr/dataList/OA-21285/A/1/datasetView.do) | 실시간 (5분 갱신) + 공연일 5분 간격·평시 1시간 간격 누적 수집(2026-11-18~) | 공원 주변 도로 **58개 구간** 속도(`SPD`)·혼잡도(`원활/서행/정체`), 실시간 인구·연령·성별, 주변 주차장(`PRK_STTS`), 지하철, **24시간 기상예보(`FCST24HOURS`)** | ✅ 실시간 연동 (`api/roads.js`, `api/weather.js`) + GitHub Actions 자동 수집 (`olpark-collector`) | 3D·평면 도로 소통 지도(`links.json`), **가는 방면별 출구→합류 교차로 둘레 도로 실측 주행 시간**(`scripts/29` → `gate_directions.json`), 공연 당일 기상예보 판별(`exit_gate.js`), 현장 실측 검증(`scripts/20`) |
| B2 | **행정동 단위 서울 생활인구(내국인)** (`OA-14991`, 송파구 오륜동 `11710566`) | 서울특별시(KT 통신 빅데이터 추계) · [서울 열린데이터광장](https://data.seoul.go.kr/dataList/OA-14991/S/1/datasetView.do) | 2024-06 ~ 2026-07 (1시간 간격, 약 18,936시간) | 1시간 × 행정동 1행 · 총생활인구수, 남·여 5세 연령대별 생활인구 | ✅ 확보 (`data/raw/seoul_living_pop_11710566.csv`, `data/raw/visitor_weather/`) | **'주로 공연장에 도착하는 시간' 선택 공연 기준 시간대별 예상 막대그래프**(`scripts/31` → `arrival_profile.json`), 공연별 관객 연령·성별 추정 및 자가용 회귀(`scripts/15` → `audience_car.json`), 시간별 방문객 모형(`scripts/22, 23` → `visitor_forecast.json`) |
| B3 | **서울시 지하철 호선별 역별 승하차 인원 정보** (`OA-12914` 월별 파일 · `CardSubwayStatsNew` 일별 API) | 서울특별시 · [서울 열린데이터광장](https://data.seoul.go.kr/dataList/OA-12914/S/1/datasetView.do) | 2024-06 ~ 2026-11 (약 900일, 공원 주변 5개 역: 올림픽공원·몽촌토성·한성백제·방이·둔촌오륜) | 일자 × 호선 × 역 1행 · 승차총승객수, 하차총승객수 | ✅ 확보 (`data/raw/visitor_weather/subway_*.csv`, `scripts/21`) | 공연일 지하철 이용 증가분(+28%) 및 **올림픽공원역 하차 쏠림(84~89%)** 산출 → 대중교통 분산 역 안내(`visitor.js`, `visitor_forecast.json`) |
| B4 | **서울교통공사 역간 거리 및 소요시간 정보** (`StationDstncReqreTimeHm`) | 서울교통공사 · [서울 열린데이터광장](https://data.seoul.go.kr) | 최신 표준 운행시간표 (1~8호선 전 구간) | 역간 1구간 = 1행 · 호선, 역명, 역간 거리, 소요시간(분:초) | ✅ 실시간 중계·캐시 (`api/subway.js`, 24시간 캐시) | 환승주차장 및 주변 지하철 노선 이동 소요시간 계산(`web/assets/common.js`) |
| B5 | **서울시 시영·공영주차장 실시간 주차대수 정보** (`GetParkingInfo`) | 서울특별시 · [서울 열린데이터광장](https://data.seoul.go.kr) | 실시간 (송파구·강동구 관내 공영주차장) | 주차장 1곳 = 1행 · 주차장명, 총 주차면, 현재 주차대수, 요금·운영시간 | ✅ 실시간 연동 (`api/parking.js`) | 천호역·잠실역·복정역·신천유수지 등 주변 환승 공영주차장 기초 정보(`places.json`) 및 실시간 잔여면 조회 |
| B6 | **서울시 도로별 일자별 통행속도** (월별 이력) | 서울특별시 교통정보과 · [서울교통정보센터(TOPIS)](https://topis.seoul.go.kr) | 2024-07 ~ 2026-10 (월별 파일, 공원 주변 주요 간선 14개 구간 매칭) | 일자 × 링크 × 1시간 속도(`01시`~`24시`) | ✅ 검증 완료 (`web/data/road_source_check.json`) | 서울시 실시간 도시데이터(B1) 58구간 속도와 TOPIS 공식 소통 통계의 일치도 교차검증(`road_source_check.json`, 상관계수 및 등급 일치율 확인) |
| B7 | **서울시 자치구별 도보 네트워크 공간정보** (`OA-21208`, `TbTraficWlkNet`) | 서울특별시 · [서울 열린데이터광장](https://data.seoul.go.kr/dataList/OA-21208/S/1/datasetView.do) (공공누리 1유형) | 2026-11-25 수집본(매일 갱신) · 송파구 21,779행 중 21,572행(99.0%)·강동구 19,274행 전부 → 공원 둘레만 잘라 노드 5,190·링크 7,286 | 보행자도로 노드·링크(WGS84) · 링크 길이, 고가도로·지하철·교량·터널·**육교**·**횡단보도**·공원녹지·건물내 표시 | ✅ 확보 (`scripts/34`, 서울시 키 필요 → 수집기 Actions `fetch_walknet`, `data/raw/seoul_walknet_olpark.geojson`) | 보행 길 안내(육교·횡단보도 구분) 준비. 아직 화면 미사용 |

---

### 1-3. 중앙행정기관 공공데이터 및 법정공휴일 자료 (3종)

| # | 데이터 제목 (식별코드·레이어명) | 제공 기관 · 출처 플랫폼 | 기간 · 규모 | 단위 · 주요 항목 | 확보 · 갱신 상태 | 프로젝트 활용처 |
|---|---|---|---|---|---|---|
| C1 | **기상청_지상(종관, ASOS) 시간자료 조회서비스** (`15057210`, 서울 관측소 지점 `108`) | 기상청 · [공공데이터포털](https://www.data.go.kr/data/15057210/openapi.do) | 2024-01-01 ~ 2025-12-31+ (1시간 간격 지상관측) | 1시간 = 1행 · 관측시각(`tm`), 기온(`ta`), 강수량(`rn`), 풍속(`ws`), 습도(`hm`), 적설(`sd_tot`), 체감온도(`feels`) | ✅ 확보 (`scripts/26` → `data/raw/weather_asos_108.csv`) | **관객 출구 안내의 비·추위 출차 지연 회귀분석 공식 기상 원천**(`scripts/25, 32` → `exit_gate.json` `weather`, 투어 고정효과 비교) |
| C2 | **국토교통부 브이월드(VWorld) 2D 데이터 API — 도로명주소 건물** (`LT_C_SPBD`) | 국토교통부 공간정보오픈플랫폼 · [브이월드(VWorld)](https://www.vworld.kr) | 최신 공간정보 (올림픽공원 일대 경위도 범위 `127.105~127.140, 37.505~37.528`) | 건물 폴리곤 GeoJSON · 건물 형상 좌표, 지상 층수(`gro_flo_co`), 건물명 | ✅ 실시간 중계·캐시 (`api/buildings.js`, 7일 캐시) | 관객·보관 화면의 MapLibre 3D 건물 입체 지도 렌더링(`web/assets/map3d.js`) |
| C3 | **대한민국 법정공휴일·대체공휴일 목록 (2024~2027)** | 인사혁신처 「관공서의 공휴일에 관한 규정」 기준 (Python `holidays` 패키지로 생성) | 2024-01 ~ 2027-12 (설·추석 연휴, 대체공휴일, 임시공휴일 포함) | 공휴일 1일 = 1행 · 날짜(`date`), 공휴일명(`name`) | ✅ 확보 (`data/processed/holidays_kr.csv`) | 평일 vs 주말·공휴일 구분(`scripts/02, 22, 23, 24, 31`), '주말 및 공휴일' 공연 회차 자동 전개 |

---

### 1-4. 민간·오픈 데이터 및 자체 조사·교차검증 데이터 (3종)

| # | 데이터 제목 | 제공처 · 라이선스 / 수집 출처 | 기간 · 규모 | 단위 · 주요 항목 | 확보 · 갱신 상태 | 프로젝트 활용처 |
|---|---|---|---|---|---|---|
| D1 | **Open-Meteo Historical Weather API (ERA5 재분석 기상 자료)** | [Open-Meteo](https://open-meteo.com) · ECMWF ERA5 재분석 (CC BY 4.0) | 2024-06-01 ~ 2026-11 (올림픽공원 좌표 `37.5207, 127.1214`, 1시간 간격) | 1시간 = 1행 · 기온, 체감온도, 강수량, 비, 적설, 습도, 풍속, 구름양, WMO 날씨코드 | ✅ 확보 (`data/raw/visitor_weather/weather_hourly_openmeteo.csv`, `scripts/21`) | 2026년까지 이어지는 시간별 방문객 연계표(`visitor_hourly.csv`) 및 방문객 예측 모형(`visitor_forecast.json`) 학습용 기상 변수 |
| D2 | **SK텔레콤 TMAP Open API (보행자 경로 · 자동차 경로 · 타임머신 · 실시간 교통)** | SK텔레콤(티맵모빌리티) · [TMAP Open API](https://openapi.sk.com) | 2026-11 사전 측정 고정본 + 공연 종료 시점 도로 검증 10회(`road_check_*.csv`) | 주차장·역→공연장 보행 거리·시간·경로선, 도로 링크 형상, 서울시 도로 속도 대비 TMAP 통행시간 | ✅ 정적 JSON·GeoJSON 구축 완료 (`scripts/05~08, 10`) — **관객 화면 런타임 호출 없음(무료 운영 보장)** | 주차장·지하철역→각 공연장 도보 시간·경로(`walk_tmap.json`, `walk_routes.geojson`), 도로 57구간 상세 선형(`link_shapes.geojson`), 서울시 도로 소통 정확도 교차검증(`road_check.json`) |
| D3 | **공식 예매처 공연 상세 정보 및 언론 현장 기사 기반 실제 공연 종료 시각 조사 데이터** | **예매처**: NOL 티켓(인터파크)·YES24 티켓·멜론티켓 상세 페이지 / **종료 시각 조사**: 동아일보·조선일보·파이낸셜뉴스·스타뉴스 등 언론 현장·성료 기사 및 후기 원문 URL 65건 | 앞으로 열리는 공연 25건(`show_seller.csv`·`show_official.csv`) + 과거 KSPO DOME 공연 65건 전수 대조(`show_runtime_known.csv`, 실제 종료 시각 확정 **43회·20개 투어**) | 공연 회차 1건 = 1행 · 예매처 시작시각·예정 관람시간·원문 URL·확인일 / 과거 공연 실제 러닝타임(분)·종료 시각·근거 문구·기사 URL·신뢰 등급 | ✅ 예매처 매일 2회 자동 갱신(`scripts/28, 27`) · 과거 공연 검증표 수록(`scripts/30`) | 관객 화면 1단계 회차 시각·예정 종료 안내(`events.json`) 및 3단계 **'공연 종료 후 관객 차 50%(약 24분)·90%(약 1시간 11분) 출차 소요 시간'** 산출(`exit_after_end_shows.csv`, `exit_gate.json`) |
| D4 | **OpenStreetMap · OpenFreeMap 올림픽공원 보행로·육교·내부도로 공간데이터** | [OpenStreetMap 기여자](https://www.openstreetmap.org/copyright) (ODbL) · [OpenFreeMap](https://openfreemap.org) 벡터 타일 | 올림픽공원 전역 보행로·보행육교(`bridge`, `layer=1`)·공원 내부 차도 377개 선형 | GeoJSON 선형·다각형 · 보행 전용 여부, 교량(`brunnel=bridge`), 층(`layer`) | ✅ 확보 (`data/processed/osm_park_paths_raw.json` → `scripts/33`) | 3D 바탕지도 및 **하부 차도(`level=0`, 보행 가능) 위로 지나가는 만남의광장~KSPO DOME 입체 보행 인도·육교(`level=1`)** 표시·다층 보행 네트워크(`pedestrian_overpass.geojson`, `pedestrian_network.geojson`) |

> **참고(보관된 선택 기능)**: `api/drive.js`(네이버 클라우드 플랫폼 Directions 5 API)와 `api/drivetime.js`(TMAP 실시간 자동차 경로 API)는 초기 환승주차 비교 시제품용 서버 함수로 저장소에 남아 있으나, 공공기관 무상 운영 원칙에 따라 현재 관객 화면(`web/index.html`)에서는 호출하지 않으며 출구·방면 안내는 100% 공공데이터 정적 분석(`exit_gate.json` + `gate_directions.json`)으로 동작합니다.

---

## 2. 웹앱 공개 데이터(`web/data/*`) ↔ 원천 데이터 연결표

사이트(`https://olpark-traffic.vercel.app/data/<파일명>`)와 저장소 `web/data/`에 공개된 모든 가공 파일의 생성 스크립트와 원천 데이터 대조표입니다.

| 공개 파일 (`web/data/`) | 주요 내용 | 생성 스크립트 | 결합된 원천 데이터 번호 |
|---|---|---|---|
| `events.json` | 앞으로 열리는 공연(및 2024.07 비교용) 날짜·공연장·시작 시각·관람시간·예매처 출처 | `scripts/28, 02, 27` | A7, C3, D3 |
| `exit_gate.json` | 주차 구역(들어온 문)별 빠른 출구, 비·추위 출차 지연 회귀, **공연 종료 후 50%·90% 출차 소요 시간** (KSPO DOME **171회**, 관객 차 **132,644대**) | `scripts/25, 30, 32` | A1, A7, C1, D3 |
| `gate_directions.json` | 가는 방면(북서·북동·남서·남동 4권역 합류 교차로)별 세 출구→둘레 도로 실측 주행 시간 | `scripts/29` | B1 (`links.json` + `olpark-collector` 공연 후 39회 수집) |
| `arrival_profile.json` | 선택한 공연 기준 **주로 공연장에 도착하는 시간** 6구간 비중(%) 및 차량 입차·지하철 집중 안내 | `scripts/31` | B2, A7, C3, A2·A3 (`live_exit.json`), B3 |
| `places.json` | 공연장·공원 주차장·주변 환승 공영주차장·지하철역 좌표·면수·요금·도보 기본값 | `scripts/04` | A6, B1, B4, B5 |
| `walk_tmap.json`, `walk_routes.geojson` | 주차장·역 → 올림픽공원 내 각 공연장 보행 거리·소요시간 및 보행 경로 도형 | `scripts/05` | D2, A6, B5 |
| `links.json`, `link_shapes.geojson` | 올림픽공원 주변 도로 58개 구간 목록·시종점 좌표 및 상세 도로 선형 | `scripts/04, 07` | B1, D2 |
| `pedestrian_overpass.geojson`, `pedestrian_network.geojson` | 하부 차도(`1230085700`, 보행 가능) 위로 지나가는 **만남의광장~KSPO DOME 입체 보행 인도·육교** 및 공원 전역 차도 겸용(`level=0`)·육교(`level=1`) 다층 보행 네트워크 | `scripts/33` | D4, B1, D2, A6 |
| `kspo_waves.json` | KSPO DOME 공연 후 15분 출차 최대 시각·대수 요약 (**171회** 공연) | `scripts/16, 32` | A1, A7 |
| `exit_profile.json` | 공연 후 출차 급증 시점, 관객 차 50%·90% 출차 시간, 7개 출구 비중 | `scripts/09` | A2, A3, A7 |
| `live_exit.json` | 공연 당일 실시간 출차 감지 규칙·오차 검증 및 관객 차 입차 절반·90% 시각 | `scripts/14` | A2, A3, A7 |
| `exit_curves.json` | 공연 시작 시각별 15분 입차·출차 중앙값 곡선 및 비공연일 기준선 (70회 공연) | `scripts/18, 32` | A2, A3, A7, C3 |
| `park_profile.json` | 공연 시작 기준 5분 단위 주차 대수 곡선 및 면수 초과 빈도 | `scripts/11` | A2, A3, A6, A7 |
| `audience_car.json` | 공연별 추정 관객 연령·성별 구성과 관객 차 대수 다중회귀분석 | `scripts/15, 32` | A2, A3, A7, B2, C3 |
| `visitor_forecast.json` | 시간별 행정동 생활인구 예측 회귀 계수·검증 및 주변 5개 역 지하철 하차 쏠림 | `scripts/21, 22, 23` | B2, B3, A7, C3, D1, A2·A3 |
| `congestion_summary.json` | 공원 내 구역별 만차 발생 비율 및 공연 시작 전 만차 시각 | `scripts/12, 13` | A5, A7 |
| `data_quality.json` | 원천 데이터 전수 검수 결과(11개 항목), 2025년 월별 수신율, 제외 공연 목록 | `scripts/17, 19` | A1, A2, A5, A6, A7, A8, B1 |
| `road_check.json`, `road_source_check.json` | 서울시 도시데이터 도로 속도 ↔ TMAP·TOPIS 교차검증 결과 | `scripts/10` | B1, B6, D2 |
| `transfer_tmap.json`, `station_drive.json` | (보관) 환승주차장→역 도보 및 공원까지 운전 시간 비교 | `scripts/06, 08` | D2, B5 |
| `exits_2024_07.json` | 2024년 7월 한 달 15분 단위 입차·출차 시계열(예비·비교 기준) | `scripts/04` | A3, A7 |

---

## 3. 데이터 검수 및 보강 내역 (품질 점검 기록)

프로젝트에 쓰인 모든 원천 데이터를 교차 검수하여 아래와 같이 오류·결측·함정을 보정했습니다(상세 수치는 `web/data/data_quality.json` 공개).

| 구분 | 대상 데이터 | 검수에서 확인한 문제 | 보강 · 처리 방법 |
|---|---|---|---|
| 1 | **2025년 입출차 (`API_CPM_008`)** | 2025년 8·9·11·12월 원본이 한 달 **65,535행**(구형 엑셀 행 한도)에서 잘려 있음 (`kcisa_2025_check.json`) | 8·9월은 모든 날의 약 1/4만 남아 차량 대수 통계에서 제외하고 시각·비율에만 사용. 11·12월은 시간순 저장이라 기록이 온전히 남은 월초 공연만 사용 |
| 2 | **2025년 입출차 (`API_CPM_008`)** | 페이지 조회 시 동일 레코드가 중복 반환됨 (**327,684행 중복**) | 고유 번호(`LOCAL_ID`) 기준으로 중복을 제거해 유효 **2,083,451행(86.4%)** 만 사용 |
| 3 | **2025년 입출차 (`API_CPM_008`)** | 1~9월은 날짜가 섞여 있고, 10~12월은 입차 시각 순서대로 번호가 부여됨 | 1~9월은 블록 수신율로 가중 보정하고, 10~12월은 각 공연 입차 시간대의 번호 폭 대비 **90% 초과 수신된 공연만** 채택(`ordered_ok`) |
| 4 | **2025년 입출차 (`API_CPM_008`)** | 특정 오프셋 **9개 구간(총 90행)** 에서 API 서버 시간 초과(`HTTP 504`)가 영구 반복됨 | 해당 90행의 시작·끝 오프셋과 시각을 `data/raw/kcisa_inout_2025.gaps.txt`에 투명하게 기록하고 나머지 전 구간(번호 폭 합 **99.99%**) 수집 완료 |
| 5 | **차량 이용현황 (`vhcle_use`)** | 배포 CSV 파일명의 연월 표기와 실제 수록 연월이 다르거나 동일 월이 두 파일에 중복 수록됨 | 파일명이 아닌 실제 입차일(`YYYY-MM`) 기준으로 달마다 행 수가 가장 많은 파일 하나만 선택하고 완전 중복 행을 제거(`scripts/inout_common.py`, `scripts/25`) |
| 6 | **공식 공연 일정 (`event_days.csv` · `events.json`)** | ① 사전 취소(`2025-01-04~05` 로드 투 킹덤, `2024-12-02` 취소 공지) 및 월요일 휴연 오표기(`2024-10-14` 오페라 투란도트, `'14일 공연 없음'`)가 공원 일정에 남아 공연 통계를 왜곡함(`net = -240.5대`, `-68.0대`, 나훈아 대관 회차 수 오매칭)<br>② `2025-08-10` 더보이즈 공연이 폭발물 신고 수색으로 2시간 지연 시작됨<br>③ 앞으로 열리는 장기·상설 공연의 `'수목금'`, `'주말 및 공휴일'`, 요일+특정일 혼합 표기에서 일부 요일이 누락됨 | ① 취소·휴연 3개 일자를 `event_days.csv`·`exit_gate.json`(173→**171회**)·`kspo_waves.json`(**171회**)·`exit_curves.json`(허위 `13:00` 그룹 제거)·`show_cars_vhcle.csv`·`aud_cars.csv`(나훈아 회당 정산 인원 `10,519.5`→`14,026.0명` 바로잡음)·`visitor_hourly.csv`에서 일괄 제외(`scripts/02, 32`)<br>② 지연 시작 회차는 `show_runtime_known.csv`에 `공식(시작지연)`으로 분리해 종료 후 출차 시간 통계 왜곡 차단<br>③ `scripts/02` 파서를 보강해 앞으로 열리는 공연의 수·목·토·공휴일 회차를 빠짐없이 복원 |
| 7 | **2025년 연계 데이터 (`API_CPM_009`)** | 내려받은 약 8,000행에서 주차대수·방문객·기온·강수량·공연명·관람객수 핵심 열이 **모두 비어 있음** | 빈 원본을 쓰지 않고 서울 생활인구(B2)·지하철 승하차(B3)·기상(D1)·입출차(A2·A3)·공연 일정(A7)을 직접 결합해 1시간 단위 연계표(`data/processed/visitor_hourly.csv`, 설명서 `docs/visitor_dataset.md`)를 자체 구축하고, 실제 관객 수는 대관 데이터(A4)로 보완 |
| 8 | **실시간 주차현황 (`parking_sum`)** | 출차 처리되지 않은 장기 미종료 차량 기록이 누적되어 새벽 4시에도 1,000대 이상으로 표시됨 | 차량 이용현황(A1)으로 확인한 실제 새벽 주차 중앙값(**225대**)과 매일 새벽 자동 수집값(`parking_night.csv`)의 차이만큼 차감해 보정(`parkActual()`) |
| 9 | **주차장 혼잡도 (`15164156`)** | `등록시간` 열의 분·초 자리에 월·일 숫자가 잘못 기록되어 있음(전 행 공통) | 분·초 단위는 폐기하고 신뢰 가능한 **시(hour) 단위**로만 집계(`scripts/13`) |
| 10 | **입출차 대수 vs 주차 면수** | 동2·남2·북2문 입차만 세고 24시간 이상 장기 주차를 제외해도 공식 면수(2,120면)를 넘는 공연일이 발생함 | 임의로 값을 깎지 않고 초과 회차 수(`overCapacity`)와 함께 `'기록상 면수보다 많음, 참고값'` 안내를 명시(`park_profile.json`) |
| 11 | **도로 58구간 상세 도형 (`link_shapes.geojson`)** | 서울시 도로 58구간 중 1개 구간(`LINK_ID 1230028803`)이 TMAP 도형 매칭에서 누락됨 | 누락된 1개 구간은 `links.json`의 시·종점 좌표를 잇는 직선 도형으로 자동 대체해 지도에서 빠지는 도로가 없도록 처리(`common.js`, `map3d.js`) |
