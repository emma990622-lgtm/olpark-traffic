# AGENTS.md — olpark-traffic 공통 규칙

모든 AI가 읽는 파일이다. Codex·Antigravity(Gemini)는 자동으로 읽고, Claude는 `CLAUDE.md`를 통해 읽는다.

## 프로젝트
- KSPO DOME·올림픽공원 공연 전후 주차·교통 혼잡 안내 웹앱. 한국체육산업개발 2026 공공데이터 활용 경진대회 출품용.
- 화면 두 개: 관객용 `web/index.html`(모바일), 운영자·기관용 `web/operator.html`(PC).
- 배포: Vercel. `main`에 반영되면 https://olpark-traffic.vercel.app 이 바뀐다. 다른 브랜치를 push하면 Vercel이 미리보기 주소를 따로 만든다.
- 구조
  - `web/` 정적 화면: `*.html`, `assets/*.js`(기능), `assets/style.css`(디자인), `data/*.json`(가공 데이터)
  - `api/*.js` Vercel 서버 함수 (CommonJS, Node 18+)
  - `scripts/*.py` 데이터 가공, `data/raw` 원본, `data/processed` 가공 결과
- 빌드 도구·프레임워크 없음. 순수 HTML/CSS/JS + MapLibre GL 4.7.1(unpkg). 새 라이브러리나 빌드 단계는 추가하지 않는다(필요하면 보고서에 제안만).

## 작업 전에 먼저 읽을 것
- `docs/context.md`: 프로젝트 배경, 화면·데이터 파일의 뜻, 데이터 함정, 이미 정한 것, 결정 기록. 다음 작업에도 영향을 주는 결정을 하면 Claude가 "결정 기록"에 한 줄 추가한다.
- 오케스트라 실행 중에는 `orchestra/runs/<id>/handoff.md`(인수인계 노트)도 먼저 읽는다. 앞 단계의 요청 해석·결정·넘긴 일·실제로 바뀐 파일이 순서대로 들어 있다. 다른 담당은 이 대화를 볼 수 없으니, 알게 된 것과 정한 것은 모두 보고서에 남긴다.

## 팀 작업 방식 (GitHub, 기본)
두 사람이 각자 자기 AI(Claude Code, Antigravity, Codex 등)로 작업하고 GitHub PR로 인수인계한다. 자세한 순서는 `docs/팀_작업법.md`.
- 할 일은 GitHub Issue에 있다. 작업 전에 해당 Issue와 `docs/context.md`를 읽는다.
- `main`에 직접 커밋하지 않는다. `main` 최신을 받은 뒤 새 브랜치(예: `minji/parking-full-badge`)에서 작업한다.
- 한 PR에는 한 가지 일만. 작게 자주 올린다(같은 파일, 특히 `style.css`를 둘이 오래 붙잡고 있으면 충돌이 난다).
- 작업을 마치면 PR 설명을 `.github/pull_request_template.md` 양식으로 채운다(요청 해석, 바꾼 것, 결정과 이유, 넘길 일, 건드리면 안 되는 것). 다른 사람과 그 사람의 AI는 이 대화를 볼 수 없다.
- 오래 지킬 결정은 `docs/context.md` "결정 기록"에, 디자인 규칙은 `docs/design.md`에 한 줄 적는다(팀 작업 방식에서는 누구의 AI든 적어도 된다).
- 이번에 못 한 일은 PR의 "넘길 일"과 새 Issue로 남긴다.
- 커밋·push·PR 만들기는 사람이 요청했을 때만 한다. Merge는 사람이 한다.
- 아래 "AI 오케스트라 역할"의 파일 제한은 오케스트라 실행 중에만 적용된다. 팀 작업에서는 누구의 AI든 모든 파일을 고칠 수 있지만, 디자인은 `docs/design.md`와 `style.css`의 변수 규칙을, 기능은 기존 동작 유지를 지킨다.

## Review guidelines
(GitHub의 Codex 자동 리뷰가 읽는 기준이다. 한국어로 리뷰한다.)
- PR 설명의 인수인계 칸(요청 해석, 결정과 이유, 넘길 일, 건드리면 안 되는 것)이 비어 있으면 지적한다.
- JS가 `innerHTML`·`className`으로 붙이는 class와 `style.css`의 class 이름이 일치하는지 본다.
- HTML의 `id`·`data-*`를 지우거나 바꿔서 JS가 요소를 못 찾는 경우를 P1로 본다.
- `/api` 실패나 빈 데이터에서 화면이 깨지는 경우, 360px(관객)·1280px(운영자)에서 깨지는 경우를 지적한다.
- 출처·기준 없이 숫자를 보이거나, 데이터가 없는데 숫자를 지어낸 경우를 P1로 본다. `docs/context.md`의 데이터 함정(부풀려진 parking_sum 등)을 무시한 표시도 지적한다.
- 인증키·비밀값이 코드·문서에 들어가면 P0. (`apiKey=PARKING21803504`는 기관 공개값이라 예외)
- 색만으로 상태를 구분하거나, 글자 대비 4.5:1 미만, 누르는 곳 44px 미만이면 지적한다.

