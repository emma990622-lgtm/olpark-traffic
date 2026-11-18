"""
공연 후 공원 주차장 출차 소요시간을 과거 입출차 기록으로 계산한다.

입력
  data/raw/kcisa_inout_2025.jsonl     2025 입출차(출구별, 초 단위). 다운로드 중이어도 받은 만큼으로 계산
  data/raw/parking_inout_202407.csv   2024년 7월 입출차(출구 없음, 분 단위)
  data/processed/event_days.csv       공연 일정
출력
  web/data/exit_profile.json

방법 (KSPO DOME 공연, 시작 시각이 하루 한 번인 날)
  1) 공연 관객 차로 보는 차: 시작 3시간 전 ~ 시작 20분 뒤에 들어와서, 2시간 넘게 머물고,
     시작 1.5시간 ~ 7시간 사이에 나간 차
  2) 15분 출차 대수가 가장 많은 때를 찾고, 그 절반 이상으로 늘어난 첫 시각을 '출차가 몰리기 시작한 때'(≈ 공연 종료)로 본다
  3) 그때부터 관객 차의 50%, 90%가 빠져나가기까지 걸린 분을 잰다
  2025 자료는 아직 일부만 받아서(날마다 일부 기록) 대수는 쓰지 않고 비율과 시간만 쓴다.

  실행: python scripts\\09_exit_profile.py
"""
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
EVENTS = ROOT / "data" / "processed" / "event_days.csv"
OUT = ROOT / "web" / "data" / "exit_profile.json"
PAT = re.compile(r"입구:([^,]*), 입차시간:([^,]*), 출구:([^,]*), 출차시간:(.*)$")


def load_2025():
    p = RAW / "kcisa_inout_2025.jsonl"
    if not p.exists():
        return pd.DataFrame(columns=["in_time", "out_time", "gate", "src"])
    rows, seen = [], set()
    with open(p, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue                       # 받는 중이라 마지막 줄이 잘렸을 수 있다
            if d.get("LOCAL_ID") in seen:
                continue
            seen.add(d.get("LOCAL_ID"))
            m = PAT.search(d.get("DESCRIPTION") or "")
            if m:
                rows.append([x.strip() for x in m.groups()])
    df = pd.DataFrame(rows, columns=["in_gate", "in_time", "out_gate", "out_time"])
    df["in_time"] = pd.to_datetime(df.in_time, errors="coerce")
    df["out_time"] = pd.to_datetime(df.out_time, errors="coerce")
    df["gate"] = df.out_gate.str.extract(r"^(\S+?문)")[0]
    df["src"] = "2025"
    return df.dropna(subset=["in_time", "out_time"])[["in_time", "out_time", "gate", "src"]]


def load_2024():
    p = RAW / "parking_inout_202407.csv"
    if not p.exists():
        return pd.DataFrame(columns=["in_time", "out_time", "gate", "src"])
    o = pd.read_csv(p, encoding="cp949")
    o.columns = ["date", "in_time", "out_time"]
    o["in_time"] = pd.to_datetime(o.in_time, errors="coerce")
    o["out_time"] = pd.to_datetime(o.out_time, errors="coerce")
    o["gate"] = None
    o["src"] = "2024"
    return o.dropna(subset=["in_time", "out_time"])[["in_time", "out_time", "gate", "src"]]


def analyze(x, day, start):
    s = pd.Timestamp(f"{day} {start}")
    rin = (x.in_time - s).dt.total_seconds() / 60
    rout = (x.out_time - s).dt.total_seconds() / 60
    a = x[(rin >= -180) & (rin <= 20) & (rout >= 90) & (rout <= 420) & (rout - rin >= 120)].copy()
    if len(a) < 150:
        return None
    a["m"] = rout[a.index]
    b = np.histogram(a.m, bins=np.arange(90, 421, 5))[0]
    r15 = np.convolve(b, [1, 1, 1], "valid")
    pk = int(r15.argmax())
    i = pk
    while i > 0 and r15[i - 1] >= 0.5 * r15[pk]:
        i -= 1
    surge = 90 + 5 * i
    after = a.m[a.m >= surge] - surge
    res = {
        "date": day, "start": start, "src": a.src.iloc[0], "cars": int(len(a)),
        "surgeMin": int(surge), "surge": (s + pd.Timedelta(minutes=surge)).strftime("%H:%M"),
        "t50": round(float(np.percentile(after, 50))), "t90": round(float(np.percentile(after, 90))),
        "gates": {},
    }
    g = a[a.gate.notna() & (a.m >= surge)]
    if len(g) >= 100:
        for name, gg in g.groupby("gate"):
            if len(gg) < 15:
                continue
            res["gates"][name] = {"share": round(len(gg) / len(g), 3),
                                  "t50": round(float(np.percentile(gg.m - surge, 50))),
                                  "t90": round(float(np.percentile(gg.m - surge, 90)))}
    return res


def q(v, p):
    return round(float(np.percentile(v, p)))


def main():
    ev = pd.read_csv(EVENTS, encoding="utf-8-sig")
    d = pd.concat([load_2025(), load_2024()], ignore_index=True)
    d["day"] = d.out_time.dt.strftime("%Y-%m-%d")
    by_day = dict(tuple(d.groupby("day")))
    shows = []
    for _, row in ev[ev["공연장"] == "KSPO DOME"].iterrows():
        day, ts = row["날짜"], str(row["시작시각들"]).split(";")
        if len(ts) != 1 or day not in by_day or len(by_day[day]) < 800:
            continue
        if "페스티벌" in str(row["공연명"]):       # 하루 종일 하는 행사는 공연 종료가 뚜렷하지 않아 뺀다
            continue
        r = analyze(by_day[day], day, ts[0])
        if r:
            r["title"] = row["공연명"]
            shows.append(r)
    if not shows:
        raise SystemExit("계산할 공연일이 없습니다.")
    S = pd.DataFrame(shows)
    summary = {
        "shows": len(S), "cars": int(S.cars.sum()),
        "surgeMin": {"p25": q(S.surgeMin, 25), "med": q(S.surgeMin, 50), "p75": q(S.surgeMin, 75)},
        "t50": {"p25": q(S.t50, 25), "med": q(S.t50, 50), "p75": q(S.t50, 75)},
        "t90": {"p25": q(S.t90, 25), "med": q(S.t90, 50), "p75": q(S.t90, 75)},
    }
    # 출구별 (2025만 출구 정보가 있음)
    gates = {}
    for r in shows:
        for g, v in r["gates"].items():
            gates.setdefault(g, []).append(v)
    gate_sum = {g: {"shows": len(v), "share": round(float(np.median([x["share"] for x in v])), 3),
                    "t50": q([x["t50"] for x in v], 50), "t90": q([x["t90"] for x in v], 50)}
                for g, v in gates.items() if len(v) >= 3}
    out = {
        "venue": "KSPO DOME", "built": pd.Timestamp.now().strftime("%Y-%m-%d"),
        "method": "시작 3시간 전~20분 뒤 입차, 2시간 넘게 머문 차를 관객 차로 보고, 출차가 몰리기 시작한 때부터 50%·90%가 빠지기까지 걸린 시간",
        "summary": summary, "gates": dict(sorted(gate_sum.items(), key=lambda kv: -kv[1]["share"])),
        "list": sorted(shows, key=lambda r: r["date"]),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    print("출구별:", json.dumps(out["gates"], ensure_ascii=False))
    print(f"저장 → {OUT}")


if __name__ == "__main__":
    main()
