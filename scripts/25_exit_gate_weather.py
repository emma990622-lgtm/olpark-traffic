"""
관객용 '내 주차 위치 → 빠른 출구'와 '날씨에 따라 출차가 늦어지나' 분석.
  입력: data/raw/vhcle_use/*.csv  문화 빅데이터 플랫폼 '올림픽공원 차량 이용현황'(차마다 입구·출구·분 단위 시각, 주인 PC에만)
        data/raw/weather_asos_108.csv  기상청 ASOS 서울 시간자료(scripts/26, 있으면 우선) / 없으면 visitor_weather/weather_hourly_openmeteo.csv(2024-06~)
  출력: web/data/exit_gate.json, data/processed/exit_gate_pairs.csv, data/processed/exit_weather_shows.csv
  관객 차 = 시작 3시간 전~20분 뒤 입차, 2시간 넘게 머물고 시작 1.5~7시간 뒤 출차 (KSPO DOME 공연, 하루 한 회차인 날)
  주차 위치는 자료에 없어 '들어온 문'으로 대신한다(공식 주차 안내: 북2문 P4·P5 / 동2문 P1B·P2·P테·P그 / 남2문 P1A·P6·P7).
  출구 비교: 같은 공연·같은 입구 안에서 출구별 출차 시각 중앙값을 비교(공연마다 끝나는 시각이 달라 공연 안에서만 비교) → 공연들의 중앙값.
  날씨: 출차 시간대(시작 2.5~4.5시간 뒤) 비 합 1mm 이상 = 비 온 공연, 체감온도 평균 0도 미만 = 추운 공연.
        출차 절반·90% 시각을 요일 유형·시작 시각·관객 차 대수를 함께 넣은 회귀로 비교(effect),
        그리고 같은 공연(투어)끼리 비교(공연명 고정효과 + 막공 여부, effectTour) — 공연 길이가 날씨와 섞이는 것을 막는 쪽이 기본.
"""
import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import inout_common as ic  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MAIN = ["북2", "동2", "남2"]
ZONES = {"북2": ["P4", "P5"], "동2": ["P1B", "P2", "P테", "P그"], "남2": ["P1A", "P6", "P7"]}
WAY = {"북2": "올림픽대교·천호 방향(북쪽)", "동2": "길동·강동 방향(동쪽), 올림픽공원역 앞", "남2": "가락·잠실 방향(남쪽, 위례성대로)"}


def load(days):
    best = {}
    for f in sorted(glob.glob(str(ROOT / "data/raw/vhcle_use/*VHCLE*.csv"))):
        x = pd.read_csv(f, encoding="utf-8-sig")
        x.columns = ["dd", "vid", "tin", "gin", "tout", "gout"]
        x = x[x.dd.isin(days)]                      # 공연일만(속도)
        for m, g in x.groupby(x.dd.str[:7]):
            if m not in best or len(g) > len(best[m]):   # 같은 달이 두 파일에 있으면 줄이 많은 쪽
                best[m] = g
    if not best:
        raise SystemExit("data/raw/vhcle_use/에 차량 이용현황 파일이 없습니다(또는 공연일 기록 없음)")
    d = pd.concat([g.drop_duplicates() for g in best.values()], ignore_index=True).drop(columns="dd")
    d["tin"] = pd.to_datetime(d.tin, errors="coerce")
    d["tout"] = pd.to_datetime(d.tout, errors="coerce")
    d["day"] = d.tin.dt.normalize()
    return d, sorted(best)


def audience(d, shows):
    rows = []
    byday = dict(tuple(d.groupby("day")))
    for date, st, title in shows:
        s = pd.Timestamp(f"{date} {st}")
        x = byday.get(s.normalize())
        if x is None or len(x) < 500:
            continue
        im = (x.tin - s).dt.total_seconds() / 60
        om = (x.tout - s).dt.total_seconds() / 60
        a = x[(im >= -180) & (im <= 20) & (om - im >= 120) & (om >= 90) & (om <= 420)].copy()
        a["om"] = om[a.index]
        a["date"], a["start"], a["title"] = date, st, title
        rows.append(a[["date", "start", "title", "gin", "gout", "om"]])
    return pd.concat(rows, ignore_index=True)


