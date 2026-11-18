"""
한국체육산업개발 '주차장 혼잡도 정보'(구역별 원활·혼잡·만차 기록)를 공연 일정과 맞춰 요약한다.

입력: data/raw/kspo_parking_congestion.csv (scripts/12_fetch_congestion.py로 받음)
      data/processed/event_days.csv
출력: web/data/congestion_summary.json

주의(자료 문제):
  - '등록시간'의 분 자리에 월, 초 자리에 일이 들어가 있다(699건 전부 해당, 예: 8월 12일 → 17:08:12).
    시각은 '시' 단위만 믿을 수 있다.
  - 직원이 상황이 바뀔 때 남긴 기록으로 보이며, 2025-02 ~ 2026-08 중 92일만 있다. 기록이 없는 날이 한산했는지는 알 수 없다.
  - 구역 이름(P1A~P11)과 실제 위치(동2문·남2문·북2문 등)의 대응은 자료에 없다.

  실행: python scripts\\13_congestion_summary.py
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "kspo_parking_congestion.csv"
EVENTS = ROOT / "data" / "processed" / "event_days.csv"
OUT = ROOT / "web" / "data" / "congestion_summary.json"


def main():
    d = pd.read_csv(RAW, encoding="utf-8-sig")
    mm = d["등록시간"].str[3:5].astype(int) == d["등록일"].str[5:7].astype(int)
    ss = d["등록시간"].str[6:8].astype(int) == d["등록일"].str[8:10].astype(int)
    d["hour"] = d["등록시간"].str[:2].astype(int)
    ev = pd.read_csv(EVENTS, encoding="utf-8-sig")
    kspo = {r["날짜"]: str(r["시작시각들"]).split(";")[0] for _, r in ev[ev["공연장"] == "KSPO DOME"].iterrows()}
    rows = []
    for day, g in d.groupby("등록일"):
        st = kspo.get(day)
        if not st or st == "nan" or int(st[:2]) < 15:       # 저녁 공연(15시 이후 시작)만
            continue
        full = g[g["혼잡도"] == "만차"]
        rows.append({"date": day, "start": st, "fullZones": int(full["주차구역"].nunique()),
                     "firstFullHour": int(full["hour"].min()) if len(full) else None,
                     "hoursBefore": int(int(st[:2]) - full["hour"].min()) if len(full) else None})
    R = pd.DataFrame(rows)
    f = R[R.fullZones > 0]
    zones = d[d["혼잡도"] == "만차"].groupby("주차구역")["등록일"].nunique().sort_values(ascending=False)
    non = [x for x in d["등록일"].unique() if x not in kspo]
    out = {
        "source": "한국체육산업개발 주차장 혼잡도 정보(공공데이터포털 15164156)",
        "period": [d["등록일"].min(), d["등록일"].max()], "records": int(len(d)), "days": int(d["등록일"].nunique()),
        "zones": int(d["주차구역"].nunique()),
        "kspoEveningDays": int(len(R)), "kspoDaysWithFull": int(len(f)),
        "hoursBefore": {"p25": float(f.hoursBefore.quantile(.25)), "med": float(f.hoursBefore.median()), "p75": float(f.hoursBefore.quantile(.75))},
        "fullZones": {"med": float(f.fullZones.median()), "max": int(f.fullZones.max())},
        "zoneFullDays": {k: int(v) for k, v in zones.items()},
        "nonKspoDays": len(non), "nonKspoDaysWithFull": int(d[d["등록일"].isin(non) & (d["혼잡도"] == "만차")]["등록일"].nunique()),
        "dataIssue": {"minuteIsMonth": float(mm.mean()), "secondIsDay": float(ss.mean())},
        "list": rows,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "list"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
