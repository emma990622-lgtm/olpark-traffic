# AI 오케스트라 사용 안내

세 AI가 순서대로 일하고, 마지막 결정(Merge)은 사람이 합니다.

```
작업 요청서(orchestra/tasks/*.md)
  → ① Claude: 코딩      (JS·api·scripts·데이터, HTML 구조)
  → ② Gemini: 웹디자인   (CSS, HTML class·문구, docs/design.md)   ← Antigravity CLI(agy)
  → ③ 자동 점검         (JS 문법, JSON, 없는 파일·id, 인증키 노출)
  → ④ Codex: 최종 검수   (읽기만 함, 판정: 통과/수정필요)
  → ⑤ GitHub에 브랜치 올리기 + PR 만들기 → Vercel 미리보기 주소 자동 생성
  → 사람: 미리보기 확인 후 Merge (그때 실제 사이트에 반영)
```

- 작업마다 `orchestra/날짜-시각` 브랜치가 새로 생겨요. **main과 실제 사이트는 Merge 전까지 그대로**예요.
- 각 AI는 자기 담당 파일만 고칠 수 있어요. 범위 밖 변경은 스크립트가 자동으로 되돌리고 기록을 남겨요 (`AGENTS.md` 표 참고).
- Gemini가 HTML의 `id`·`data-*`를 지우면(= JS가 화면을 못 찾게 되면) 그 HTML 변경은 되돌려요.
- 각 AI의 보고서와 Codex 의견은 PR 본문에 모두 들어가요.

## 처음 한 번 준비 (윈도우)

1. 프로그램 설치 — PowerShell에서:
   ```
   winget install Git.Git Python.Python.3.12 OpenJS.NodeJS.LTS GitHub.cli
   npm install -g @anthropic-ai/claude-code @openai/codex
   irm https://antigravity.google/cli/install.ps1 | iex
   ```
   (이미 있는 건 건너뛰어도 돼요. Claude Code는 공식 설치 프로그램으로 깔아도 됩니다.)
2. 로그인 — 각각 한 번씩 실행해서 구독 계정으로 로그인:
   - `claude` (Claude Pro/Max 계정)
   - `agy` (Google AI Pro/Ultra 또는 Gemini 계정)
   - `codex` (ChatGPT Plus/Pro 계정, "Sign in with ChatGPT")
   - `gh auth login` (GitHub, 선택 — 있으면 PR을 자동으로 만들어요)
3. GitHub Desktop의 olpark-traffic 폴더에서 `orchestra.bat` 더블클릭 → **7) 환경 점검** → 모두 ✅ 인지 확인.

> `agy --version`을 쳤는데 Antigravity 데스크톱 앱이 열리면, 데스크톱 앱과 CLI의 명령 이름이 겹친 것이에요. Antigravity CLI 설치 안내의 "agy 명령 충돌 해결"을 따르거나, `orchestra/orchestra.py` 위쪽 `GEMINI_CMD`의 `"agy"`를 CLI 실행 파일의 전체 경로로 바꾸세요.

## 매번 하는 일

1. `orchestra/tasks/_양식.md`를 복사해서 작업 요청서를 씁니다. (예시: `예시_관객화면_첫인상.md`)
2. GitHub Desktop에 **저장 안 한 변경이 없는지** 확인 (작업 요청서는 괜찮아요).
3. `orchestra.bat` 더블클릭 → **1) 새 작업** → 요청서 번호 선택.
   - 디자인만 손볼 땐 2), 기능만 고칠 땐 3).
4. 끝나면 GitHub의 PR에서
   - Codex 판정과 의견 확인
   - Vercel 댓글의 **Preview** 링크로 바뀐 화면 확인 (휴대폰으로도)
5. 결정
   - 괜찮다 → GitHub에서 **Merge** → 실제 사이트 반영
   - 고칠 게 있다 → GitHub Desktop에서 그 `orchestra/...` 브랜치로 바꾼 뒤 `orchestra.bat` → **4) 검수 의견 반영**
     (Claude·Gemini가 Codex 의견 중 자기 담당 항목을 고치고, Codex가 다시 검수해서 PR에 댓글로 남겨요)
   - 버리고 싶다 → PR을 Close (main은 처음부터 안 바뀌었어요)
6. 다음 작업 전에 GitHub Desktop에서 **main으로 돌아와 Fetch/Pull** 하세요.

## 메뉴

| 번호 | 하는 일 |
|---|---|
| 1 | 새 작업: Claude → Gemini → 점검 → Codex → PR |
| 2 | 새 작업, 디자인만: Gemini → 점검 → Codex → PR |
| 3 | 새 작업, 코딩만: Claude → 점검 → Codex → PR |
| 4 | 검수 의견 반영 (지금 orchestra 브랜치에서 한 회차 더) |
| 5 | 다시 검수만 (사람이 직접 고친 뒤 Codex에게 다시 보이기) |
| 6 | 멈춘 곳부터 이어서 (로그인 만료·인터넷 끊김 등으로 멈췄을 때) |
| 7 | 환경 점검 |

명령줄로도 됩니다: `python orchestra\orchestra.py new orchestra\tasks\파일.md --design-only --no-push`

## 파일

| 파일 | 내용 |
|---|---|
| `AGENTS.md` | 세 AI 공통 규칙 + 역할 범위 (Codex·Antigravity가 자동으로 읽음) |
| `CLAUDE.md` | Claude 코딩 규칙 (AGENTS.md를 불러옴) |
| `GEMINI.md` | Gemini 디자인 규칙 (Antigravity가 자동으로 읽음) |
| `.claude/settings.json` | 무인 실행 때 Claude에게 허용한 명령 (파일 수정, git 읽기, node 문법 검사) |
| `orchestra/roles/*.md` | 단계별 지시서 틀 |
| `orchestra/tasks/` | 작업 요청서 (사람이 씀) |
| `orchestra/runs/` | 실행 기록 — 지시서, 보고서, 점검 결과, 변경 내용. **이 컴퓨터에만** 남아요 (git 제외) |

## 비용·권한 메모
- 세 AI 모두 각자 구독 계정의 사용량으로 돌아요. 별도 API 키가 필요 없어요. 한 작업에 구독 한도를 꽤 쓸 수 있으니, 요청서는 작게 나누는 게 좋아요.
- Gemini(agy)는 무인 실행을 위해 `--dangerously-skip-permissions`로 돌아요(파일 수정·명령 실행을 묻지 않음). 대신 작업은 별도 브랜치에서만 하고, 범위 밖 변경은 스크립트가 되돌려요.
- Codex는 `--sandbox read-only`라 파일을 고칠 수 없어요.
- 모델을 바꾸려면 `orchestra/orchestra.py` 위쪽의 `CLAUDE_CMD` / `GEMINI_CMD` / `CODEX_CMD`에 `--model ...` 옵션을 더하세요.
