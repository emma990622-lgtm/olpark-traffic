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

## AI 오케스트라 역할
| 역할 | 담당 | 고치는 파일 | 고치면 안 되는 파일 |
|---|---|---|---|
| Claude | 코딩 | `web/assets/*.js`, `api/`, `scripts/`, `web/data/`, HTML 구조(요소 추가, `id`, `data-*`), `docs/`(design.md 제외), README | `web/assets/style.css`, `docs/design.md`, 규칙 파일 |
| Gemini (Antigravity) | 웹디자인 | `web/assets/*.css`, `web/*.html`(class, 감싸는 요소, 화면 문구), `web/assets/img/`, `web/assets/fonts/`, `docs/design.md` | JS·api·scripts·data, HTML의 `id`·`data-*` 속성 |
| Codex | 최종 검수 | 없음 (읽기만) | 전부 |

- 오케스트라 실행 중에는 범위를 벗어난 변경을 지휘 스크립트(`orchestra/orchestra.py`)가 자동으로 되돌린다.
- 오케스트라 실행 중에는 커밋·push·브랜치 변경을 스크립트가 한다. AI는 하지 않는다.
- 다른 역할이 할 일은 직접 하지 말고 보고서의 "넘길 일"에 적는다.

## 꼭 지킬 것
- **인증키는 코드·화면·문서에 적지 않는다.** 키는 Vercel 환경변수(`SEOUL_API_KEY`, `NAVER_KEY_ID`, `NAVER_KEY`)와 GitHub Secrets(`TMAP_APP_KEY`)에만 있다. `set_keys.bat`, `delete_keys.bat`은 건드리지 않는다.
- `data/raw/` 원본은 수정하지 않는다.
- 화면에 숫자·예측을 보일 때는 출처와 기준(기간·방법)을 같이 보인다. 데이터가 없으면 지어내지 말고 "아직 없음"으로 표시한다. (심사에서 데이터 신뢰가 중요하다.)
- 화면 문구는 쉬운 한국어. 관객 화면은 "~해요"체. 전문용어는 풀어 쓴다.
- 관객 화면은 모바일(360px 폭)부터, 운영자 화면은 PC(1280px)부터 맞춘다.
- 접근성: 색만으로 상태를 구분하지 않는다(글자·아이콘 함께), 글자 대비 4.5:1 이상, 누르는 곳은 44px 이상.
- 로컬 실행은 `web\run_web.bat`(http://127.0.0.1:8000). 로컬에서는 `/api`가 동작하지 않으므로 `/api` 호출이 실패해도 화면이 깨지지 않아야 한다.
- 보고서와 답변은 한국어로 쓴다.
