# -*- coding: utf-8 -*-
"""
AI 오케스트라 지휘 스크립트
  Claude(코딩) → Gemini/Antigravity(디자인) → 자동 점검 → Codex(최종 검수) → GitHub에 올리기(PR)

사용법 (저장소 맨 위 폴더에서):
  python orchestra/orchestra.py            메뉴로 고르기 (orchestra.bat 더블클릭과 같음)
  python orchestra/orchestra.py new [작업파일] [--design-only | --code-only] [--no-push]
  python orchestra/orchestra.py fix        Codex 검수 의견을 Claude·Gemini가 반영 → 다시 검수
  python orchestra/orchestra.py review     다시 점검·검수만
  python orchestra/orchestra.py resume     멈춘 단계부터 이어서
  python orchestra/orchestra.py doctor     필요한 프로그램이 다 있는지 점검
  python orchestra/orchestra.py sheet      구글 시트 작업함의 '대기' 일을 차례로 처리
  python orchestra/orchestra.py sheet-setup  구글 시트 연결(웹 앱 주소·토큰) 저장

외부 라이브러리 없이 Python 3.8+ 표준 기능만 쓴다.
"""
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# 모델 설정 — 여기만 바꾸면 된다. 빈칸("")이면 그 프로그램의 기본값을 쓴다.
#   생각 깊이(effort): 높을수록 꼼꼼하지만 느리고 사용량을 더 쓴다.
#   Claude: low / medium / high / xhigh / max      Codex: low / medium / high / xhigh
# ---------------------------------------------------------------------------
CLAUDE_MODEL = "claude-opus-5-5"   # Claude Opus 5.5
CLAUDE_EFFORT = "high"
CODEX_MODEL = "gpt-6.2-astra"      # GPT-6.2 Astra. 빈칸 = Codex 기본 모델. 이름은 codex 안에서 /model 로 확인
CODEX_EFFORT = "medium"
GEMINI_MODEL = "gemini-4-carbon-high"  # Gemini 4 Carbon, 생각 깊이 High. 빈칸 = agy에서 /model 로 골라 둔 모델. 이름 목록: agy models

# 실행 명령 (보통은 고칠 필요 없음)
#   {prompt} 자리에 "이 파일을 읽고 따라 해" 라는 짧은 영어 문장이 들어간다.
#   (윈도우에서 긴 한글 프롬프트를 명령줄로 넘기면 깨질 수 있어서, 지시는 파일로 넘긴다.)
CLAUDE_CMD = (["claude", "-p", "{prompt}", "--permission-mode", "acceptEdits"]
              + (["--model", CLAUDE_MODEL] if CLAUDE_MODEL else [])
              + (["--effort", CLAUDE_EFFORT] if CLAUDE_EFFORT else []))
GEMINI_CMD = (["agy", "-p", "{prompt}", "--dangerously-skip-permissions"]
              + (["--model", GEMINI_MODEL] if GEMINI_MODEL else []))
CODEX_CMD = (["codex", "exec", "--sandbox", "read-only"]
             + (["-m", CODEX_MODEL] if CODEX_MODEL else [])
             + (["-c", 'model_reasoning_effort="%s"' % CODEX_EFFORT] if CODEX_EFFORT else [])
             + ["-o", "{out}", "{prompt}"])
STAGE_TIMEOUT_MIN = 45          # AI 한 단계 최대 시간(분)
AUTO_FIX_ROUNDS = 1             # 구글 시트 작업함: Codex가 '수정필요'면 자동으로 고치는 횟수
SHEET_URL_ENV, SHEET_TOKEN_ENV = "ORCH_SHEET_URL", "ORCH_SHEET_TOKEN"   # 시트 연결(웹 앱 주소·토큰)
KIND_MODE = {"": "full", "자동": "full", "둘 다": "full", "코딩": "code", "디자인": "design"}
BASE_BRANCH = "main"

ROOT = Path(__file__).resolve().parent.parent
ORCH = ROOT / "orchestra"
RUNS = ORCH / "runs"
TASKS = ORCH / "tasks"
ROLES = ORCH / "roles"

# 역할별 파일 범위 (AGENTS.md 표와 같게 유지)
CLAUDE_DENY = [
    "web/assets/*.css", "docs/design.md",
    "AGENTS.md", "CLAUDE.md", "GEMINI.md", ".claude/*", "orchestra/*",
    "set_keys.bat", "delete_keys.bat", "data/raw/*",
]
GEMINI_ALLOW = [
    "web/*.html", "web/assets/*.css", "web/assets/img/*", "web/assets/fonts/*", "docs/design.md",
]

# 사람이 관리하는 폴더: AI 범위 검사·되돌리기에서 제외
USER_PATHS = ("orchestra/runs/", "orchestra/tasks/")

STAGE_NAMES = {
    "claude": "1. Claude 코딩",
    "gemini": "2. Gemini 디자인",
    "claude_followup": "2-1. Claude 후속 (디자인 담당이 넘긴 일)",
    "checks": "3. 자동 점검",
    "codex": "4. Codex 검수",
    "publish": "5. GitHub에 올리기",
}


# ---------------------------------------------------------------------------
# 공통 도우미
# ---------------------------------------------------------------------------
try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass


class Stop(Exception):
    """사용자에게 보여 줄 메시지와 함께 멈춘다."""


def say(msg=""):
    print(msg, flush=True)


def banner(msg):
    say()
    say("=" * 62)
    say("  " + msg)
    say("=" * 62)


def read(p):
    return Path(p).read_text(encoding="utf-8", errors="replace")


def write(p, text):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


def git(*args, check=True, strip=True):
    r = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if check and r.returncode != 0:
        raise Stop("git %s 실패:\n%s" % (" ".join(args), (r.stderr or r.stdout).strip()))
    if not check:
        return r
    return r.stdout.strip() if strip else r.stdout


# 공식 설치 프로그램이 CLI를 넣는 곳. PATH보다 먼저 본다.
# (Antigravity 데스크톱 앱이 'agy' 이름을 가져가도 CLI를 쓰게, 설치 직후 새 창을 안 열어도 찾게)
KNOWN_EXE = {
    "agy": [r"%LOCALAPPDATA%\agy\bin\agy.exe", "~/.local/bin/agy"],
    "claude": [r"%USERPROFILE%\.local\bin\claude.exe", "~/.local/bin/claude"],
}


def which(name):
    for p in KNOWN_EXE.get(name, []):
        f = Path(os.path.expanduser(os.path.expandvars(p)))
        if "%" not in str(f) and f.is_file():
            return str(f)
    return shutil.which(name)


def rel(p):
    return Path(p).resolve().relative_to(ROOT).as_posix()


