# Antigravity (Gemini)

`AGENTS.md`의 공통 규칙과 작업 순서를 그대로 따른다. Gemini만 따로 맡는 역할은 없다(기능·디자인·데이터·문서 모두 가능).
- 화면을 고칠 때는 `docs/design.md`(CSS 변수, JS↔CSS 클래스 대조표, 지우면 안 되는 `id`)를 먼저 본다.
- class·`id` 이름을 바꾸면 그것을 쓰는 JS도 같은 작업에서 함께 고친다.
- 작업을 마치면 `python scripts/check_all.py`로 점검하고, `docs/handoff/`에 인수인계 노트를 새 파일로 남긴다.