def gate_advice(A):
    M = A[A.gin.isin(MAIN) & A.gout.isin(MAIN)]
    P = M.groupby(["date", "gin", "gout"]).om.agg(["size", "median"]).reset_index()
    P = P[P["size"] >= 10]
    P.to_csv(ROOT / "data/processed/exit_gate_pairs.csv", index=False, encoding="utf-8-sig")
    out = {}
    for g in MAIN:
        q = P[P.gin == g].pivot(index="date", columns="gout", values="median")
        n = P[P.gin == g].groupby("gout")["size"].sum()
        opts = []
        for o in MAIN:
            others = [x for x in MAIN if x != o]
            diffs = {x: (q[o] - q[x]).dropna() for x in others if o in q and x in q}
            opts.append({"gate": o, "cars": int(n.get(o, 0)), "shows": int(q[o].notna().sum()) if o in q else 0,
                         "vs": {x: {"min": round(float(v.median()), 1), "fasterShare": round(float((v < 0).mean()), 2), "n": int(len(v))}
                                for x, v in diffs.items()}})
        # 추천 = 다른 두 출구보다 중앙값이 가장 빠른(차이 합이 가장 작은) 출구
        best = min(opts, key=lambda o: sum(v["min"] for v in o["vs"].values()))
        out[g] = {"zones": ZONES[g], "best": best["gate"], "options": opts}
    # 출구별 혼잡: 공연 하나에서 그 출구로 나간 관객 차, 90%가 빠진 시각(공연 전체 90% 시각과의 차이)
    G = M.groupby(["date", "gout"]).om.agg(n="size", p90=lambda s: s.quantile(0.9)).reset_index()
    G = G.join(M.groupby("date").om.quantile(0.9).rename("s90"), on="date")
    G["d90"] = G.p90 - G.s90
    load_ = {o: {"carsPerShow": int(G[G.gout == o].n.median()), "late90": round(float(G[G.gout == o].d90.median()), 1)} for o in MAIN}
    other = {}
    for g in ["서2", "서1", "남3", "남4"]:
        x = A[A.gin == g]
        if len(x):
            other[g] = {"cars": int(len(x)), "sameGate": round(float((x.gout == g).mean()), 3)}
    return out, load_, other


ASOS = ROOT / "data/raw/weather_asos_108.csv"


def load_weather():
    """기상청 ASOS 서울(108) 시간자료가 있으면 그것(공공데이터), 없으면 Open-Meteo 재분석. (표[rain, feels], 출처 문구)"""
    if ASOS.exists():
        W = pd.read_csv(ASOS, encoding="utf-8-sig")
        W["t"] = pd.to_datetime(W.tm)
        W = W.set_index("t").rename(columns={"rn": "rain"})
        W["rain"] = W.rain.fillna(0)
        return W[["rain", "feels"]], "기상청 지상관측(ASOS) 시간자료, 서울(108) 지점 — 공공데이터포털"
    W = pd.read_csv(ROOT / "data/raw/visitor_weather/weather_hourly_openmeteo.csv")
    W["t"] = pd.to_datetime(W.time)
    W = W.set_index("t").drop(columns=["rain"]).rename(columns={"precipitation": "rain", "apparent_temperature": "feels"})
    return W[["rain", "feels"]], "Open-Meteo 과거 기상(재분석, 올림픽공원 좌표) — 기상청 관측(ASOS)으로 바꿀 예정"