def now_id():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


# ---------------------------------------------------------------------------
# 상태 (orchestra/runs/<id>/state.json, git에는 안 올라감)
# ---------------------------------------------------------------------------
def run_dir(run_id):
    return RUNS / run_id


def save_state(st):
    write(run_dir(st["id"]) / "state.json", json.dumps(st, ensure_ascii=False, indent=2))


def load_state_for_current_branch():
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    if not branch.startswith("orchestra/"):
        raise Stop(
            "지금 브랜치는 '%s' 이에요. 오케스트라 작업 브랜치(orchestra/...)에서만 할 수 있어요.\n"
            "GitHub Desktop에서 해당 orchestra/ 브랜치로 바꾼 뒤 다시 실행하세요." % branch)
    run_id = branch.split("/", 1)[1]
    f = run_dir(run_id) / "state.json"
    if not f.exists():
        raise Stop("이 브랜치의 작업 기록(%s)이 이 컴퓨터에 없어요. 처음 실행한 컴퓨터에서 이어 주세요." % rel(f))
    return json.loads(read(f))


def fname(st, key):
    """회차별 파일 이름. 예: r1_1_claude_report.md"""
    r = "r%d" % st["round"]
    return {
        "claude_prompt": r + "_1_claude_prompt.md",
        "claude_report": r + "_1_claude_report.md",
        "gemini_prompt": r + "_2_gemini_prompt.md",
        "gemini_report": r + "_2_gemini_report.md",
        "claude_changes": r + "_1_claude_changes.patch",
        "gemini_changes": r + "_2_gemini_changes.patch",
        "followup_prompt": r + "_2b_claude_followup_prompt.md",
        "followup_report": r + "_2b_claude_followup_report.md",
        "followup_changes": r + "_2b_claude_followup_changes.patch",
        "checks": r + "_3_checks.md",
        "diff": r + "_diff.patch",
        "codex_prompt": r + "_4_codex_prompt.md",
        "codex_review": r + "_4_codex_review.md",
    }[key]


def prev_review_path(st):
    if st["round"] <= 1:
        return None
    p = run_dir(st["id"]) / ("r%d_4_codex_review.md" % (st["round"] - 1))
    return p if p.exists() else None


def fill(template_name, mapping):
    text = read(ROLES / template_name)
    for k, v in mapping.items():
        text = text.replace("{{%s}}" % k, v)
    return text


# ---------------------------------------------------------------------------
# 인수인계 노트 (handoff.md)
#   AI끼리는 대화를 못 하고 파일로만 일을 넘긴다. 그래서 단계마다 스크립트가
#   "요청 해석·결정·넘긴 일·실제로 바뀐 파일"을 한 파일에 차례로 쌓고, 모든 AI가 먼저 읽게 한다.
# ---------------------------------------------------------------------------
HANDOFF_REPORT_MAX = 6000


def handoff_path(st):
    return run_dir(st["id"]) / "handoff.md"


def handoff_init(st):
    write(handoff_path(st),
          "# 인수인계 노트 — %s\n\n"
          "- 실행 id: `%s` · 브랜치: `%s` · 방식: %s\n"
          "- 단계: %s\n"
          "- 모든 담당은 이 노트를 먼저 읽는다. 노트는 지휘 스크립트가 단계마다 덧붙인다(AI는 고치지 않는다).\n"
          "- 프로젝트 배경은 `docs/context.md`, 작업 요청서는 `task.md`.\n"
          % (st["title"], st["id"], st["branch"], st["mode"], " → ".join(STAGE_NAMES[x] for x in st["plan"])))


def handoff_add(st, title, body):
    f = handoff_path(st)
    old = read(f) if f.exists() else ""
    stamp = datetime.now().strftime("%m-%d %H:%M")
    write(f, old.rstrip() + "\n\n---\n## [%d회차] %s  (%s)\n\n%s\n" % (st["round"], title, stamp, body.strip()))


def save_stage_changes(st, before_sha, key):
    """이 단계에서 실제로 바뀐 코드를 파일로 남긴다(다음 담당이 보고서만 믿지 않게)."""
    head = git("rev-parse", "HEAD")
    if head == before_sha:
        write(run_dir(st["id"]) / fname(st, key), "(이 단계에서 바뀐 파일 없음)\n")
        return "(바뀐 파일 없음)"
    stat = git("diff", "--stat", before_sha, head)
    diff = git("diff", before_sha, head, "--", ".", ":(exclude)data/**", ":(exclude)web/data/**",
               ":(exclude)orchestra/runs/**")
    if len(diff) > 200_000:
        diff = diff[:200_000] + "\n\n...(너무 길어서 잘랐어요)"
    write(run_dir(st["id"]) / fname(st, key), "# 바뀐 파일\n" + stat + "\n\n# 변경 내용 (data/, web/data/ 제외)\n" + diff)
    return stat


def report_section(text, heading):
    """보고서에서 '## heading' 아래 내용을 꺼낸다."""
    m = re.search(r"^##\s*" + re.escape(heading) + r"[^\n]*\n(.*?)(?=^##\s|\Z)", text, re.S | re.M)
    return m.group(1).strip() if m else ""


def has_real_items(section_text):
    """'없음'이나 양식 안내문만 있으면 False."""
    for line in section_text.splitlines():
        t = line.strip().lstrip("-*•").strip()
        if not t or t.startswith("```"):
            continue
        if re.fullmatch(r"(없음|해당\s*없음|none|n/?a)[.。]?", t, re.I):
            continue
        if "없으면" in t or "파일:함수 |" in t:
            continue
        return True
    return False


# ---------------------------------------------------------------------------
# 변경 파일 목록과 범위 지키기
# ---------------------------------------------------------------------------
def changed_entries():
    """[(상태코드, 경로)] — 작업 폴더에서 아직 커밋 안 된 변경."""
    out = git("status", "--porcelain", "-z", "-uall", strip=False)
    items, parts, i = [], out.split("\0"), 0
    while i < len(parts):
        e = parts[i]
        i += 1
        if not e:
            continue
        code, path = e[:2], e[3:]
        items.append((code, path))
        if code[0] in "RC" and i < len(parts):   # 이름 바꾸기: 다음 칸이 옛 이름
            items.append(("D ", parts[i]))
            i += 1
    return items


def match_any(path, patterns):
    return any(fnmatch.fnmatch(path, p) for p in patterns)


def in_head(path):
    return git("cat-file", "-e", "HEAD:" + path, check=False).returncode == 0


def revert_path(path):
    if in_head(path):
        git("checkout", "HEAD", "--", path)
    else:
        git("rm", "-q", "--cached", "--ignore-unmatch", "--", path, check=False)
        f = ROOT / path
        if f.exists():
            f.unlink()


