# 디자인 규칙 및 JS↔CSS 계약서 (`docs/design.md`)

> ALL PARK 관객 화면에는 `park-web.css`가 공통 스타일 위에 적용된다. `park-journey.js`가 `data-journey` 화면과 `data-car` 하위 단계를 전환한다. 주차 위치와 방면 선택은 `park-zone-selected` 및 `park-direction-selected` 이벤트로 연결한다. 기존 필수 ID와 `#mode button.on` 상태를 유지한다. `.topic-choices`는 안내 진입 버튼, `.exit-options`와 `.is-recommended`는 출구 비교 목록과 추천 표시다. 화면 제목과 행동 버튼은 명사형을 쓰고, 이동 감소 설정에서는 전환 애니메이션을 끈다.

어떤 AI든(Claude Code, Antigravity, Codex 등) 화면을 고치거나 확인할 때 함께 보는 기준 문서다.
공통 원칙은 `AGENTS.md`, 프로젝트 배경과 데이터 함정은 `docs/context.md`를 먼저 따른다.

---

## 1. 디자인 방향 (투트랙 통일 시스템)

- **공통 기반 — KRDS(디지털 정부서비스 UI/UX 가이드라인)**
  - 글꼴: `Pretendard Variable` 다이나믹 서브셋 CDN (`index.html`, `operator.html` `<head>`에 연결)
  - 한국어 줄바꿈: `body` 전체 `word-break: keep-all`, 표 핵심 열 `.nowrap` 적용 (`동2문`, 시각 등이 두 줄로 깨지지 않게 함)
  - 숫자 정렬: 지표·표·요금·시간·잔여면에 `font-variant-numeric: tabular-nums` 적용
  - 접근성: 명도 대비 **4.5:1 이상** 유지, 누르는 요소(`select`, `button`, `.toggle button`, `.timectl button`, `details summary`) 최소 높이 **`--tap-min: 44px`**, 상태 표시 시 **색상 + 기호(`●`/`▲`/`■`/`○`) + 글자** 동시 표기
- **관객 화면 (`web/index.html`, 모바일 `360px` 우선 · 최대 폭 `760px`)**
  - **Toss TDS**: 선택한 공연 요약(`.event-summary`, `.stat-strip`) 및 주차 선택지 상단 핵심 3지표 스트립(`.opt-metrics` > `.metric-card`)으로 5초 스캔 지원
  - **카카오T 주차**: 공원 주차장 실시간 보정 잔여면·점유율 게이지 바(`.live-lot-box`, `.occ-bar`) 및 환승주차장 빈자리 상태 칩
  - **Citymapper**: 환승주차(`갈 때` / `나올 때`) 이동 경로를 문장 나열 대신 단계별 알약 칩(`.route-steps` > `.step-pill`)으로 시각화
- **운영자·기관 화면 (`web/operator.html`, PC `1200px` 우선 · `body.is-operator`)**
  - **KRDS + 서울시 실시간 도시데이터 대시보드**: 상단 점검 필터 바(`.filter-bar`), 상단 상태 컬러 보더 KPI 4종(`.kpi`), 실시간 도로 교차검증 박스(`.verify-box`), 출구 비중 미니 바(`.share-cell`), A4 한 장 인쇄용 브리핑 시트(`.brief`, `@media print`)

---

## 2. CSS 변수(`:root`) 체계 (`web/assets/style.css`)

새 색·크기는 하드코딩하지 않고 아래 변수를 쓰거나 `:root`에 변수를 추가한다.