def weather(A):
    M = A[A.gout.isin(MAIN)]
    S = M.groupby(["date", "start", "title"]).om.agg(n="size", p50="median", p90=lambda s: s.quantile(0.9)).reset_index()
    W, _ = load_weather()
    rain, feels = [], []
    for _, r in S.iterrows():
        s = pd.Timestamp(f"{r.date} {r.start}")
        w = W.loc[s + pd.Timedelta(minutes=150): s + pd.Timedelta(minutes=270)]
        rain.append(w.rain.sum() if len(w) else np.nan)
        feels.append(w.feels.mean() if len(w) else np.nan)
    S["rain"], S["feels"] = rain, feels
    S = S.dropna(subset=["rain"]).copy()
    S["wet"] = S.rain >= 1.0
    S["cold"] = S.feels < 0
    S["we"] = pd.to_datetime(S.date).dt.dayofweek >= 5
    S.round(2).to_csv(ROOT / "data/processed/exit_weather_shows.csv", index=False, encoding="utf-8-sig")
    Z = pd.get_dummies(S.start.str[:2].astype("category"), drop_first=True).astype(float)
    for c in ["wet", "cold", "we"]:
        Z[c] = S[c].astype(float).values
    Z["n100"] = S.n.values / 100
    Z.insert(0, "c", 1.0)
    X = Z.values
    res = {}
    for y in ["p50", "p90"]:
        b = np.linalg.lstsq(X, S[y].values, rcond=None)[0]
        e = S[y].values - X @ b
        se = np.sqrt(np.diag(e @ e / (len(e) - X.shape[1]) * np.linalg.inv(X.T @ X)))
        for c in ["wet", "cold"]:
            i = list(Z.columns).index(c)
            res.setdefault(c, {})[y] = {"min": round(float(b[i]), 1), "lo": round(float(b[i] - 1.96 * se[i]), 1), "hi": round(float(b[i] + 1.96 * se[i]), 1)}
    # 같은 공연(투어)끼리 비교: 공연마다 길이가 달라(연말 공연이 김) 날씨와 섞이므로 공연명 고정효과 + 막공 여부
    T = pd.get_dummies(S.title, drop_first=True).astype(float)
    T["st"] = S.start.str[:2].astype(int).values
    T["we"] = S.we.astype(float).values
    for c in ["wet", "cold"]:
        T[c] = S[c].astype(float).values
    T["last"] = (S.groupby("title").date.transform("max") == S.date).astype(float).values
    T["n100"] = S.n.values / 100
    T.insert(0, "c", 1.0)
    XT = T.values
    tour = {}
    for y in ["p50", "p90"]:
        b = np.linalg.lstsq(XT, S[y].values, rcond=None)[0]
        e = S[y].values - XT @ b
        dof = len(e) - np.linalg.matrix_rank(XT)
        se = np.sqrt(np.diag(e @ e / dof * np.linalg.pinv(XT.T @ XT)))
        for c in ["wet", "cold"]:
            i = list(T.columns).index(c)
            tour.setdefault(c, {})[y] = {"min": round(float(b[i]), 1), "lo": round(float(b[i] - 1.96 * se[i]), 1), "hi": round(float(b[i] + 1.96 * se[i]), 1)}
    multi = S.groupby("title").date.transform("size") > 1
    for c in ["wet", "cold"]:
        g = S[multi].groupby("title")[c].agg(["sum", "size"])
        tour[c]["tours"] = int(((g["sum"] > 0) & (g["sum"] < g["size"])).sum())
        tour[c]["shows"] = int(S[multi & S[c]].shape[0])
    win = S[pd.to_datetime(S.date).dt.month.isin([12, 1, 2])]          # 추위는 겨울 공연(연말 공연 등)과 겹쳐서 겨울끼리도 비교
    winter = {"shows": int(len(win)), "cold": int(win.cold.sum()),
              "coldP50": round(float(win[win.cold].p50.median()), 0), "mildP50": round(float(win[~win.cold].p50.median()), 0),
              "coldP90": round(float(win[win.cold].p90.median()), 0), "mildP90": round(float(win[~win.cold].p90.median()), 0)}
    return {"shows": int(len(S)), "wetShows": int(S.wet.sum()), "coldShows": int(S.cold.sum()), "winter": winter, "effectTour": tour,
            "period": f"{S.date.min()} ~ {S.date.max()}", "effect": res,
            "wetMedian": {"p50": round(float(S[S.wet].p50.median()), 0), "p90": round(float(S[S.wet].p90.median()), 0)},
            "dryMedian": {"p50": round(float(S[~S.wet].p50.median()), 0), "p90": round(float(S[~S.wet].p90.median()), 0)}}


def main():
    shows = ic.kspo_shows("2024-03")
    d, months = load({x[0] for x in shows})
    A = audience(d, shows)
    adv, load_, other = gate_advice(A)
    wx = weather(A)
    out = {"built": pd.Timestamp.now(tz="Asia/Seoul").strftime("%Y-%m-%d"),
           "source": f"한국체육산업개발 '올림픽공원 차량 이용현황'(문화 빅데이터 플랫폼, {months[0]}~{months[-1]}), 차마다 들어온 문·나간 문·시각(분)",
           "shows": int(A.date.nunique()), "cars": int(len(A)),
           "method": "KSPO DOME 공연 관객 차(시작 3시간 전~20분 뒤 입차, 2시간 넘게 머물고 시작 1.5~7시간 뒤 출차). 주차 위치는 들어온 문으로 대신함. "
                     "같은 공연·같은 입구 안에서 출구별 출차 시각 중앙값을 비교한 뒤 공연들의 중앙값(공연마다 끝나는 시각이 달라서)",
           "byEntry": adv, "gateLoad": load_, "otherLots": other, "way": WAY,
           "weather": wx, "weatherSource": load_weather()[1]}
    p = ROOT / "web/data/exit_gate.json"
    p.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ["shows", "cars", "byEntry", "gateLoad", "otherLots", "weather"]}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
