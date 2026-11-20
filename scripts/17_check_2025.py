"""
2025 입출차 원본(data/raw/kcisa_inout_2025.jsonl)을 얼마나 받았고, 그중 몇 줄을 계산에 쓸 수 있는지 점검한다.
인증키가 필요 없다. 원본은 읽기만 한다.

왜 필요한가
  - 2025 대수(몇 대가 왔나)는 전체 줄 수(TOTAL_2025)의 80% 이상을 '쓸 수 있는 줄'로 받았을 때만 쓴다(inout_common.enough_2025).
  - 받은 줄(offset)은 88%인데 쓸 수 있는 줄이 80%에 못 미치면, 겹친 줄·형식이 다른 줄이 얼마나 되는지 알아야 한다.

결과: data/processed/kcisa_2025_check.json (줄 수, 겹친 줄, 형식이 안 맞는 줄, 달별 받은 비율, 형식이 안 맞는 예 몇 개)
"""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inout_common as ic  # noqa: E402

OUT = ic.ROOT / "data" / "processed" / "kcisa_2025_check.json"


def main():
    p = ic.RAW / "kcisa_inout_2025.jsonl"
    if not p.exists():
        print("data/raw/kcisa_inout_2025.jsonl 이 없어요")
        return
    off = ic.RAW / "kcisa_inout_2025.jsonl.offset"
    offset = off.read_text(encoding="utf-8").strip() if off.exists() else None

    lines = bad_json = no_id = dup_same = dup_diff = no_pat = bad_num = 0
    seen = {}                                   # LOCAL_ID -> 줄 내용 해시
    prefix = Counter()
    month_lines = Counter()
    ex_no_pat, ex_bad_num, ex_dup_diff = [], [], []
    nums, months = [], []
    with open(p, encoding="utf-8") as f:
        for line in f:
            lines += 1
            try:
                d = json.loads(line)
            except ValueError:
                bad_json += 1
                continue
            lid = d.get("LOCAL_ID") or ""
            if not lid:
                no_id += 1
            h = hashlib.md5(line.strip().encode("utf-8")).hexdigest()
            if lid in seen:
                if seen[lid] == h:
                    dup_same += 1
                else:
                    dup_diff += 1
                    if len(ex_dup_diff) < 3:
                        ex_dup_diff.append(lid)
                continue
            seen[lid] = h
            prefix[lid.split("-")[0] if "-" in lid else "(하이픈 없음)"] += 1
            month = (d.get("TITLE") or "")[:6]
            month_lines[month] += 1
            desc = d.get("DESCRIPTION") or ""
            if not ic.PAT.search(desc):
                no_pat += 1
                if len(ex_no_pat) < 5:
                    ex_no_pat.append(desc[:120])
                continue
            try:
                num = int(lid.split("-")[1])
            except (IndexError, ValueError):
                bad_num += 1
                if len(ex_bad_num) < 5:
                    ex_bad_num.append(lid[:40])
                continue
            nums.append(num)
            months.append(month)

    used = len(nums)
    cov = {}
    if used:
        _, cov = ic.block_coverage(np.array(nums, dtype=np.int64), np.array(months))
    out = {
        "file": "data/raw/kcisa_inout_2025.jsonl",
        "offset": offset,
        "total2025": ic.TOTAL_2025,
        "lines": lines,
        "badJson": bad_json,
        "noLocalId": no_id,
        "dupSameLine": dup_same,
        "dupDiffContent": dup_diff,
        "uniqueIds": len(seen),
        "noPattern": no_pat,
        "badNumber": bad_num,
        "usable": used,
        "usableShare": round(used / ic.TOTAL_2025, 4),
        "enough2025": ic.enough_2025(used),
        "idPrefix": dict(prefix.most_common(10)),
        "monthLines": dict(sorted(month_lines.items())),
        "coverage": cov,
        "examples": {"noPattern": ex_no_pat, "badNumber": ex_bad_num, "dupDiffContent": ex_dup_diff},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"받은 줄 {lines:,} (다운로드 위치 {offset})")
    print(f"  겹친 줄: 내용까지 같음 {dup_same:,} · 번호만 같고 내용 다름 {dup_diff:,}")
    print(f"  형식 안 맞음 {no_pat:,} · 번호 못 읽음 {bad_num:,} · JSON 깨짐 {bad_json:,}")
    print(f"계산에 쓸 수 있는 줄 {used:,} = 전체 {ic.TOTAL_2025:,}의 {used / ic.TOTAL_2025:.1%}"
          f" → 2025 대수 사용 {'가능' if ic.enough_2025(used) else '불가(80% 미만)'}")
    for m, v in cov.items():
        print(f"  {m}: 받은 {v['got']:,} / 번호 폭 {v['span']:,} = {v['ratio']:.0%} (덩어리 {v['blocks']})")
    print(f"저장: {OUT.relative_to(ic.ROOT)}")


if __name__ == "__main__":
    main()
