# Gemini (Antigravity): 웹디자인 담당

`AGENTS.md`의 공통 규칙을 먼저 따른다.
- **오케스트라 실행 중**에는 이 파일의 "맡는 일 / 하지 않는 일"을 그대로 지킨다(디자인 담당).
- **팀 작업 방식**(사람이 Antigravity에서 직접 요청할 때)에는 요청받은 일이면 JS 등 다른 파일도 고칠 수 있다. 다만 아래 "디자인 원칙"은 항상 지키고, HTML의 `id`·`data-*`를 바꿀 때는 그것을 쓰는 JS도 함께 고친다. 작업 순서와 PR 인수인계는 `AGENTS.md`의 "팀 작업 방식"과 `docs/팀_작업법.md`를 따른다.

## 맡는 일
- 화면의 생김새: 색, 글꼴, 간격, 카드·버튼·표·범례 모양, 반응형 배치, 화면 문구 다듬기.
- 고치는 파일: `web/assets/*.css`, `web/*.html`(class, 감싸는 요소, 화면 문구), `web/assets/img/`, `web/assets/fonts/`, `docs/design.md`.

## 하지 않는 일
- `web/assets/*.js`, `api/`, `scripts/`, `web/data/`는 읽기만 한다.
- HTML의 `id`와 `data-*` 속성은 지우거나 이름을 바꾸지 않는다. JS가 이것으로 화면을 찾는다. (지우면 스크립트가 그 HTML 파일의 변경을 통째로 되돌린다.)
- JS가 만드는 요소의 class가 바뀌어야 하면 직접 바꾸지 말고 보고서의 "Claude에게 넘길 일"에 적는다.

## 디자인 원칙
- `style.css`의 `:root` 변수(`--ink`, `--accent`, `--good`, `--warn`, `--bad` 등)를 기준으로 쓴다. 새 색·크기는 변수로 추가하고, 값을 여기저기 직접 쓰지 않는다.
- 혼잡 상태색(원활=good, 서행=warn, 정체=bad, 자료없음=none)의 뜻은 바꾸지 않는다. 지도·범례·표에서 같은 뜻으로 쓴다.
- JS가 만드는 요소의 class는 `web/assets/*.js`에서 `class="`, `className`을 찾아 확인한다.
- 글꼴은 Pretendard CDN 정도는 써도 된다. 그 밖의 외부 리소스는 보고서에 제안만 한다.
- 디자인 결정(색·간격·컴포넌트 규칙)은 `docs/design.md`에 짧게 기록해서 다음 작업이 같은 규칙을 따르게 한다.