| 구분 | 변수 | 용도 및 규칙 |
|---|---|---|
| 표면·배경 | `--bg`, `--card`, `--surface-2`, `--surface-3` | 페이지 바탕(`#f2f5f9`), 기본 카드(`#fff`), 내부 보조 박스·표 헤더(`#f8fafc`), 토글 트랙(`#eef2f7`) |
| 글자·선 | `--ink`, `--ink-2`, `--ink-3`, `--line`, `--line-strong` | 본문(`#161d2b`), 보조 설명(`#475467`, 대비 7:1+), 캡션(`#525e71`, 대비 6.1:1+), 구분선 |
| 주요 강조 | `--accent`, `--accent-hover`, `--accent-soft`, `--accent-border` | 주요 버튼·활성 탭·추천 테두리·선택 공연장 마커(`#1d4ed8`) |
| 상태: 원활/여유 | `--good`, `--good-ink`, `--good-bg`, `--good-border` | 도로 원활·주차 여유·평소 수준 (`●` 기호 병기) |
| 상태: 서행/주의 | `--warn`, `--warn-ink`, `--warn-bg`, `--warn-border` | 도로 서행·혼잡 주의 (`▲` 기호 병기) |
| 상태: 정체/집중 | `--bad`, `--bad-ink`, `--bad-bg`, `--bad-border` | 도로 정체·혼잡 집중 (`■` 또는 `●` 기호 병기) |
| 상태: 자료없음 | `--none`, `--none-ink`, `--none-bg` | 미수집 구간·비교 기준 평일 점선 (`—` 기호 병기) |
| 지하철 노선 | `--subway-2`, `--subway-5`, `--subway-8`, `--subway-9` | `.line-badge.l2 / .l5 / .l8 / .l9` |
| 규격 | `--radius` (`16px`), `--radius-sm` (`10px`), `--tap-min` (`44px`) | 카드 모서리 및 터치 최소 크기 |

> **주의**: `--good` / `--warn` / `--bad` / `--none`의 의미는 `map3d.js`의 `IDX_HEX` 및 `common.js`의 `IDX_COLOR`와 반드시 일치시킨다.

---

## 3. JS ↔ CSS 클래스 계약표 (인수인계 필수 대조표)

- 클래스 이름을 바꾸거나 지울 때는 **JS와 CSS를 같은 작업에서 함께** 고친다(한쪽만 바꾸면 화면이 깨진다).
- 새 클래스를 만들면 이 표에 한 줄 추가하고, 인수인계 노트(`docs/handoff/`)의 "건드리면 안 되는 것"에도 적는다.

