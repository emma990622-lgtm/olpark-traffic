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

  출구별 비중: 공연마다 출구별 비중(합 100%)을 구한 뒤 공연들의 평균. 그 출구가 안 쓰인 공연은 0%로 넣는다.
  절반 이상 공연에서 쓰인 출구만 따로 보이고, 나머지는 '그 밖의 출구'로 묶는다 → 합이 항상 100%.

  실행: python scripts\\09_exit_profile.py
        python scripts\\09_exit_profile.py --from-json   (원본 없이 web/data/exit_profile.json의 공연별 결과로 출구 집계만 다시)
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
            v = {"n": int(len(gg)), "share": round(len(gg) / len(g), 4)}   # 작은 출구도 비중에는 넣는다(합 100%)
            if len(gg) >= 15:                                             # 시간은 15대 이상일 때만
                v["t50"] = round(float(np.percentile(gg.m - surge, 50)))
                v["t90"] = round(float(np.percentile(gg.m - surge, 90)))
            res["gates"][name] = v
    return res


def q(v, p):
    return round(float(np.percentile(v, p)))


OTHER = "그 밖의 출구"


def round_pct(shares):
    """비중(0~1)들을 정수 %로 반올림하되 합이 정확히 100이 되게(나머지가 큰 것부터 1씩 배분)."""
    raw = {k: v * 100 for k, v in shares.items()}
    base = {k: int(np.floor(v)) for k, v in raw.items()}
    left = 100 - sum(base.values())
    for k in sorted(raw, key=lambda k: -(raw[k] - base[k]))[:max(0, left)]:
        base[k] += 1
    return base


def aggregate_gates(shows, main_ratio=0.5):
    """공연별 출구 비중 → 출구별 평균 비중(합 100%). 자주 쓰인 출구만 따로, 나머지는 '그 밖의 출구'."""
    G = [r for r in shows if r.get("gates")]
    if not G:
        return {}, {}
    n = len(G)
    seen = {}
    for r in G:
        for k in r["gates"]:
            seen[k] = seen.get(k, 0) + 1
    main = [k for k, c in seen.items() if c >= main_ratio * n]
    rest = sorted((k for k in seen if k not in main), key=lambda k: -seen[k])
    per = {k: [] for k in main + [OTHER]}
    for r in G:
        sh = {k: v["share"] for k, v in r["gates"].items()}
        left = max(0.0, 1 - sum(sh.values()))   # 예전 결과처럼 작은 출구가 빠져 있으면 남은 몫도 '그 밖의 출구'로
        tot = sum(sh.values()) + left
        for k in main:
            per[k].append(sh.get(k, 0.0) / tot)
        per[OTHER].append((sum(v for k, v in sh.items() if k not in main) + left) / tot)
    mean = {k: float(np.mean(v)) for k, v in per.items()}
    if mean[OTHER] < 0.005:
        mean.pop(OTHER)
    pct = round_pct(mean)
    out = {}
    for k in sorted(mean, key=lambda k: (k == OTHER, -mean[k])):
        if k == OTHER:
            t = [v for r in G for kk, v in r["gates"].items() if kk not in main and "t50" in v]
            shows_k = sum(1 for r in G if any(kk not in main for kk in r["gates"]))
        else:
            t = [r["gates"][k] for r in G if k in r["gates"] and "t50" in r["gates"][k]]
            shows_k = seen[k]
        out[k] = {"shows": shows_k, "share": round(mean[k], 3), "pct": pct[k],
                  "p25": round(float(np.percentile(per[k], 25)), 3), "p75": round(float(np.percentile(per[k], 75)), 3),
                  "t50": q([x["t50"] for x in t], 50) if len(t) >= 3 else None,
                  "t90": q([x["t90"] for x in t], 50) if len(t) >= 3 else None}
        if k == OTHER:
            out[k]["members"] = [{"gate": g, "shows": seen[g]} for g in rest]
    meta = {"shows": n,
            "method": f"공연마다 출구별 비중(합 100%)을 구해 공연 평균. 안 쓰인 공연은 0%. 전체 공연의 "
                      f"{int(main_ratio * 100)}% 이상에서 쓰인 출구만 따로 보이고 나머지는 '{OTHER}'로 묶음",
            "range": "p25~p75 = 공연 4개 중 가운데 2개가 들어가는 범위"}
    return out, meta


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
    # 자료별로도 따로 (2024년 7월은 전체 기록, 2025년은 받은 만큼의 일부 기록이라 섞어 보면 치우칠 수 있음)
    summary["bySource"] = {}
    for src, g in S.groupby("src"):
        summary["bySource"][src] = {"shows": int(len(g)), "surgeMin": q(g.surgeMin, 50), "t50": q(g.t50, 50), "t90": q(g.t90, 50)}
    # 출구별 (2025만 출구 정보가 있음)
    gate_sum, gate_meta = aggregate_gates(shows)
    out = {
        "venue": "KSPO DOME", "built": pd.Timestamp.now().strftime("%Y-%m-%d"),
        "method": "시작 3시간 전~20분 뒤 입차, 2시간 넘게 머문 차를 관객 차로 보고, 출차가 몰리기 시작한 때부터 50%·90%가 빠지기까지 걸린 시간",
        "summary": summary, "gates": gate_sum, "gateMeta": gate_meta,
        "list": sorted(shows, key=lambda r: r["date"]),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    print("출구별:", json.dumps(out["gates"], ensure_ascii=False))
    print(f"저장 → {OUT}")


def regate_from_json():
    """원본 없이, 이미 저장된 공연별 결과(list)로 출구 집계만 다시 한다."""
    d = json.loads(OUT.read_text(encoding="utf-8"))
    d["gates"], d["gateMeta"] = aggregate_gates(d["list"])
    d["gateMeta"]["rebuilt"] = pd.Timestamp.now().strftime("%Y-%m-%d") + " (--from-json)"
    OUT.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print("출구별:", json.dumps(d["gates"], ensure_ascii=False))
    print("합계:", sum(v["pct"] for v in d["gates"].values()), "%")


if __name__ == "__main__":
    import sys
    regate_from_json() if "--from-json" in sys.argv else main()
