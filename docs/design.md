# 디자인 규칙 및 JS↔CSS 계약서 (`docs/design.md`)

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
| 공통 (`common.js` · `levelOf`) | `.chip.good`, `.chip.warn`, `.chip.bad`, `.chip.accent` | 혼잡 수준(`평소`/`주의`/`집중`) 및 강조 배지 (`lv.sym` 기호 포함) |
| 공통 (`common.js` · `lineBadgesHTML`) | `.line-badge`, `.l2`, `.l5`, `.l8`, `.l9` | 호선 번호별 색상 알약 배지 |
| 공통/3D지도 (`common.js`, `map3d.js`) | `.legend`, `.m3d`, `.m3d.lot`, `.m3d.st`, `.m3d.venue`, `.m3d.dome` | 범례 및 3D 지도 HTML 캡슐 마커 (`map3d.failed` 시 평면 지도 자동 펼침) |
| 관객 (`audience.js` · `render`) | `.event-summary`, `.event-head`, `.stat-strip`, `.stat-item` (`.sk`, `.sv`) | Step 1 선택 공연 제목·배지·3열 핵심 시간/좌석 요약 |
| 관객 (`audience.js` · `renderCar`) | `.reco`, `.reco.is-caution`, `.reco.is-normal`, `.reco-kicker` | Step 3 상단 오늘의 주차 추천 배너 (혼잡도별 배경 분기) |
| 관객 (`audience.js` · `renderCar`) | `.opt`, `.opt.recommended`, `.opt-top`, `.kind`, `.reco-pill` | 주차 선택지 카드 3종 및 추천 강조 테두리/배지 |
| 관객 (`audience.js` · `renderCar`) | `.opt-metrics`, `.metric-card` (`.mk`, `.mv`, `.ms`) | 각 주차 선택지 상단 3열 핵심 지표 요약 |
| 관객 (`audience.js` · `renderCar`) | `.live-lot-box`, `.live-lot-head`, `.live-badge`, `.live-lot-nums`, `.free-num`, `.occ-bar` (`.is-warn`, `.is-bad`) | 공원 주차장 실시간 보정 대수(`parkActual`) 및 점유율 게이지 바 |
| 관객 (`audience.js` · `transferGo`, `transferOutHTML`) | `.tlot-list`, `.tlot`, `.tlot.skip`, `.tlot-head`, `.tname`, `.tlot-meta`, `.tlot-route-desc`, `.ttotal`, `.route-steps`, `.step-pill` (`.is-subway`, `.is-crowd`), `.step-arrow`, `.tlot-compare`, `.warnline` | 환승주차 카드, 단계별 이동 알약 칩, 운전/출차 비교 영역, 비추천 경고 |
| 운영자 (`operator.js` · `roadCheck`) | `.verify-box`, `.verify-title`, `.verify-list` | TOPIS·TMAP 실시간 도로 자료 교차검증 결과 박스 (`<ol>` 자동 번호) |
| 운영자 (`operator.js` · `render`) | `.kpis`, `.kpi` (`.is-bad`, `.is-warn`, `.is-good`), `.v`, `.l` | 상단 핵심 대응 지표 4종 카드 |
| 운영자 (`operator.js` · `showTime`) | `.timectl`, `.trow`, `.tlabel`, `.phase` | 3D 지도 시간대 슬라이더 컨트롤러 및 단계 배지 |
| 운영자 (`operator.js` · `drawHeat`) | `.heat`, `.tick`, `.table-scroll` | 5분 단위 도로별 속도 히트맵 (첫 열 도로명 `position: sticky`) |
| 운영자 (`operator.js` · `drawGates`) | `.share-cell`, `.share-bar`, `.nowrap` | 출구별 차량 비중 미니 바 및 출구명 줄바꿈 방지 |
| 운영자 (`live_exit.js`) | `.le-head`, `.le-pick`, `.le-status`, `.le-chart`, `.le-field`, `.le-err` (+ 기존 `.kpis`/`.kpi`, `.chip.good`/`.warn`/`.bad`, `button.ghost` 재사용) | 공연 당일 실시간 입출차 감지 카드(11/20 이름 바꿈). 상태는 기호+글자(`○ 감시 중`, `▲ 확인 중`, `▼ 출차 시작 감지`)로 함께 표시. 그래프 세로선(이 카드와 '공연 후 출차 곡선' 공통): 예상 = 점선 + 옅은 띠(입차 `--warn`/`--warn-bg`, 출차 `--accent`/`--accent-soft`), 실제 = 초록 실선(`--good-ink`) + `●` 글자. 선 글자는 흰 테두리(`paint-order="stroke"`)로 겹쳐도 읽히게, 곡선 이름은 곡선 옆 글자로(색만으로 구분하지 않음) |
| 운영자 (`audience_car.js`) | `.ac-grid`, `.ac-pick`, `.ac-result` (`.is-match`), `.ac-result-head`, `.ac-num`, `.ac-bar` (+ `.le-status`, `.le-chart`, `.legend`, `table.list` 재사용) | 관객 성향으로 본 자가용 예상 카드. 판단은 기호+글자(`● 뚜렷함`, `▲ 덜 뚜렷함`, `○ 뚜렷하지 않음`), 산점도는 주말 ●·금요일 ▲ 모양으로도 구분 |
| 관객 (`audience.js` · `renderCar`) | 기존 `dl` 안 `dt`/`dd` 한 줄 추가('차로 오는 관객') | 같은 가수 지난 관객 구성이 있고 `audience_car.json`의 `meaningful`이 참일 때만 보임 |
| 운영자 (`operator.js` · `drawBrief`) | `.brief-header-bar`, `.brief`, `.print-me`, `.no-print` | 유관기관 공유용 A4 한 장 인쇄 양식 |