| 생성 위치 (파일 · 함수) | 클래스 이름 | 역할 및 조건 |
|---|---|---|
| 공통 (`common.js` · `levelOf`, 보관 운영자용) | `.chip.good`, `.chip.warn`, `.chip.bad`, `.chip.accent` | 강조·상태 배지 (`audience.js` 1단계 공연 요약에서는 혼잡 배지 미표시, `archive/operator`에서만 `levelOf` 사용) |
| 공통 (`common.js` · `lineBadgesHTML`) | `.line-badge`, `.l2`, `.l5`, `.l8`, `.l9` | 호선 번호별 색상 알약 배지 |
| 공통/3D지도 (`common.js`, `map3d.js`) | `.legend`, `.m3d`, `.m3d.lot`, `.m3d.st`, `.m3d.venue`, `.m3d.dome`, `.m3d.me` (MapLibre `ped-overpass` 레이어 포함) | 범례, 3D 지도 HTML 캡슐 마커 및 `roads` 위에 그려지는 입체 보행 인도·육교(`ped-promenade-fill`·`ped-overpass-3d` 등, `.m3d.me`는 GPS 허용 시 `● 내 위치` 표시, `map3d.failed` 시 평면 지도 자동 펼침). **이름표 겹침**: `map3d.js`의 `declutter()`가 화면에서 겹치는 `.m3d`를 중요도(dome > me > st > 공원 주차장 > 다른 주차장 > venue) 낮은 쪽부터 `visibility:hidden`(지도 이동·확대 때 다시 계산). **저작권 ⓘ**는 접힌 상태로 시작, `park-web.css`의 `details summary` 48px 규칙에서 제외. **평면 지도**(`drawRoadMap`)는 화면 폭에 맞춰 글씨 12px 안팎으로 그리고(`ResizeObserver`로 보일 때 다시 그림), 겹치는 이름은 위·아래·옆 자리를 찾고 없으면 이름만 뺌 |
| 관객 (`common.js`, `audience.js`, `exit_gate.js`) | `.gps-bar`, `button.ghost.gps-off` (`[data-gps-off]`) | 이용자 위치 권한(GPS) 동의 버튼 바 및 `위치 끄기` 버튼(최소 높이 44px, 기호+글자 상태 병기) |
| 관객 (`audience.js` · `render`) | `.event-summary`, `.event-head`, `.stat-strip`, `.stat-item` (`.sk`, `.sv`) | Step 1 선택 공연 제목·공연장 배지(`.chip.accent`)·3열 핵심 시간/좌석 요약 |
| 관객 (`exit_gate.js`) | `.eg-zones` (안의 `button.on` + `button.span-all` + `aria-pressed`), `.eg-reco`, `.eg-gate`, `.eg-wx` (+ `.chip.good`/`.warn`/`.accent`, `table.list`, `.subhead`, `.footnote` 재사용) | 3단계 '공연 끝나고 어느 문으로 나갈까요?' 카드(주차 구역 `#egZone` + 가는 방면 빠른 버튼 `#egWay`). 고른 버튼은 테두리+`✓` 글자로도 표시, 판단은 기호+글자(`● 가장 빠름`, `● 거의 비슷해요`, `▲ +n분`). 차로 오는 관객(`#mode`가 `car`일 때)에게만 보임 |
| 관객 (`visitor.js`) | `.arr-chart-wrap`, `.arr-chart-box`, `.arr-chart-head`, `.arr-chart-title`, `.arr-chart-legend`, `.arr-bars`, `.arr-col` (`.is-good`, `.is-warn`, `.is-bad`), `.arr-val`, `.arr-track`, `.arr-fill`, `.arr-lbl`, `.arr-clock`, `.arr-rel`, `.arr-start-row`, `.arr-start-pill` (+ `.le-status`, `.notice.info`, `.chip.bad` 재사용) | '주로 공연장에 도착하는 시간' 카드. 1단계에서 고른 공연(날짜·시작 시각·공연장) 기준 시작 6시간 전~시작 6구간 예상 도착 비중(%) 세로 막대그래프(막대마다 `●`/`▲`/`■` 기호 + 퍼센트 동시 표기) |
| (삭제·CSS 보관) 옛 주차 선택지 (`style.css`) | `.reco`, `.opt`, `.opt-metrics`, `.metric-card`, `.live-lot-box`, `.occ-bar`, `.tlot-list`, `.tlot`, `.route-steps`, `.step-pill` | 2026-11-23 '어디에 주차할까요?'(`#carSection`) 삭제에 따라 화면에서 제거 |
| (보관) 운영자 (`operator.js` · `roadCheck`) | `.verify-box`, `.verify-title`, `.verify-list` | TOPIS·TMAP 실시간 도로 자료 교차검증 결과 박스 (`<ol>` 자동 번호) |
| 운영자 (`operator.js` · `render`) | `.kpis`, `.kpi` (`.is-bad`, `.is-warn`, `.is-good`), `.v`, `.l` | 상단 핵심 대응 지표 4종 카드 |
| 운영자 (`operator.js` · `showTime`) | `.timectl`, `.trow`, `.tlabel`, `.phase` | 3D 지도 시간대 슬라이더 컨트롤러 및 단계 배지 |
| 운영자 (`operator.js` · `drawHeat`) | `.heat`, `.tick`, `.table-scroll` | 5분 단위 도로별 속도 히트맵 (첫 열 도로명 `position: sticky`) |
| 운영자 (`operator.js` · `drawGates`) | `.share-cell`, `.share-bar`, `.nowrap` | 출구별 차량 비중 미니 바 및 출구명 줄바꿈 방지 |
| 운영자 (`live_exit.js`) | `.le-head`, `.le-pick`, `.le-status`, `.le-chart`, `.le-field`, `.le-err` (+ 기존 `.kpis`/`.kpi`, `.chip.good`/`.warn`/`.bad`, `button.ghost` 재사용) | 공연 당일 실시간 입출차 감지 카드(11/20 이름 바꿈). 상태는 기호+글자(`○ 감시 중`, `▲ 확인 중`, `▼ 출차 시작 감지`)로 함께 표시. 그래프 세로선(이 카드와 '공연 후 출차 곡선' 공통): 예상 = 점선 + 옅은 띠(입차 `--warn`/`--warn-bg`, 출차 `--accent`/`--accent-soft`), 실제 = 초록 실선(`--good-ink`) + `●` 글자. 선 글자는 흰 테두리(`paint-order="stroke"`)로 겹쳐도 읽히게, 곡선 이름은 곡선 옆 글자로(색만으로 구분하지 않음) |
| 운영자 (`audience_car.js`) | `.ac-grid`, `.ac-pick`, `.ac-result` (`.is-match`), `.ac-result-head`, `.ac-num`, `.ac-bar` (+ `.le-status`, `.le-chart`, `.legend`, `table.list` 재사용) | 관객 성향으로 본 자가용 예상 카드. 판단은 기호+글자(`● 뚜렷함`, `▲ 덜 뚜렷함`, `○ 뚜렷하지 않음`), 산점도는 주말 ●·금요일 ▲ 모양으로도 구분 |
| 운영자 (`operator.js` · `drawBrief`) | `.brief-header-bar`, `.brief`, `.print-me`, `.no-print` | 유관기관 공유용 A4 한 장 인쇄 양식 |

