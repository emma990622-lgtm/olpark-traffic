@AGENTS.md

# Claude: 코딩 담당

- 기능 구현, 버그 수정, 데이터 연결, `api/` 서버 함수, `scripts/` 데이터 가공을 맡는다.
- 디자인(색·간격·글꼴·모양 꾸미기)은 하지 않는다. `web/assets/style.css`는 Gemini 담당이다.
- 새 화면 요소를 만들면 뜻이 드러나는 class 이름을 붙인다(예: `.lot-card`, `.lot-card.is-full`, `.badge-busy`). 꾸미기는 보고서의 "Gemini에게 넘길 디자인 일"에 적는다.
- JS가 `innerHTML`로 만드는 HTML의 class 이름은 Gemini가 바꿀 수 없다. 그래서 새 class를 만들거나 바꾸면 반드시 보고서에 목록으로 적는다.
- 기존 동작을 유지한다. 요청 없는 큰 구조 변경은 하지 않는다.
- JS를 고친 뒤에는 `node --check 파일`로 문법을 확인한다.
- 오케스트라 밖에서 사용자가 직접 Claude를 쓸 때는 사용자가 요청하면 커밋해도 된다.
- 오케스트라 밖에서 사용자가 Claude에게 직접 요청할 때는 디자인(`web/assets/style.css`, HTML의 class·감싸는 요소·화면 문구)도 고쳐도 된다. 이때 정한 색·간격·컴포넌트 규칙은 `docs/design.md`에 짧게 적어서 Gemini가 다음 작업에서 같은 규칙을 따르게 한다.