---

## 4. 절대 지우면 안 되는 HTML `id` · `data-*` 목록

`scripts/check_all.py`가 검사하는 필수 식별자다(없어지면 ❌, PR 자동 합치기도 멈춘다). 새로 꼭 필요한 `id`가 생기면 여기에 추가한다.

- **`web/index.html`**:
  - `id`: `date`, `event`, `eventInfo`, `mode`, `carSection`, `reco`, `options`, `walkSrc`, `subwayNote`, `transitSection`, `stations`, `stationTip`, `map3d`, `legend3d`, `flat`, `map`, `legend`, `roadNote`
  - `data-*`: `#mode` 내부 버튼의 `data-v="car"`, `data-v="transit"` / `#options` 내부 환승 탭 버튼의 `data-tmode="go"`, `data-tmode="out"`
- **`web/operator.html`**:
  - `id`: `date`, `showMin`, `events`, `kpis`, `chart`, `chartNote`, `map3d`, `tPlay`, `tSlider`, `tNow`, `tLabel`, `tInfo`, `legend3d`, `flat`, `map`, `legend`, `roadNote`, `roadCheck`, `roadDayNote`, `roadChart`, `roadChartLegend`, `heat`, `slowTop`, `gateNote`, `gateTable`, `gateSrc`, `brief`, `liveExit`, `leReplay`, `leStatus`, `leKpis`, `leChart`, `leMark`, `leCsv`, `leMarks`, `leRec`, `leErr`, `leSrc`, `audCar`, `acStatus`, `acPreset`, `acDay`, `acPredict`, `acCoef`, `acChart`, `acLegend`, `acSrc`

---

## 5. 화면 문구 · 공모전 표현 체크리스트

1. **혼잡 분산 프레이밍**: 공원 주차장을 *"피하는/회피하는"* 표현을 쓰지 않고 **"출구 혼잡을 덜어 주는 분산 주차"**처럼 분산·완화 관점으로 적는다.
2. **기관 권한 명시**: 운영자 요약표(`#brief`) 하단에 *"실제 현장 배치와 교통 통제는 각 기관이 판단·결정합니다"* 취지 문구를 유지한다.
3. **데이터 정직성**:
   - 실시간 주차는 반드시 `parkActual()` 보정값과 장기 주차 차감 근거를 함께 표시한다.
   - 환승주차 `'공연장에서 나올 때'` 탭에는 `'공연장 나오기 N분'`을 넣지 않는다(`docs/context.md` 합의 사항).
   - 비교 표현은 `'같은 시간대 평일 평균'`처럼 비교 기준을 명시한다.
4. **이모티콘 미사용**: 버튼·경로 칩·안내 문구에 그림 이모티콘(`🚗`, `🚶`, `🚇`, `💡`, `🖨` 등)을 넣지 않는다. 접근성 상태 기호(`●`/`▲`/`■`/`○`/`—`)와 3D 지도 재생 기호(`▶`/`❚❚`)만 사용한다.