---

## 4. 절대 지우면 안 되는 HTML `id` · `data-*` 목록

`scripts/check_all.py`가 검사하는 필수 식별자다(없어지면 ❌, PR 자동 합치기도 멈춘다). 새로 꼭 필요한 `id`가 생기면 여기에 추가한다.

- **`web/index.html`**:
  - `id`: `date`, `event`, `eventInfo`, `mode`, `transitSection`, `stGpsBtn`, `stGpsNote`, `stations`, `stationTip`, `walkSrc`, `exitGate`, `egGpsBtn`, `egGpsNote`, `egZone`, `egWay`, `egResult`, `egWx`, `egWeather`, `egSrc`, `visitorCard`, `vfStatus`, `vfChart`, `vfNote`, `vfSrc`, `mapGpsBtn`, `mapGpsNote`, `map3d`, `legend3d`, `flat`, `map`, `legend`, `roadNote`
  - `data-*`: `#mode` 내부 버튼의 `data-v="car"`, `data-v="transit"` / `#egZone` 버튼의 `data-g` / `#egWay` 버튼의 `data-w` / `.gps-bar` 내부 끄기 버튼의 `data-gps-off`
- (운영자 화면 `web/operator.html`은 2026-11-21 사이트에서 내려 `archive/operator/`에 보관 — 다시 살리면 그때의 id 목록은 git 기록 참고)

---

## 5. 화면 문구 · 공모전 표현 체크리스트

1. **혼잡 분산 프레이밍**: 공원 주차장을 *"피하는/회피하는"* 표현을 쓰지 않고 **"출구 혼잡을 덜어 주는 분산 주차"**처럼 분산·완화 관점으로 적는다.
2. **기관 권한 명시**: 운영자 요약표(`#brief`) 하단에 *"실제 현장 배치와 교통 통제는 각 기관이 판단·결정합니다"* 취지 문구를 유지한다.
3. **데이터 정직성**:
   - 실시간 주차는 반드시 `parkActual()` 보정값과 장기 주차 차감 근거를 함께 표시한다.
   - 환승주차 `'공연장에서 나올 때'` 탭에는 `'공연장 나오기 N분'`을 넣지 않는다(`docs/context.md` 합의 사항).
   - 비교 표현은 `'같은 시간대 평일 평균'`처럼 비교 기준을 명시한다.
4. **이모티콘 미사용**: 버튼·경로 칩·안내 문구에 그림 이모티콘(`🚗`, `🚶`, `🚇`, `💡`, `🖨` 등)을 넣지 않는다. 접근성 상태 기호(`●`/`▲`/`■`/`○`/`—`)와 3D 지도 재생 기호(`▶`/`❚❚`)만 사용한다.

- 2026-11-20: 운영자 '공연 후 출차 곡선' 카드와 '주변 도로 (3D)' 카드는 `.grid2`(두 칸)에서 빼서 한 줄 전체 폭 카드로 둔다(실시간 입출차 감지 카드와 같은 폭). 출차 곡선 그래프 viewBox는 760×280.
- 2026-11-20: `web/data-guide.html`(결과 데이터 설명서)은 JS 없는 정적 페이지. 운영자 화면과 같은 머리(`header.top`)·`card`·`table.list`를 쓴다. 운영자 '데이터 점검 결과' 카드(`data_quality.js`)는 새 class 없이 `.le-status`, `.chip.warn`, `table.list`, `.subhead` 재사용, 비고는 기호+글자(`●`/`▲`).
- 2026-11-24: 기존 '방문객 혼잡 예측·분산 안내' 카드(`#visitorCard`, `visitor.js`)를 **'주로 공연장에 도착하는 시간'** 세로 막대그래프(`.arr-chart-*`)로 개편(1단계에서 고른 공연의 시작 시각·요일 유형에 연동, 막대마다 `●`/`▲`/`■` + `%` 표시).