## AI 오케스트라 역할
| 역할 | 담당 | 고치는 파일 | 고치면 안 되는 파일 |
|---|---|---|---|
| Claude | 코딩 | `web/assets/*.js`, `api/`, `scripts/`, `web/data/`, HTML 구조(요소 추가, `id`, `data-*`), `docs/`(design.md 제외), README | `web/assets/style.css`, `docs/design.md`, 규칙 파일 |
| Gemini (Antigravity) | 웹디자인 | `web/assets/*.css`, `web/*.html`(class, 감싸는 요소, 화면 문구), `web/assets/img/`, `web/assets/fonts/`, `docs/design.md` | JS·api·scripts·data, HTML의 `id`·`data-*` 속성 |
| Codex | 최종 검수 | 없음 (읽기만) | 전부 |

- 위 역할 범위는 오케스트라 실행 중에 적용한다. 오케스트라 밖에서 사용자가 Claude에게 직접 요청하면 Claude가 디자인도 고칠 수 있다(`CLAUDE.md` 참고).
- 오케스트라 실행 중에는 범위를 벗어난 변경을 지휘 스크립트(`orchestra/orchestra.py`)가 자동으로 되돌린다.
- 오케스트라 실행 중에는 커밋·push·브랜치 변경을 스크립트가 한다. AI는 하지 않는다.
- 다른 역할이 할 일은 직접 하지 말고 보고서의 "넘길 일"에 적는다.

## 꼭 지킬 것
- **인증키는 코드·화면·문서에 적지 않는다.** 키는 아래 세 곳에만 있다. 키 값을 찾거나 출력하지 말고, 필요하면 아래 이름으로 환경변수를 읽는다.
  - Vercel 환경변수(`api/*.js`가 씀): `SEOUL_API_KEY`(서울시 열린데이터광장), `VWORLD_KEY`·`VWORLD_DOMAIN`(브이월드 건물), `NAVER_KEY_ID`·`NAVER_KEY`(네이버 길찾기, 선택), `TMAP_APP_KEY`(선택: `/api/drivetime` 실시간 운전시간, 없으면 501)
  - GitHub Secrets: 이 저장소의 `TMAP_APP_KEY`(도로 자료 검증 자동 실행, `.github/workflows/verify_roads.yml`), 수집기 저장소 olpark-collector의 `SEOUL_API_KEY`(공연일 자동 수집)
  - 사용자 컴퓨터의 윈도우 사용자 환경변수(`set_keys.bat`으로 저장, `scripts/*.py`가 씀): `TMAP_APP_KEY`, `KCISA_KEY`(문화공공데이터광장 2025 입출차정보), `DATAGO_KEY`(공공데이터포털, 주차장 혼잡도 정보)
  - 예외: 한국체육산업개발 실시간 주차 API 주소의 `apiKey=PARKING21803504`는 기관이 누구나 쓰도록 공개한 값이라 코드(`api/parking.js` 등)에 있어도 된다. 검수에서 인증키 노출로 보지 않는다.
  - `set_keys.bat`, `delete_keys.bat`은 건드리지 않는다.
- `data/raw/` 원본은 수정하지 않는다.
- 화면에 숫자·예측을 보일 때는 출처와 기준(기간·방법)을 같이 보인다. 데이터가 없으면 지어내지 말고 "아직 없음"으로 표시한다. (심사에서 데이터 신뢰가 중요하다.)
- 화면 문구는 쉬운 한국어. 관객 화면은 "~해요"체. 전문용어는 풀어 쓴다.
- 관객 화면은 모바일(360px 폭)부터, 운영자 화면은 PC(1280px)부터 맞춘다.
- 접근성: 색만으로 상태를 구분하지 않는다(글자·아이콘 함께), 글자 대비 4.5:1 이상, 누르는 곳은 44px 이상.
- 로컬 실행은 `web\run_web.bat`(http://127.0.0.1:8000). 로컬에서는 `/api`가 동작하지 않으므로 `/api` 호출이 실패해도 화면이 깨지지 않아야 한다.
- 보고서와 답변은 한국어로 쓴다.
