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
   irm https://claude.ai/install.ps1 | iex
   irm https://antigravity.google/cli/install.ps1 | iex
   powershell -ExecutionPolicy ByPass -c "irm https://chatgpt.com/codex/install.ps1 | iex"
   winget install GitHub.cli
   ```
   (공식 설치 프로그램이라 Node.js가 없어도 돼요. 이미 있는 건 건너뛰어도 돼요. 설치 후 PowerShell 창을 닫고 새로 여세요.
   Git·Python이 없을 때만 `winget install Git.Git Python.Python.3.12`. Node.js는 선택 — 있으면 JS 문법 검사를 해요.)
2. 로그인 — 각각 한 번씩 실행해서 구독 계정으로 로그인:
   - `claude` (Claude Pro/Max 계정)
   - `agy` (Google AI Pro/Ultra 또는 Gemini 계정)
   - `codex` (ChatGPT Plus/Pro 계정, "Sign in with ChatGPT")
   - `gh auth login` (GitHub, 선택 — 있으면 PR을 자동으로 만들어요)
3. GitHub Desktop의 olpark-traffic 폴더에서 `orchestra.bat` 더블클릭 → **7) 환경 점검** → 모두 ✅ 인지 확인.

> `agy`를 쳤는데 Antigravity 데스크톱 앱이 열리면, 데스크톱 앱과 CLI의 명령 이름이 겹친 것이에요. 로그인은 `& "$env:LOCALAPPDATA\agy\bin\agy.exe"`로 하세요. 오케스트라는 이 위치(`%LOCALAPPDATA%\agy\bin\agy.exe`)를 먼저 찾아 쓰므로 따로 고칠 필요가 없어요.

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

## 팀원과 같이 쓰기: 구글 시트 작업함

팀원은 프로그램을 깔 필요 없이 **구글 시트에 할 일을 한 줄씩** 적으면 돼요. 오케스트라를 돌리는 컴퓨터(AI 로그인이 된 한 대)에서 **8) 구글 시트 작업함 처리**를 고르면, '대기' 줄을 차례로 가져가 AI에게 맡기고 결과를 시트에 다시 적어요.

| 번호 | 요청자 | 할 일 | 자세한 내용 | 종류 | 상태 | 결과(PR) | Codex 판정 | 갱신 시각 |
|---|---|---|---|---|---|---|---|---|
| 1 | 민지 | 주차장 카드 글씨 키우기 | 360px 폭에서 '빈자리' 숫자가 작아서 안 보임 | 디자인 | (비워 둠) | (자동) | (자동) | (자동) |

- **종류**: 비워 두거나 `자동` → Claude 코딩 → Gemini 디자인 → Codex. `코딩` → Claude만. `디자인` → Gemini만.
- **상태**: 비워 두거나 `대기`면 가져가요 → `진행중` → `완료`(Codex 통과) / `수정필요` / `실패`. 사람이 `보류`로 바꾸면 안 가져가요.
- Codex가 `수정필요`라고 하면 한 번은 자동으로 고치고 다시 검수해요(`AUTO_FIX_ROUNDS`).
- 한 줄 = 작업 하나 = PR 하나. 작게 나눠 적을수록 잘 돼요. 할 일 칸이 PR 제목이 돼요.
- 결과(PR) 칸의 링크에서 Vercel 미리보기를 보고, 괜찮으면 Merge 해요.

**처음 한 번 연결 (시트 주인)**
1. 시트 메뉴 [확장 프로그램] → [Apps Script]에 `orchestra/sheet_inbox.gs` 내용을 붙여 넣고 저장해요.
2. 함수 `setup`을 실행 → 권한 허용 → 실행 로그의 **오케스트라 토큰**을 복사해요.
3. [배포] → [새 배포] → 웹 앱(실행: 나, 액세스: 모든 사용자) → **웹 앱 URL**을 복사해요.
4. 오케스트라 컴퓨터에서 `orchestra.bat` → **9) 구글 시트 연결 설정** → URL·토큰을 붙여 넣어요. (토큰은 채팅·문서에 올리지 않아요. 토큰이 없으면 시트를 읽거나 바꿀 수 없어요.)
5. `orchestra.bat`을 다시 열고 **8)**을 골라요.

## AI끼리 맥락 넘기기

AI들은 서로 대화하지 못하고 파일로만 일을 넘겨요. 그래서 맥락이 빠지지 않게 이렇게 해요.

- **`docs/context.md`** (프로젝트 배경): 무엇을 왜 만드는지, 데이터 파일의 뜻과 함정, 이미 정한 것. 모든 AI가 맨 먼저 읽고, 새로 정한 것은 Claude가 "결정 기록"에 덧붙여요.
- **`orchestra/runs/<id>/handoff.md`** (인수인계 노트): 스크립트가 단계마다 "요청 해석·결정과 이유·넘긴 일·실제로 바뀐 파일·검수 결과"를 차례로 쌓아요. 다음 AI는 이걸 먼저 읽어요. 수정 회차에도 이어서 쌓여요.
- **단계별 실제 변경 파일**(`r1_1_claude_changes.patch` 등): 다음 AI가 보고서만 믿지 않고 실제 코드를 확인해요.
- **Claude 후속 단계**: Gemini가 "Claude에게 넘길 일"(JS가 만드는 class 변경 등)을 적으면, 스크립트가 Claude에게 바로 한 번 더 맡겨요. 예전엔 이 요청이 검수까지 그냥 넘어갔어요.
- **Codex 인수인계 점검**: 넘긴 일이 모두 처리됐는지, JS와 CSS의 class 이름이 맞는지 따로 확인해요.

PR 본문에도 인수인계 노트 전체가 들어가요.

## 모델 바꾸기

`orchestra/orchestra.py` 위쪽 "모델 설정" 몇 줄만 고치면 돼요. 빈칸(`""`)이면 그 프로그램의 기본값을 써요.

| AI | 지금 설정 | 바꾸는 법 |
|---|---|---|
| Claude | `CLAUDE_MODEL = "claude-opus-5-5"`, `CLAUDE_EFFORT = "high"` | effort: low / medium / high / xhigh / max |
| Codex | `CODEX_MODEL = "gpt-6.2-astra"`, `CODEX_EFFORT = "medium"` | 모델 이름은 `codex` 실행 후 `/model`에서 확인 |
| Gemini | `GEMINI_MODEL = ""` | `agy` 실행 후 `/model`에서 고르면 그 선택이 계속 유지돼요 |

effort(생각 깊이)가 높을수록 꼼꼼하지만 느리고 사용량을 더 써요. **7) 환경 점검**에서 지금 설정을 볼 수 있어요.

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
| 8 | 구글 시트 작업함 처리 (팀원이 적은 '대기' 일을 차례로, 결과를 시트에 다시 적음) |
| 9 | 구글 시트 연결 설정 (처음 한 번) |

명령줄로도 됩니다: `python orchestra\orchestra.py new orchestra\tasks\파일.md --design-only --no-push`

## 파일

| 파일 | 내용 |
|---|---|
| `AGENTS.md` | 세 AI 공통 규칙 + 역할 범위 (Codex·Antigravity가 자동으로 읽음) |
| `CLAUDE.md` | Claude 코딩 규칙 (AGENTS.md를 불러옴) |
| `GEMINI.md` | Gemini 디자인 규칙 (Antigravity가 자동으로 읽음) |
| `.claude/settings.json` | 무인 실행 때 Claude에게 허용한 명령 (파일 수정, git 읽기, node 문법 검사) |
| `orchestra/roles/*.md` | 단계별 지시서 틀 |
| `orchestra/tasks/` | 작업 요청서 (사람이 씀, 시트에서 가져온 일은 `시트N행_*.md`로 자동 생성) |
| `orchestra/sheet_inbox.gs` | 구글 시트에 붙이는 연결 스크립트 |
| `orchestra/runs/` | 실행 기록 — 지시서, 보고서, 점검 결과, 변경 내용. **이 컴퓨터에만** 남아요 (git 제외) |

## 비용·권한 메모
- 세 AI 모두 각자 구독 계정의 사용량으로 돌아요. 별도 API 키가 필요 없어요. 한 작업에 구독 한도를 꽤 쓸 수 있으니, 요청서는 작게 나누는 게 좋아요.
- Gemini(agy)는 무인 실행을 위해 `--dangerously-skip-permissions`로 돌아요(파일 수정·명령 실행을 묻지 않음). 대신 작업은 별도 브랜치에서만 하고, 범위 밖 변경은 스크립트가 되돌려요.
- Codex는 `--sandbox read-only`라 파일을 고칠 수 없어요.
- 모델을 바꾸려면 `orchestra/orchestra.py` 위쪽의 `CLAUDE_CMD` / `GEMINI_CMD` / `CODEX_CMD`에 `--model ...` 옵션을 더하세요.