def fold_ai_commits(before_sha, log):
    """AI가 규칙을 어기고 직접 커밋했으면, 커밋을 풀어서 변경으로 되돌려 놓는다."""
    head = git("rev-parse", "HEAD")
    if head != before_sha:
        git("reset", "--soft", before_sha)
        git("reset", "-q")
        log.append("AI가 직접 만든 커밋을 풀었어요(스크립트가 다시 커밋합니다).")


def guard(role, log):
    reverted = []
    for code, path in changed_entries():
        if path.startswith(USER_PATHS):
            continue
        bad = match_any(path, CLAUDE_DENY) if role == "claude" else not match_any(path, GEMINI_ALLOW)
        if bad:
            revert_path(path)
            reverted.append(path)
    if reverted:
        log.append("[%s] 담당 범위 밖이라 되돌린 파일: %s" % (role, ", ".join(sorted(set(reverted)))))
    if role == "gemini":
        id_guard(log)


ID_RE = re.compile(r"""\bid\s*=\s*["']([^"']+)["']""")
DATA_RE = re.compile(r"""\b(data-[\w-]+)\s*=""")


def id_guard(log):
    """HTML에서 JS가 쓰는 id·data-* 가 사라졌으면 그 HTML 파일을 되돌린다."""
    for code, path in changed_entries():
        if not fnmatch.fnmatch(path, "web/*.html") or not in_head(path) or not (ROOT / path).exists():
            continue
        old = git("show", "HEAD:" + path, strip=False)
        new = read(ROOT / path)
        lost = (set(ID_RE.findall(old)) - set(ID_RE.findall(new))) | (set(DATA_RE.findall(old)) - set(DATA_RE.findall(new)))
        if lost:
            revert_path(path)
            log.append("[gemini] %s 에서 JS가 쓰는 %s 가 사라져서 이 파일 변경을 되돌렸어요."
                       % (path, ", ".join(sorted(lost))))


def commit_stage(st, label):
    if not changed_entries():
        say("  (바뀐 파일 없음)")
        return False
    git("add", "-A")
    git("commit", "-q", "-m", "[오케스트라/%s] %s" % (label, st["title"]))
    say("  커밋했어요: " + git("log", "-1", "--format=%h %s"))
    return True


def write_guard_log(st, lines):
    if not lines:
        return
    f = run_dir(st["id"]) / "guard.log"
    old = read(f) if f.exists() else ""
    stamp = datetime.now().strftime("%m-%d %H:%M")
    write(f, old + "".join("%s r%d %s\n" % (stamp, st["round"], l) for l in lines))
    for l in lines:
        say("  ⚠ " + l)


# ---------------------------------------------------------------------------
# AI 실행
# ---------------------------------------------------------------------------
def run_ai(cmd_template, prompt_rel, out_rel=None):
    exe = which(cmd_template[0])
    if not exe:
        raise Stop("'%s' 명령을 찾을 수 없어요. orchestra/README.md의 설치 안내를 보세요." % cmd_template[0])
    prompt = "Read the file %s and carry out the instructions in it exactly. Write in Korean." % prompt_rel
    cmd = [exe] + [a.replace("{prompt}", prompt).replace("{out}", out_rel or "") for a in cmd_template[1:]]
    say("  실행: %s ..." % cmd_template[0])
    t0 = time.time()
    try:
        env = dict(os.environ)
        if cmd_template[0] == "claude" and CLAUDE_EFFORT:
            env["CLAUDE_CODE_EFFORT_LEVEL"] = CLAUDE_EFFORT
        r = subprocess.run(cmd, cwd=str(ROOT), timeout=STAGE_TIMEOUT_MIN * 60, env=env)
    except subprocess.TimeoutExpired:
        raise Stop("%s 이(가) %d분 안에 끝나지 않았어요." % (cmd_template[0], STAGE_TIMEOUT_MIN))
    say("  끝 (%d분 %d초, 종료코드 %d)" % (divmod(int(time.time() - t0), 60) + (r.returncode,)))
    if r.returncode != 0:
        raise Stop("%s 이(가) 오류로 끝났어요(종료코드 %d). 위 메시지를 확인하세요.\n"
                   "로그인이 풀렸다면 터미널에서 '%s' 를 한 번 직접 실행해 로그인하세요."
                   % (cmd_template[0], r.returncode, cmd_template[0]))


def extra_for_fix(st, role):
    prev = prev_review_path(st)
    if not prev:
        return ""
    tag = "[코딩]" if role == "claude" else "[디자인]"
    return ("- **이번은 수정 회차(%d회차)다.** 이전 검수 의견 `%s` 을 읽고, \"반드시 고칠 것\" 중 `%s` 항목을 고친다. "
            "\"고치면 좋은 것\"도 담당 범위면 반영해도 된다. 해당 항목이 없으면 아무것도 바꾸지 말고 보고서에 \"해당 없음\"이라고 쓴다.\n"
            "- 앞 회차에 무엇을 왜 했는지는 `handoff.md`에 있다. 앞 회차의 결정을 뒤집어야 하면 보고서 \"결정과 이유\"에 이유를 적는다."
            % (st["round"], rel(prev), tag))


