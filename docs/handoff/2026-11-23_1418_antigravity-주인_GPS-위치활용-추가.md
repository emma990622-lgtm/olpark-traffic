# 이용자 위치 권한(GPS) 허용 시 주차 구역 자동 선택·가까운 역 거리·지도 내 위치 표시 추가

- 날짜·시각: 2026-11-23 14:18
- 누가: Antigravity + 주인
- 관련 Issue/PR: 없음

## 요청 해석
- 웹서비스 이용자가 위치 권한을 허가하면 브라우저 표준 위치 정보(`navigator.geolocation`, GPS)를 활용하게 한다.
- 첫 진입 시 동의 없이 권한 창을 무작정 띄우지 않고, 이용자가 GPS 버튼을 눌러 허가하거나 이미 사이트에 권한(`granted`)을 준 경우에만 동작하게 하며, 위치 좌표는 서버로 보내지 않고 브라우저 안에서만 계산한다.

## 바꾼 것
- `web/assets/common.js`:
  - 거리 계산 함수 `distMeters()`와 공용 상태 객체 `USER_GPS`(`requestUserGPS`, `clearUserGPS`, `onUserGPS`) 추가.
  - `navigator.permissions.query({ name: "geolocation" })`가 이미 `"granted"`인 재방문자에게만 조용히 현재 위치를 읽고, `"prompt"` 상태일 때는 버튼 클릭 시 권한을 요청하도록 함(버튼 새로 고침 시 `maximumAge: 0`으로 최신 위치 반영).
  - `drawRoadMap()`에서 내 위치가 평면 지도 범위 안에 있으면 `● 내 위치` 표식을 함께 그리게 함.
- `web/assets/exit_gate.js` (`#exitGate`):
  - `현재 위치(GPS)로 주차한 곳 찾기` 버튼(`#egGpsBtn`)과 안내 줄(`#egGpsNote`) 추가.
  - 기존 데이터(`walk_tmap.json` TMAP POI, `places.json`, `links.json` 서울시 도로 노드)의 검증된 기준점 15곳과 직선거리를 비교해 공원 반경 1.2km 안이면 가장 가까운 주차 구역(`북2`·`동2`·`남2`·`그 밖의 주차장`)을 자동 선택하고 오차·거리·수동 변경 안내를 함께 표시함. 1.2km 밖이면 억지로 고르지 않고 공원 밖임을 사실대로 안내함.
- `web/assets/audience.js` (`#transitSection`, 지도 섹션):
  - `가까운 역`(`#stGpsBtn`, `#stGpsNote`): 반경 3km 안이면 내 위치에서 각 역까지 추정 도보 시간(`직선거리 × 1.3, 분당 75m 추정`)과 직선거리를 표에 함께 보이며 가까운 역 순으로 정렬함.
  - 지도(`#mapGpsBtn`, `#mapGpsNote`): GPS 허용 시 3D·평면 지도에 `● 내 위치` 표식을 표시하고, 지도 버튼으로 요청했을 때 공원 반경 3km 안이면 내 위치로 부드럽게 이동함.
  - 모든 `.gps-bar`에 44px 높이의 `위치 끄기`(`data-gps-off`) 버튼을 두어 언제든 위치 표시를 끌 수 있게 함.
- `web/assets/map3d.js`: `setUserLocation(loc, opts)` 및 `.m3d.me` 마커 추가.
- `web/index.html`, `web/assets/style.css`, `docs/design.md`, `docs/context.md`: GPS 버튼·상태 요소 6개, `.gps-bar`/`.m3d.me` 스타일(`style.css?v=6`), 보호 `id` 및 결정 기록 반영.

## 확인한 방법
- `python3 scripts/check_all.py` 실행: JS 13개·파이썬·JSON·보호 `id` 검사 오류 0건, 경고 0건 확인.
- 360px 모바일 폭 Playwright 브라우저 자동 시험(5가지 상황):
  1. 공원 내 P2 옆(`37.5148, 127.1276`) 권한 허용 시 `동2문 구역` 자동 선택 및 출구 비교 표시, 평면 지도 `● 내 위치` 표시 확인.
  2. 한성백제역 앞(`37.5164, 127.1165`)에서 대중교통 탭 `내 위치 새로 고침` 시 `한성백제역` 최상단 정렬 및 360px 가로 넘침 `0px` 확인.
  3. `위치 끄기` 클릭 시 지도 마커·내 위치 열 즉시 해제 확인.
  4. 공원 밖(서울시청, 약 13.1km) 위치일 때 자동 선택하지 않고 `○ 공원 밖` 안내 표시 확인.
  5. 위치 권한 거부 시 오류 없이 `▲ 확인 안 됨` 안내 및 수동 선택 정상 동작 확인(버튼 높이 44px 이상 확인).

## 결정과 이유
- 주차 구역 폴리곤 원본이 따로 없으므로 지어낸 좌표를 쓰지 않고 저장소에 이미 검증되어 있는 `walk_tmap.json`·`places.json`·`links.json` 좌표를 기준점으로 사용했으며, 공연장 안에서 누른 경우 실제 차 위치와 다를 수 있음을 문구로 함께 안내함.
- 외부 서버로 이용자 GPS 좌표를 보내지 않고 브라우저 안에서만 계산해 개인정보 부담을 없앰.

## 건드리면 안 되는 것
- `docs/design.md` 4절에 추가한 `stGpsBtn`, `stGpsNote`, `egGpsBtn`, `egGpsNote`, `mapGpsBtn`, `mapGpsNote` `id`와 `[data-gps-off]` 속성.
- `common.js`의 `USER_GPS`, `onUserGPS`, `requestUserGPS`, `clearUserGPS`, `distMeters` 전역 함수(`audience.js`, `exit_gate.js`, `map3d.js`가 함께 사용).

## 다음 사람에게 넘길 일
1. 실제 휴대폰(HTTPS 배포 주소 `https://olpark-traffic.vercel.app`)에서 위치 권한 허용·거부·위치 끄기 동작 확인.
2. 11/27~29 공연 데이터 수집 및 기획서 정리.
