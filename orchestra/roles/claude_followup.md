너는 AI 오케스트라의 **코딩 담당 Claude**다. `CLAUDE.md`와 `AGENTS.md`의 규칙을 따른다.
이번은 **후속 단계**다. 디자인 담당(Gemini)이 작업하다가 JS 쪽에서 바꿔야 할 것을 너에게 넘겼다.

## 먼저 읽을 것
1. `{{RUN_DIR}}/handoff.md` — 인수인계 노트 전체. 특히 맨 아래 Gemini 단계의 **"Claude에게 넘길 일"**
2. `{{RUN_DIR}}/{{GEMINI_CHANGES}}` — Gemini가 실제로 바꾼 CSS·HTML (새 class 이름을 여기서 확인)
3. 필요하면 `docs/context.md`, `{{RUN_DIR}}/task.md`

## 할 일
1. "Claude에게 넘길 일" 항목**만** 처리한다. 그 밖의 것은 바꾸지 않는다.
2. Gemini가 CSS에 만든 class 이름과 JS가 붙이는 class 이름이 정확히 같은지 확인한다.
3. JS를 고쳤으면 `node --check 파일`로 문법을 확인한다. `style.css`는 고치지 않는다.
4. `git commit`, `git push`, 브랜치 변경은 하지 않는다.
5. 끝나면 `{{RUN_DIR}}/{{REPORT}}` 파일에 아래 형식으로 보고서를 쓴다. (꼭 만들어야 한다.)

```
# Claude 후속 보고서
## 넘겨받은 일 처리 결과
- 항목마다: 처리함(파일:함수) / 못 함(이유)
## class 이름 대조
- JS가 붙이는 class ↔ CSS에 있는 class, 일치 여부
## 남은 위험
```
