"""
PR을 올리기 전에 누구나(사람·AI 모두) 돌리는 기본 점검. 설치할 것 없음(Python 3, 있으면 Node).

  python scripts/check_all.py

점검 내용
  1) JS 문법 (node --check)  — Node가 없으면 건너뜀
  2) 파이썬 문법 (scripts/)
  3) web/data/*.json·*.geojson 이 올바른 JSON인지
  4) JS가 id로 찾는 화면 요소가 HTML에 있는지 (audience.js·exit_gate.js ↔ index.html),
     docs/design.md "절대 지우면 안 되는 id" 목록이 HTML에 그대로 있는지
  5) 인증키처럼 보이는 값이 코드에 직접 적혀 있지 않은지

문제(❌)가 하나라도 있으면 끝 코드 1. 경고(⚠)는 확인만 하면 된다.
"""
import json
import py_compile
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
problems, warnings = [], []


def rel(p):
    return p.relative_to(ROOT).as_posix()


# 1) JS 문법
node = shutil.which("node")
js_files = sorted((ROOT / "web" / "assets").glob("*.js")) + sorted((ROOT / "api").glob("*.js"))
if node:
    for f in js_files:
        r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
        if r.returncode:
            lines = r.stderr.strip().splitlines()
            where = next((l for l in lines if ".js:" in l), "")
            what = next((l for l in lines if "Error" in l), lines[-1] if lines else "")
            problems.append(f"JS 문법 오류: {rel(f)}\n    {where.strip()}  {what.strip()}")
else:
    warnings.append("Node가 없어서 JS 문법 검사를 건너뜀")

# 2) 파이썬 문법
for f in sorted((ROOT / "scripts").glob("*.py")):
    try:
        py_compile.compile(str(f), doraise=True)
    except py_compile.PyCompileError as e:
        problems.append(f"파이썬 문법 오류: {rel(f)}\n    {e.msg.strip().splitlines()[-1]}")

# 3) 데이터 JSON
for f in sorted((ROOT / "web" / "data").glob("*.json")) + sorted((ROOT / "web" / "data").glob("*.geojson")):
    try:
        json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:
        problems.append(f"JSON 오류: {rel(f)} ({e})")

# 4) JS가 찾는 id ↔ HTML의 id
ID_CALL = re.compile(r"""(?:getElementById|\$)\(\s*["']([A-Za-z][\w-]*)["']\s*\)""")
for js, html in (("audience.js", "index.html"), ("exit_gate.js", "index.html")):
    jf, hf = ROOT / "web" / "assets" / js, ROOT / "web" / html
    if not (jf.exists() and hf.exists()):
        continue
    jtext = jf.read_text(encoding="utf-8")
    html_ids = set(re.findall(r"""\bid\s*=\s*["']([^"']+)["']""", hf.read_text(encoding="utf-8")))
    made_by_js = set(re.findall(r"""\bid\s*=\s*\\?["']([A-Za-z][\w-]*)""", jtext)) | \
        set(re.findall(r"""\.id\s*=\s*["']([A-Za-z][\w-]*)["']""", jtext))
    missing = sorted(set(ID_CALL.findall(jtext)) - html_ids - made_by_js)
    for m in missing:
        warnings.append(f"{js}가 찾는 id '{m}'가 {html}에 없음 (JS가 따로 만드는 요소가 아니라면 화면이 깨질 수 있음)")

# 4-2) docs/design.md에 적힌 "절대 지우면 안 되는 id"가 HTML에 있는지
design = ROOT / "docs" / "design.md"
if design.exists():
    text = design.read_text(encoding="utf-8")
    m = re.search(r"^## 4\..*?(?=^## |\Z)", text, re.S | re.M)
    current = None
    for line in (m.group(0).splitlines() if m else []):
        h = re.search(r"`web/([\w-]+\.html)`", line)
        if h and not line.strip().startswith("- `id`"):
            current = ROOT / "web" / h.group(1)
        if current and re.match(r"\s*-\s*`id`\s*:", line) and current.exists():
            need = re.findall(r"`([A-Za-z][\w-]*)`", line.split(":", 1)[1])
            have = set(re.findall(r"""\bid\s*=\s*["']([^"']+)["']""", current.read_text(encoding="utf-8")))
            for i in need:
                if i not in have:
                    problems.append(f"{current.name}에서 지우면 안 되는 id '{i}'가 없어짐 (docs/design.md 4절)")

# 5) 인증키처럼 보이는 값
KEYLIKE = re.compile(r"""(?i)(appkey|app_key|apikey|api_key|servicekey|service_key|secret|token)["']?\s*[:=]\s*["']([A-Za-z0-9%+/=_-]{16,})["']""")
ALLOWED = {"PARKING21803504"}
for f in js_files + sorted((ROOT / "scripts").glob("*.py")) + sorted((ROOT / "web").glob("*.html")):
    for m in KEYLIKE.finditer(f.read_text(encoding="utf-8", errors="ignore")):
        if m.group(2) not in ALLOWED:
            problems.append(f"인증키처럼 보이는 값이 코드에 있음: {rel(f)} ({m.group(1)}=…) → 환경변수로 읽게 바꾸세요")

# 6) 진행 중 작업 표지판(docs/wip/) 미삭제 알림
wip_dir = ROOT / "docs" / "wip"
if wip_dir.exists():
    active_wips = sorted(f.name for f in wip_dir.glob("*.md") if f.name.lower() != "readme.md")
    if active_wips:
        warnings.append(f"docs/wip/에 진행 중 표지판이 남아 있음: {', '.join(active_wips)} (내 작업이 끝났다면 커밋 전에 삭제)")

print("=== 기본 점검 ===")
for w in warnings:
    print("⚠ " + w)
for p in problems:
    print("❌ " + p)
if not problems:
    print(f"✅ 문제 없음 (JS {len(js_files) if node else 0}개, 경고 {len(warnings)}개)")
sys.exit(1 if problems else 0)
