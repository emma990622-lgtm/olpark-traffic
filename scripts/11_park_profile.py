"""
KSPO DOME 공연일, 공연 시작 시각을 기준으로 공원 주차장에 차가 몇 대 있고 15분마다 몇 대 들어오고 나가는지
(공연 시작 3시간 전 ~ 6시간 뒤, 5분 간격). 운영자 화면 3D 지도의 시간 슬라이더에 쓴다.

입력: data/raw/parking_inout_202407.csv (2024년 7월 전체 입출차, 빠짐없는 기록이라 대수를 그대로 쓸 수 있음)
      data/processed/event_days.csv
출력: web/data/park_profile.json
2025년 자료는 날마다 일부만 받아서 대수에는 쓰지 않는다.

  실행: python scripts\\11_park_profile.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "parking_inout_202407.csv"
EVENTS = ROOT / "data" / "processed" / "event_days.csv"
OUT = ROOT / "web" / "data" / "park_profile.json"
REL = np.arange(-180, 361, 5)          # 공연 시작 기준 분


def main():
    d = pd.read_csv(RAW, encoding="cp949")
    d.columns = ["date", "in_time", "out_time"]
    d["in_time"] = pd.to_datetime(d.in_time, errors="coerce")
    d["out_time"] = pd.to_datetime(d.out_time, errors="coerce")
    d = d.dropna(subset=["in_time", "out_time"])
    ev = pd.read_csv(EVENTS, encoding="utf-8-sig")
    shows = []
    for _, r in ev[(ev["공연장"] == "KSPO DOME") & ev["날짜"].str.startswith("2024-07")].iterrows():
        ts = str(r["시작시각들"]).split(";")
        if len(ts) != 1:
            continue
        s = pd.Timestamp(f"{r['날짜']} {ts[0]}")
        rin = (d.in_time - s).dt.total_seconds().values / 60
        rout = (d.out_time - s).dt.total_seconds().values / 60
        parked = [int(((rin <= t) & (rout > t)).sum()) for t in REL]
        ins = [int(((rin > t - 15) & (rin <= t)).sum()) for t in REL]
        outs = [int(((rout > t - 15) & (rout <= t)).sum()) for t in REL]
        shows.append({"date": r["날짜"], "start": ts[0], "title": r["공연명"], "parked": parked, "in15": ins, "out15": outs})
    if not shows:
        raise SystemExit("2024년 7월 KSPO DOME 공연일이 없습니다.")
    med = lambda k: [int(np.median([s[k][i] for s in shows])) for i in range(len(REL))]
    lo = lambda k: [int(min(s[k][i] for s in shows)) for i in range(len(REL))]
    hi = lambda k: [int(max(s[k][i] for s in shows)) for i in range(len(REL))]
    out = {
        "venue": "KSPO DOME", "source": f"2024년 7월 공원 주차장 입출차 전체 기록, KSPO DOME 공연 {len(shows)}회 중앙값",
        "relMin": REL.tolist(), "parked": med("parked"), "parkedMin": lo("parked"), "parkedMax": hi("parked"),
        "peakByShow": [{"date": s["date"], "title": s["title"], "peak": max(s["parked"])} for s in shows], "in15": med("in15"), "out15": med("out15"),
        "capacity": 2120, "shows": [{k: s[k] for k in ("date", "start", "title")} for s in shows],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    pk = int(np.argmax(out["parked"]))
    print(f"공연 {len(shows)}회. 주차 최대 {out['parked'][pk]}대(시작 {REL[pk]:+d}분), 저장 → {OUT}")


if __name__ == "__main__":
    main()
