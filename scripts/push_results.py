"""
주인 컴퓨터에서 다시 계산한 결과 파일만 GitHub main에 올릴지 묻는다(1~2분 뒤 사이트 반영).
  실행: python scripts\\push_results.py web/data/a.json web/data/b.json ...
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    files = [f for f in sys.argv[1:] if (ROOT / f).exists()]
    if not files:
        print("올릴 파일이 없어요.")
        return
    changed = subprocess.run(["git", "status", "--porcelain", "--", *files], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if not changed:
        print("바뀐 결과가 없어 올리지 않았어요.")
        return
    print("바뀐 결과 파일:\n" + changed)
    try:
        a = input("\n이 결과를 GitHub에 올릴까요? 올리면 1~2분 뒤 사이트에 반영돼요. (y/n): ").strip().lower()
    except EOFError:
        return
    if a not in ("y", "yes", "ㅛ"):
        print("올리지 않았어요.")
        return
    steps = [["git", "add", "--", *files],
             ["git", "commit", "-m", "[주인 PC] 2025 입출차 자료로 출차·주차·관객 성향 분석 다시 계산"],
             ["git", "pull", "--rebase", "--autostash"], ["git", "push"]]
    for c in steps:
        r = subprocess.run(c, cwd=ROOT)
        if r.returncode != 0 and c[1] != "commit":
            print("※ 올리기 중 문제가 생겼어요. 이 창 내용을 AI에게 보여 주세요.")
            return
    print("올렸어요.")


if __name__ == "__main__":
    main()