def stage_ai(st, role):
    d = run_dir(st["id"])
    rd = rel(d)
    if role == "claude":
        mapping = {"RUN_DIR": rd, "REPORT": fname(st, "claude_report"), "EXTRA": extra_for_fix(st, "claude")}
        prompt_f, report_f, cmd, label, guard_role, chg = (d / fname(st, "claude_prompt"), d / fname(st, "claude_report"),
                                                           CLAUDE_CMD, "Claude", "claude", "claude_changes")
        tmpl = "claude.md"
    elif role == "claude_followup":
        mapping = {"RUN_DIR": rd, "REPORT": fname(st, "followup_report"), "GEMINI_CHANGES": fname(st, "gemini_changes")}
        prompt_f, report_f, cmd, label, guard_role, chg = (d / fname(st, "followup_prompt"), d / fname(st, "followup_report"),
                                                           CLAUDE_CMD, "Claude 후속", "claude", "followup_changes")
        tmpl = "claude_followup.md"
    else:
        claude_chg = fname(st, "claude_changes")
        if not (d / claude_chg).exists():
            write(d / claude_chg, "(이번 회차엔 코딩 단계가 없었어요)\n")
        mapping = {"RUN_DIR": rd, "REPORT": fname(st, "gemini_report"), "CLAUDE_CHANGES": claude_chg,
                   "EXTRA": extra_for_fix(st, "gemini")}
        prompt_f, report_f, cmd, label, guard_role, chg = (d / fname(st, "gemini_prompt"), d / fname(st, "gemini_report"),
                                                           GEMINI_CMD, "Gemini", "gemini", "gemini_changes")
        tmpl = "gemini.md"
    if not handoff_path(st).exists():
        handoff_init(st)
    write(prompt_f, fill(tmpl, mapping))
    before = git("rev-parse", "HEAD")
    run_ai(cmd, rel(prompt_f))
    log = []
    fold_ai_commits(before, log)
    guard(guard_role, log)
    write_guard_log(st, log)
    if not report_f.exists():
        write(report_f, "# %s 보고서\n(%s가 보고서를 남기지 않았어요.)\n" % (label, label))
        say("  ⚠ %s가 보고서를 남기지 않았어요." % label)
    commit_stage(st, label)
    stat = save_stage_changes(st, before, chg)
    rep_text = read(report_f).strip()
    if len(rep_text) > HANDOFF_REPORT_MAX:
        rep_text = rep_text[:HANDOFF_REPORT_MAX] + "\n...(길어서 잘랐어요. 전체: `%s`)" % report_f.name
    body = "**실제로 바뀐 파일** (전체 변경: `%s`)\n```\n%s\n```\n" % (fname(st, chg), stat.strip("\n"))
    if log:
        body += "\n**범위 지키기로 되돌린 것**\n" + "\n".join("- " + l for l in log) + "\n"
    # 보고서 제목 단계를 두 칸 내려서(## → ####) 노트의 단계 제목과 섞이지 않게 한다
    rep_text = re.sub(r"^(#{1,4})\s", lambda m: "#" * min(6, len(m.group(1)) + 2) + " ", rep_text, flags=re.M)
    body += "\n**보고서** (`%s`)\n\n%s\n" % (report_f.name, rep_text)
    handoff_add(st, STAGE_NAMES[role], body)


def need_followup(st):
    """Gemini가 'Claude에게 넘길 일'을 적었으면 Claude 후속 단계를 넣는다(회차당 한 번)."""
    f = run_dir(st["id"]) / fname(st, "gemini_report")
    if not f.exists() or "claude_followup" in st["plan"]:
        return False
    return has_real_items(report_section(read(f), "Claude에게 넘길 일"))


# ---------------------------------------------------------------------------
# 자동 점검 (AI 없이 스크립트가 직접)
# ---------------------------------------------------------------------------
SECRET_RE = re.compile(r"""(?i)(api[_-]?key|secret|token|passw(or)?d|app[_-]?key)\s*[:=]\s*["']?[A-Za-z0-9_\-]{16,}""")
JS_ID_RE = re.compile(r"""(?:getElementById|\$)\(\s*["']([A-Za-z][\w-]*)["']\s*\)""")


