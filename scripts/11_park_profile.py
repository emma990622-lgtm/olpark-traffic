"""
KSPO DOME 공연일, 공연 시작 시각을 기준으로 공원 주차장에 차가 몇 대 있고 15분마다 몇 대 들어오고 나가는지
(공연 시작 3시간 전 ~ 6시간 뒤, 5분 간격). 운영자 화면 3D 지도의 시간 슬라이더에 쓴다.

입력: data/raw/parking_inout_202407.csv (2024년 7월 전체, 빠짐없는 기록)
      data/raw/kcisa_inout_2025.jsonl   (2025년, 전체의 80% 이상 받았을 때만 대수에 씀. 받은 비율로 보정 → inout_common.py)
      data/processed/event_days.csv
출력: web/data/park_profile.json
2024년 7월과 2025년 공연을 모두 넣어 공연별 곡선의 중앙값을 낸다. 2025 자료가 모자라면 2024년 7월만 쓴다.

  실행: python scripts\\11_park_profile.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inout_common as ic  # noqa: E402

OUT = ic.ROOT / "web" / "data" / "park_profile.json"
REL = np.arange(-180, 361, 5)          # 공연 시작 기준 분


def curves(x, s):
    rin = ((x.in_time - s).dt.total_seconds() / 60).values
    rout = ((x.out_time - s).dt.total_seconds() / 60).values
    w = x.w.values
    parked = [float(w[(rin <= t) & (rout > t)].sum()) for t in REL]
    ins = [float(w[(rin > t - 15) & (rin <= t)].sum()) for t in REL]
    outs = [float(w[(rout > t - 15) & (rout <= t)].sum()) for t in REL]
    return parked, ins, outs


def main():
    d24 = ic.load_2024()
    d25, cov = ic.load_2025()
    got = sum(v["got"] for v in cov.values())
    use25 = ic.enough_2025(got)
    d = pd.concat([d24, d25] if use25 else [d24], ignore_index=True)
    d = d[d.w.notna()]
    shows = []
    for day, start, title in ic.kspo_shows("2024-07"):
        s = pd.Timestamp(f"{day} {start}")
        win = d[(d.in_time <= s + pd.Timedelta(hours=6)) & (d.out_time > s - pd.Timedelta(minutes=195))]
        if len(win) < 800:
            continue
        parked, ins, outs = curves(win, s)
        shows.append({"date": day, "start": start, "title": title, "src": day[:4],
                      "parked": parked, "in15": ins, "out15": outs})
    if not shows:
        raise SystemExit("KSPO DOME 공연일이 없습니다.")
    med = lambda k: [int(round(np.median([s[k][i] for s in shows]))) for i in range(len(REL))]
    lo = lambda k: [int(round(np.percentile([s[k][i] for s in shows], 10))) for i in range(len(REL))]
    hi = lambda k: [int(round(np.percentile([s[k][i] for s in shows], 90))) for i in range(len(REL))]
    n24 = sum(1 for s in shows if s["src"] == "2024")
    n25 = len(shows) - n24
    src = f"공원 주차장 입출차 기록, KSPO DOME 공연 {len(shows)}회 중앙값 (2024년 7월 {n24}회"
    src += f" + 2025년 {n25}회, 2025 자료 {got / ic.TOTAL_2025:.0%} 받아 받은 비율로 보정)" if n25 else ")"
    out = {
        "venue": "KSPO DOME", "source": src, "built": pd.Timestamp.now().strftime("%Y-%m-%d"),
        "bySource": {"2024": n24, "2025": n25}, "share2025": round(got / ic.TOTAL_2025, 3) if n25 else None,
        "relMin": REL.tolist(), "parked": med("parked"), "parkedMin": lo("parked"), "parkedMax": hi("parked"),
        "rangeNote": "공연별 10~90% 범위" if len(shows) >= 10 else "공연별 최소~최대",
        "peakByShow": [{"date": s["date"], "title": s["title"], "peak": int(round(max(s["parked"])))} for s in shows],
        "in15": med("in15"), "out15": med("out15"),
        "capacity": 2120, "shows": [{k: s[k] for k in ("date", "start", "title")} for s in shows],
    }
    if len(shows) < 10:          # 공연이 적으면 범위는 최소~최대
        out["parkedMin"] = [int(round(min(s["parked"][i] for s in shows))) for i in range(len(REL))]
        out["parkedMax"] = [int(round(max(s["parked"][i] for s in shows))) for i in range(len(REL))]
    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    pk = int(np.argmax(out["parked"]))
    print(f"{src}. 주차 최대 {out['parked'][pk]}대(시작 {REL[pk]:+d}분), 저장 → {OUT}")
    if not use25:
        print(f"※ 2025 자료가 {got / ic.TOTAL_2025:.0%}만 있어 대수에는 2024년 7월만 썼어요.")


if __name__ == "__main__":
    main()