def stage_checks(st):
    d = run_dir(st["id"])
    lines, fails, warns = [], 0, 0

    # 1) JS 문법
    node = which("node")
    js_files = sorted(list((ROOT / "web" / "assets").glob("*.js")) + list((ROOT / "api").glob("*.js")))
    if node:
        bad = []
        for f in js_files:
            r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode != 0:
                bad.append("%s\n```\n%s\n```" % (rel(f), (r.stderr or "").strip()[-800:]))
        if bad:
            fails += 1
            lines.append("❌ JS 문법 오류\n" + "\n".join(bad))
        else:
            lines.append("✅ JS 문법 (%d개 파일)" % len(js_files))
    else:
        warns += 1
        lines.append("⚠ node가 없어서 JS 문법 검사를 건너뛰었어요")

    # 2) 데이터 JSON
    bad = []
    data_files = sorted(list((ROOT / "web" / "data").glob("*.json")) + list((ROOT / "web" / "data").glob("*.geojson")))
    for f in data_files:
        try:
            json.loads(read(f))
        except Exception as e:
            bad.append("%s — %s" % (rel(f), e))
    if bad:
        fails += 1
        lines.append("❌ 데이터 JSON 오류\n- " + "\n- ".join(bad))
    else:
        lines.append("✅ 데이터 JSON (%d개 파일)" % len(data_files))

    # 3) HTML이 부르는 파일이 실제로 있는지
    missing = []
    html_files = sorted((ROOT / "web").glob("*.html"))
    for h in html_files:
        for ref in re.findall(r"""(?:src|href)\s*=\s*["']([^"'#?]+)""", read(h)):
            if re.match(r"^(https?:|//|mailto:|tel:|data:|/api)", ref):
                continue
            if not (h.parent / ref).exists():
                missing.append("%s → %s" % (rel(h), ref))
    if missing:
        fails += 1
        lines.append("❌ HTML이 부르는 파일이 없어요\n- " + "\n- ".join(missing))
    else:
        lines.append("✅ HTML이 부르는 파일 (%d개 화면)" % len(html_files))

    # 4) JS가 찾는 id가 HTML(또는 JS가 만드는 HTML)에 있는지
    defined = set()
    for h in html_files:
        defined |= set(ID_RE.findall(read(h)))
    js_text = {f: read(f) for f in js_files if f.parent.name == "assets"}
    for t in js_text.values():
        defined |= set(ID_RE.findall(t))
        defined |= set(re.findall(r"""\.id\s*=\s*["']([\w-]+)["']""", t))
    used = {}
    for f, t in js_text.items():
        for i in JS_ID_RE.findall(t):
            used.setdefault(i, set()).add(f.name)
    lost = sorted(i for i in used if i not in defined)
    if lost:
        warns += 1
        lines.append("⚠ JS가 찾는데 HTML에 없는 id (동적으로 만드는 것일 수도 있음)\n- " +
                     "\n- ".join("%s (%s)" % (i, ", ".join(sorted(used[i]))) for i in lost))
    else:
        lines.append("✅ JS가 찾는 id %d개 모두 있음" % len(used))

    # 5) CSS 괄호 짝
    for f in sorted((ROOT / "web" / "assets").glob("*.css")):
        t = re.sub(r"/\*.*?\*/", "", read(f), flags=re.S)
        if t.count("{") != t.count("}"):
            fails += 1
            lines.append("❌ %s 괄호 짝이 안 맞아요 ({ %d개, } %d개)" % (rel(f), t.count("{"), t.count("}")))
        else:
            lines.append("✅ %s 괄호 짝" % rel(f))

    # 6) 이번 작업 변경 + 비밀값 검사
    diff = git("diff", st["base"], "HEAD", "--", ".", ":(exclude)data/**", ":(exclude)web/data/**",
               ":(exclude)orchestra/runs/**")
    stat = git("diff", "--stat", st["base"], "HEAD")
    big = len(diff) > 300_000
    write(d / fname(st, "diff"),
          "# 변경 요약 (데이터 파일 포함)\n" + stat + "\n\n# 변경 내용 (data/, web/data/ 제외)\n" +
          (diff[:300_000] + "\n\n...(너무 길어서 잘랐어요)" if big else diff))
    added = [l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")]
    leaks = [l.strip()[:120] for l in added if SECRET_RE.search(l)]
    if leaks:
        fails += 1
        lines.append("❌ 인증키처럼 보이는 값이 새로 들어갔어요\n- " + "\n- ".join(leaks))
    else:
        lines.append("✅ 새로 들어간 인증키 없음")
    lines.append("ℹ 이번 작업에서 바뀐 파일:\n```\n%s\n```" % (stat or "(없음)"))

    head = "# 자동 점검 결과 (%d회차)\n오류 %d · 주의 %d\n\n" % (st["round"], fails, warns)
    write(d / fname(st, "checks"), head + "\n\n".join(lines) + "\n")
    st["checks"] = {"fails": fails, "warns": warns}
    say("  오류 %d · 주의 %d → %s" % (fails, warns, rel(d / fname(st, "checks"))))


# ---------------------------------------------------------------------------
# Codex 검수
# ---------------------------------------------------------------------------
VERDICT_RE = re.compile(r"판정\s*[:：]\s*\**\s*(통과|수정\s*필요)")


def stage_codex(st):
    d = run_dir(st["id"])
    prev = prev_review_path(st)
    extra = ""
    if prev:
        extra = "- 이전 회차 검수 의견: `%s` — 그때 \"반드시 고칠 것\"이 이번에 고쳐졌는지도 확인한다." % rel(prev)
    mapping = {
        "RUN_DIR": rel(d), "CLAUDE_REPORT": fname(st, "claude_report"), "GEMINI_REPORT": fname(st, "gemini_report"),
        "FOLLOWUP_REPORT": fname(st, "followup_report"),
        "CHECKS": fname(st, "checks"), "DIFF": fname(st, "diff"), "BASE": st["base"][:8], "EXTRA": extra,
    }
    prompt_f, out_f = d / fname(st, "codex_prompt"), d / fname(st, "codex_review")
    if not handoff_path(st).exists():
        handoff_init(st)
    write(prompt_f, fill("codex.md", mapping))
    run_ai(CODEX_CMD, rel(prompt_f), rel(out_f))
    if not out_f.exists() or not read(out_f).strip():
        raise Stop("Codex가 검수 결과를 남기지 않았어요. 'review'로 다시 검수해 보세요.")
    m = VERDICT_RE.search(read(out_f))
    verdict = m.group(1).replace(" ", "") if m else "판정없음"
    st.setdefault("verdicts", {})[str(st["round"])] = verdict
    say("  Codex 판정: %s" % verdict)
    review = read(out_f)
    must = report_section(review, "반드시 고칠 것") or "(없음)"
    hand = report_section(review, "인수인계 점검")
    handoff_add(st, STAGE_NAMES["codex"], "**판정: %s** (전체: `%s`)\n\n**반드시 고칠 것**\n%s\n%s"
                % (verdict, out_f.name, must, ("\n**인수인계 점검**\n" + hand) if hand else ""))
    # 검수 중에 혹시 파일이 바뀌었으면 되돌린다 (Codex는 읽기만)
    for code, path in changed_entries():
        if not path.startswith(USER_PATHS):
            revert_path(path)
            write_guard_log(st, ["[codex] 검수 담당이 바꾼 %s 을(를) 되돌렸어요." % path])


# ---------------------------------------------------------------------------
# 요약 + GitHub 올리기
# ---------------------------------------------------------------------------
def section(path, title):
    p = Path(path)
    body = read(p).strip() if p.exists() else "(이번 회차엔 없음)"
    return "<details><summary><b>%s</b></summary>\n\n%s\n\n</details>\n" % (title, body)


def build_summary(st):
    d = run_dir(st["id"])
    verdict = st.get("verdicts", {}).get(str(st["round"]), "판정없음")
    ck = st.get("checks", {})
    icon = {"통과": "✅", "수정필요": "🛠"}.get(verdict, "❔")
    parts = [
        "## %s Codex 판정: %s  (%d회차)" % (icon, verdict, st["round"]),
        "자동 점검: 오류 %s · 주의 %s" % (ck.get("fails", "?"), ck.get("warns", "?")),
        "",
        "**미리보기**: 이 PR에 Vercel이 남기는 댓글(Preview 링크)에서 바뀐 화면을 확인하세요. "
        "괜찮으면 Merge, 고칠 게 있으면 `orchestra.bat` → '검수 의견 반영'.",
        "",
        section(d / fname(st, "codex_review"), "Codex 검수 의견"),
        section(d / "task.md", "작업 요청서"),
    ]
    if handoff_path(st).exists():   # 단계별 보고서·바뀐 파일·검수 결과가 순서대로 다 들어 있음
        parts.append(section(handoff_path(st), "인수인계 노트 (단계별 보고서와 넘긴 일, 회차 전체)"))
    else:
        parts += [section(d / fname(st, "claude_report"), "Claude 보고서 (코딩)"),
                  section(d / fname(st, "gemini_report"), "Gemini 보고서 (디자인)")]
    parts.append(section(d / fname(st, "checks"), "자동 점검"))
    if (d / "guard.log").exists():
        parts.append(section(d / "guard.log", "범위 지키기 기록"))
    parts.append("\n---\n_AI 오케스트라(orchestra/orchestra.py)가 만든 PR입니다. 실행 id: `%s`_" % st["id"])
    text = "\n".join(parts)
    if len(text) > 60000:
        text = text[:60000] + "\n\n...(길어서 잘랐어요. 전체는 실행한 컴퓨터의 orchestra/runs/%s 에 있어요)" % st["id"]
    write(d / ("r%d_summary.md" % st["round"]), text)
    return d / ("r%d_summary.md" % st["round"])


def repo_slug():
    url = git("remote", "get-url", "origin", check=False)
    url = url.stdout.strip() if hasattr(url, "stdout") else ""
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    return m.group(1) if m else None


def stage_publish(st):
    summary = build_summary(st)
    if st.get("no_push"):
        say("  --no-push: GitHub에 올리지 않았어요. 요약: " + rel(summary))
        return
    r = git("push", "-u", "origin", st["branch"], check=False)
    if r.returncode != 0:
        raise Stop("GitHub에 올리기(push) 실패:\n%s\nGitHub Desktop에서 이 브랜치를 Push 해도 돼요." % r.stderr.strip())
    say("  브랜치를 올렸어요: " + st["branch"])
    gh = which("gh")
    slug = repo_slug()
    compare = "https://github.com/%s/compare/%s...%s?expand=1" % (slug, BASE_BRANCH, st["branch"]) if slug else None
    st["pr_url"] = compare or st["branch"]
    if not gh:
        say("  gh(GitHub CLI)가 없어서 PR은 직접 만들어야 해요.")
        if compare:
            say("  → 이 주소를 열고 'Create pull request': " + compare)
            say("    본문에는 이 파일 내용을 붙여 넣으세요: " + rel(summary))
        return
    ghrun = lambda *a: subprocess.run([gh, *a], cwd=str(ROOT), capture_output=True, text=True,
                                      encoding="utf-8", errors="replace")
    v = ghrun("pr", "view", st["branch"], "--json", "url,state")
    if v.returncode == 0 and '"OPEN"' in v.stdout:
        url = json.loads(v.stdout)["url"]
        st["pr_url"] = url
        c = ghrun("pr", "comment", st["branch"], "--body-file", str(summary))
        say("  PR에 %d회차 검수 결과를 댓글로 남겼어요: %s" % (st["round"], url) if c.returncode == 0
            else "  PR 댓글 실패: " + c.stderr.strip())
    else:
        title = "[AI 오케스트라] " + st["title"]
        c = ghrun("pr", "create", "--base", BASE_BRANCH, "--head", st["branch"], "--title", title,
                  "--body-file", str(summary))
        if c.returncode == 0:
            st["pr_url"] = c.stdout.strip().splitlines()[-1]
            say("  PR을 만들었어요: " + c.stdout.strip())
        else:
            say("  PR 만들기 실패: " + c.stderr.strip())
            if compare:
                say("  → 직접 만들기: " + compare)


# ---------------------------------------------------------------------------
# 흐름
# ---------------------------------------------------------------------------
def run_plan(st):
    for stage in st["plan"]:
        if stage in st["done"]:
            continue
        banner(STAGE_NAMES[stage] + "  (%d회차)" % st["round"])
        if stage in ("claude", "gemini", "claude_followup"):
            stage_ai(st, stage)
            if stage == "gemini" and need_followup(st):
                st["plan"].insert(st["plan"].index("gemini") + 1, "claude_followup")
                say("  Gemini가 Claude에게 넘긴 일이 있어요 → 'Claude 후속' 단계를 넣었어요.")
        elif stage == "checks":
            stage_checks(st)
        elif stage == "codex":
            stage_codex(st)
        elif stage == "publish":
            stage_publish(st)
        st["done"].append(stage)
        save_state(st)
    v = st.get("verdicts", {}).get(str(st["round"]), "")
    banner("끝! Codex 판정: %s" % (v or "-"))
    say("  기록 폴더: " + rel(run_dir(st["id"])))
    if v == "수정필요":
        say("  다음: 검수 의견을 반영하려면 orchestra.bat → '검수 의견 반영'")
    say("  다음: PR의 Vercel 미리보기에서 화면 확인 → 괜찮으면 GitHub에서 Merge")


def ensure_clean():
    dirty = [p for c, p in changed_entries() if not p.startswith(USER_PATHS)]
    if dirty:
        raise Stop("아직 저장(커밋)하지 않은 변경이 있어요:\n  " + "\n  ".join(dirty[:15]) +
                   "\nGitHub Desktop에서 Commit 하거나 되돌린 뒤 다시 실행하세요.")


def task_title(text, fallback):
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def pick_task():
    files = sorted([f for f in TASKS.glob("*.md") if not f.name.startswith("_")],
                   key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        raise Stop("orchestra/tasks/ 에 작업 요청서가 없어요. _양식.md 를 복사해서 하나 만드세요.")
    say("\n작업 요청서를 고르세요 (최근 수정 순):")
    for i, f in enumerate(files[:15], 1):
        say("  %d) %s — %s" % (i, f.name, task_title(read(f), "")))
    s = input("번호 (그냥 Enter = 1): ").strip() or "1"
    if not s.isdigit() or not (1 <= int(s) <= len(files[:15])):
        raise Stop("번호를 잘못 골랐어요.")
    return files[int(s) - 1]


def cmd_new(task_path, mode, no_push):
    ensure_clean()
    task_path = Path(task_path) if task_path else pick_task()
    if not task_path.is_absolute():
        task_path = (Path.cwd() / task_path).resolve()
    if not task_path.exists():
        raise Stop("작업 요청서가 없어요: %s" % task_path)
    text = read(task_path)
    say("\n최신 %s 를 받아 오는 중..." % BASE_BRANCH)
    r = git("fetch", "origin", BASE_BRANCH, check=False)
    base_ref = "origin/" + BASE_BRANCH if r.returncode == 0 else BASE_BRANCH
    if r.returncode != 0:
        say("  ⚠ 받아 오기 실패, 이 컴퓨터의 %s 기준으로 시작해요." % BASE_BRANCH)
    run_id = now_id()
    branch = "orchestra/" + run_id
    git("switch", "-c", branch, base_ref)
    plan = {"full": ["claude", "gemini"], "design": ["gemini"], "code": ["claude"]}[mode] + ["checks", "codex", "publish"]
    st = {
        "id": run_id, "branch": branch, "base": git("rev-parse", "HEAD"), "title": task_title(text, task_path.stem),
        "task_src": str(task_path), "mode": mode, "round": 1, "plan": plan, "done": [], "no_push": no_push,
    }
    write(run_dir(run_id) / "task.md", text)
    handoff_init(st)
    save_state(st)
    if any(p.startswith("orchestra/tasks/") for c, p in changed_entries()):
        git("add", "--", "orchestra/tasks")
        git("commit", "-q", "-m", "[오케스트라] 작업 요청서: " + st["title"])
    banner("새 작업: %s" % st["title"])
    say("  브랜치: %s  (main은 그대로예요)" % branch)
    say("  순서: " + " → ".join(STAGE_NAMES[s] for s in plan))
    run_plan(st)
    return st


def cmd_fix():
    ensure_clean()
    st = load_state_for_current_branch()
    if "codex" not in st["done"]:
        raise Stop("아직 이번 회차 검수가 끝나지 않았어요. 'resume'으로 이어서 하세요.")
    st["round"] += 1
    ai = [s for s in ("claude", "gemini") if s in st["plan"]] or ["claude"]
    if st["mode"] == "code":
        ai = ["claude"]
    st["plan"], st["done"] = ai + ["checks", "codex", "publish"], []
    handoff_add(st, "수정 회차 시작", "앞 회차 Codex 검수의 \"반드시 고칠 것\"을 반영한다. 순서: "
                + " → ".join(STAGE_NAMES[x] for x in st["plan"]))
    save_state(st)
    run_plan(st)


def cmd_review():
    ensure_clean()
    st = load_state_for_current_branch()
    st["plan"] = [s for s in st["plan"] if s in ("claude", "gemini")] + ["checks", "codex", "publish"]
    st["done"] = [s for s in ("claude", "gemini") if s in st["plan"]]
    save_state(st)
    run_plan(st)


def cmd_resume():
    st = load_state_for_current_branch()
    left = [s for s in st["plan"] if s not in st["done"]]
    if not left:
        say("이 작업은 이미 끝까지 진행됐어요.")
        return
    nxt = left[0]
    if nxt in ("claude", "gemini", "claude_followup") and changed_entries():
        say("⚠ 멈춘 단계(%s)에서 만들다 만 변경이 있어요. 지우고 그 단계를 처음부터 다시 해요." % nxt)
        for c, p in changed_entries():
            if not p.startswith(USER_PATHS):
                revert_path(p)
    run_plan(st)


# ---------------------------------------------------------------------------
# 구글 시트 작업함 (팀원이 시트에 적은 할 일을 가져와 처리하고, 결과를 시트에 다시 적음)
#   시트 쪽 연결 스크립트: orchestra/sheet_inbox.gs
# ---------------------------------------------------------------------------
def sheet_conf():
    url, token = os.environ.get(SHEET_URL_ENV, "").strip(), os.environ.get(SHEET_TOKEN_ENV, "").strip()
    if not url or not token:
        raise Stop("구글 시트 연결 정보가 없어요. orchestra.bat → 9) 시트 연결 설정 을 먼저 하세요.\n"
                   "(설정한 뒤에는 이 창을 닫고 orchestra.bat을 다시 열어야 적용돼요.)")
    return url, token


def sheet_call(payload=None):
    """payload가 없으면 대기 목록(GET), 있으면 상태 바꾸기(POST)."""
    import urllib.parse
    import urllib.request
    url, token = sheet_conf()
    if payload is None:
        req = urllib.request.Request(url + ("&" if "?" in url else "?") + urllib.parse.urlencode({"token": token}))
    else:
        body = json.dumps(dict(payload, token=token), ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "text/plain;charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:      # 구글이 한 번 다른 주소로 보내는 것은 자동으로 따라감
            d = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        raise Stop("구글 시트에 연결하지 못했어요: %s" % e)
    if isinstance(d, dict) and d.get("error"):
        raise Stop("구글 시트: " + d["error"])
    return d


def sheet_update(task, **kw):
    try:
        sheet_call(dict(kw, row=task["row"]))
    except Stop as e:
        say("  ⚠ 시트에 결과를 못 적었어요(%s). 시트 %s행을 직접 고쳐 주세요." % (e, task["row"]))


def sheet_task_file(task):
    safe = re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", task["title"])[:30].strip("_") or "작업"
    f = TASKS / ("시트%s행_%s.md" % (task["row"], safe))
    detail = task.get("detail", "").strip() or task["title"]
    write(f, "# %s\n\n- 요청자: %s\n- 출처: 구글 시트 작업함 %s행 (번호 %s), 종류: %s\n\n## 바꿀 것\n%s\n" % (
        task["title"], task.get("who") or "-", task["row"], task.get("no") or "-", task.get("kind") or "자동", detail))
    return f


def cmd_sheet():
    banner("구글 시트 작업함")
    ensure_clean()
    tasks = sheet_call().get("tasks", [])
    if not tasks:
        say("  대기 중인 할 일이 없어요.")
        return
    for i, t in enumerate(tasks, 1):
        say("  %d) [%s행] %s  — %s, 종류: %s" % (i, t["row"], t["title"], t.get("who") or "-", t.get("kind") or "자동"))
    s = input("\n번호 하나, 또는 그냥 Enter = 위에서부터 전부 차례로: ").strip()
    if s:
        if not s.isdigit() or not (1 <= int(s) <= len(tasks)):
            raise Stop("번호를 잘못 골랐어요.")
        tasks = [tasks[int(s) - 1]]
    start_branch = git("rev-parse", "--abbrev-ref", "HEAD")
    done = []
    try:
        for t in tasks:
            mode = KIND_MODE.get(t.get("kind", ""), "full")
            claim = sheet_call({"action": "claim", "row": t["row"], "status": "진행중", "verdict": ""})
            if not claim.get("ok"):
                say("  [%s행] 다른 곳에서 이미 맡았어요(%s). 건너뜀." % (t["row"], claim.get("status")))
                continue
            banner("시트 %s행: %s" % (t["row"], t["title"]))
            try:
                st = cmd_new(str(sheet_task_file(t)), mode, False)
                for _ in range(AUTO_FIX_ROUNDS):
                    if st.get("verdicts", {}).get(str(st["round"])) != "수정필요":
                        break
                    say("  Codex가 수정필요라고 해서 한 번 더 고쳐요.")
                    cmd_fix()
                    st = load_state_for_current_branch()
                v = st.get("verdicts", {}).get(str(st["round"]), "판정없음")
                sheet_update(t, status="완료" if v == "통과" else "수정필요", result=st.get("pr_url", st["branch"]),
                             verdict="%s (%d회차)" % (v, st["round"]))
                done.append((t, v))
            except Stop as e:
                say("■ [%s행] 멈췄어요: %s" % (t["row"], e))
                sheet_update(t, status="실패", verdict=str(e)[:200])
                done.append((t, "실패"))
                if changed_entries():           # 다음 작업을 위해 만들다 만 변경을 정리
                    for c, p in changed_entries():
                        if not p.startswith(USER_PATHS):
                            revert_path(p)
    finally:
        r = git("switch", BASE_BRANCH if start_branch.startswith("orchestra/") else start_branch, check=False)
        if r.returncode != 0:
            git("switch", BASE_BRANCH, check=False)
    banner("작업함 처리 끝")
    for t, v in done:
        say("  [%s행] %s → %s" % (t["row"], t["title"], v))
    say("  결과(PR 링크)는 구글 시트에 적었어요. 미리보기를 보고 GitHub에서 Merge 하세요.")


def cmd_sheet_setup():
    banner("구글 시트 연결 설정")
    say("  orchestra/sheet_inbox.gs 맨 위 안내대로 시트에 스크립트를 붙이고 웹 앱으로 배포한 뒤 진행하세요.")
    say("  토큰은 채팅·문서에 올리지 마세요. 이 컴퓨터의 윈도우 사용자 설정에만 저장돼요.")
    url = input("\n웹 앱 URL (https://script.google.com/macros/s/.../exec): ").strip()
    token = input("오케스트라 토큰: ").strip()
    if not url.startswith("https://script.google.com/") or not token:
        raise Stop("URL이나 토큰이 비었거나 형식이 달라요.")
    for k, v in ((SHEET_URL_ENV, url), (SHEET_TOKEN_ENV, token)):
        r = subprocess.run(["setx", k, v], capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            raise Stop("저장 실패: " + (r.stderr or r.stdout).strip())
        os.environ[k] = v
    n = len(sheet_call().get("tasks", []))
    say("  연결 성공! 지금 대기 중인 할 일 %d개. 다음부터는 8) 시트 작업함 처리 를 고르면 돼요." % n)


def cmd_doctor():
    banner("환경 점검")
    ok = True

    def show(name, good, detail, need=True):
        nonlocal ok
        mark = "✅" if good else ("❌" if need else "⚠")
        if need and not good:
            ok = False
        say("  %s %-22s %s" % (mark, name, detail))

    def ver(cmd):
        exe = which(cmd)
        if not exe:
            return None
        try:
            r = subprocess.run([exe, "--version"], capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=60)
            return (r.stdout or r.stderr).strip().splitlines()[0] if (r.stdout or r.stderr).strip() else "설치됨"
        except Exception:
            return "설치됨"

    show("Python", sys.version_info >= (3, 8), sys.version.split()[0])
    g = ver("git")
    show("git", bool(g), g or "없음 → https://git-scm.com 설치")
    if g:
        name = git("config", "user.name", check=False).stdout.strip()
        show("git 사용자 이름", bool(name), name or "없음 → git config --global user.name \"이름\"")
        show("GitHub 저장소", bool(repo_slug()), repo_slug() or "origin이 GitHub가 아님")
    for cmd, label, hint in [
        ("claude", "Claude Code", "PowerShell: irm https://claude.ai/install.ps1 | iex"),
        ("agy", "Antigravity CLI (agy)", "PowerShell: irm https://antigravity.google/cli/install.ps1 | iex"),
        ("codex", "Codex CLI", "PowerShell: powershell -ExecutionPolicy ByPass -c \"irm https://chatgpt.com/codex/install.ps1 | iex\""),
    ]:
        v = ver(cmd)
        show(label, bool(v), v or "없음 → " + hint)
    v = ver("gh")
    show("GitHub CLI (gh, 선택)", bool(v), v or "없으면 PR은 링크로 직접 만듦 → winget install GitHub.cli", need=False)
    show("구글 시트 작업함 (선택)", bool(os.environ.get(SHEET_URL_ENV) and os.environ.get(SHEET_TOKEN_ENV)),
         "연결됨" if os.environ.get(SHEET_URL_ENV) else "없음 → 9) 시트 연결 설정", need=False)
    say("  ·  모델 설정               Claude %s(%s) / Codex %s(%s) / Gemini %s" % (
        CLAUDE_MODEL or "기본", CLAUDE_EFFORT or "기본", CODEX_MODEL or "기본", CODEX_EFFORT or "기본",
        GEMINI_MODEL or "agy에서 고른 모델"))
    v = ver("node")
    show("Node.js (선택)", bool(v), v or "없으면 JS 문법 검사를 건너뜀", need=False)
    say()
    say("  모두 ✅ 이면 준비 완료. 각 AI는 처음 한 번 터미널에서 claude / agy / codex 를 실행해 로그인해 두세요."
        if ok else "  ❌ 항목을 설치한 뒤 다시 점검하세요.")


def menu():
    banner("AI 오케스트라 — olpark-traffic")
    say("  1) 새 작업          Claude 코딩 → Gemini 디자인 → Codex 검수")
    say("  2) 새 작업 (디자인만) Gemini 디자인 → Codex 검수")
    say("  3) 새 작업 (코딩만)   Claude 코딩 → Codex 검수")
    say("  4) 검수 의견 반영     지금 브랜치에서 Codex 의견을 고치고 다시 검수")
    say("  5) 다시 검수만")
    say("  6) 멈춘 곳부터 이어서")
    say("  7) 환경 점검")
    say("  8) 구글 시트 작업함 처리  팀원이 시트에 적은 '대기' 일을 차례로")
    say("  9) 구글 시트 연결 설정    처음 한 번")
    s = input("\n번호: ").strip()
    if s == "1":
        cmd_new(None, "full", False)
    elif s == "2":
        cmd_new(None, "design", False)
    elif s == "3":
        cmd_new(None, "code", False)
    elif s == "4":
        cmd_fix()
    elif s == "5":
        cmd_review()
    elif s == "6":
        cmd_resume()
    elif s == "7":
        cmd_doctor()
    elif s == "8":
        cmd_sheet()
    elif s == "9":
        cmd_sheet_setup()
    else:
        say("번호를 잘못 골랐어요.")


def main(argv):
    os.chdir(str(ROOT))
    if not argv:
        return menu()
    cmd, rest = argv[0], argv[1:]
    flags = {a for a in rest if a.startswith("--")}
    args = [a for a in rest if not a.startswith("--")]
    if cmd == "new":
        mode = "design" if "--design-only" in flags else "code" if "--code-only" in flags else "full"
        cmd_new(args[0] if args else None, mode, "--no-push" in flags)
    elif cmd == "fix":
        cmd_fix()
    elif cmd == "review":
        cmd_review()
    elif cmd == "resume":
        cmd_resume()
    elif cmd == "doctor":
        cmd_doctor()
    elif cmd == "sheet":
        cmd_sheet()
    elif cmd == "sheet-setup":
        cmd_sheet_setup()
    else:
        say(__doc__)


def wait_enter():
    """orchestra.bat으로 메뉴를 열었을 때 결과를 읽기 전에 창이 닫히지 않게."""
    # 메뉴로 열었을 때(orchestra.bat 또는 orchestra.py 더블클릭)는 항상 기다린다.
    if os.environ.get("ORCH_PAUSE") == "1" or not sys.argv[1:]:
        try:
            input("\n  다 읽었으면 Enter를 누르세요. (창이 닫혀요)")
        except (EOFError, KeyboardInterrupt):
            pass


if __name__ == "__main__":
    code = 0
    try:
        main(sys.argv[1:])
    except Stop as e:
        say()
        say("■ 멈췄어요: %s" % e)
        say("  (이어서 하려면 orchestra.bat → '멈춘 곳부터 이어서')")
        code = 1
    except KeyboardInterrupt:
        say("\n■ 중단했어요. 이어서 하려면 orchestra.bat → '멈춘 곳부터 이어서'")
        code = 130
    except Exception:
        import traceback
        traceback.print_exc()
        say("\n■ 예상하지 못한 오류예요. 위 내용을 Claude에게 보여 주세요.")
        code = 1
    wait_enter()
    sys.exit(code)
