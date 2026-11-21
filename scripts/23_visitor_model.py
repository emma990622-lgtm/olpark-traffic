"""
방문객 혼잡도 예측 모형과 분산 안내용 자료를 만든다. 입력은 data/processed/visitor_hourly.csv 하나(인증키·원본 불필요).

1) 시간별 방문객(올림픽공원 동 생활인구) 모형 — 화면에서 날짜·공연·날씨 예보를 넣어 바로 계산할 수 있게 계수를 내보낸다.
   ln(생활인구) = [요일 유형 × 시각] + [월] + [KSPO DOME 공연: 시작 기준 −6~+5시간] + [다른 큰 공연장: 시간대 3구간]
                 + [페스티벌] + [비(0.5mm 이상)·큰비(3mm 이상)·추위(체감 0도 미만)·더위(체감 30도 이상), 9~21시만]
   - 최소제곱(numpy). 새 꾸러미 없음.
   - 검증: 2025년까지로 맞추고 2026년 1~7월을 맞혀 봄(시간 순서 검증). 비교 기준 = 같은 요일 유형·시각의 과거 중앙값.
2) 하루 지하철 하차(주변 5역 합) 모형 — 공연·비·추위·더위가 하루 방문객을 몇 % 바꾸는지.
3) 역별 쏠림 — KSPO DOME 공연일에 평소(큰 공연 없는 같은 요일 유형)보다 늘어난 하차 인원이 어느 역에 몰리는지.
4) 혼잡 단계 기준 — 과거 10~22시 생활인구의 50·80·95% 값.

출력: web/data/visitor_forecast.json
  실행: python scripts/23_visitor_model.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "processed" / "visitor_hourly.csv"
OUT = ROOT / "web" / "data" / "visitor_forecast.json"
DT = ["평일", "토", "일·공휴일"]
RELS = list(range(-6, 6))
BLOCKS = {"12-15": (12, 15), "16-19": (16, 19), "20-22": (20, 22)}
WX_HOURS = (9, 21)
SPLIT = "2026-01-01"
T0 = pd.Timestamp("2024-06-01")


def design(d, trend):
    """모형 칸(화면 visitor.js의 predict와 똑같아야 한다)"""
    cols, X = [], []
    add = lambda name, v: (cols.append(name), X.append(np.asarray(v, dtype=float)))
    for t in DT:
        for h in range(24):
            add(f"base|{t}|{h}", (d.day_type == t) & (d.hour == h))
    for m in range(2, 13):
        add(f"month|{m}", d.month == m)
    if trend:
        add("trend", d.years)
    for r in RELS:
        add(f"show|{r}", (d.kspo_show == 1) & (d.rel == r))
    for k, (a, b) in BLOCKS.items():
        add(f"other|{k}", (d.other_big == 1) & d.hour.between(a, b))
    add("festival", (d.festival == 1) & d.hour.between(10, 21))
    wx = d.hour.between(*WX_HOURS)
    add("rain", wx & (d.precip_mm >= 0.5))
    add("heavy", wx & (d.precip_mm >= 3))
    add("cold", wx & (d.feels_c < 0))
    add("hot", wx & (d.feels_c >= 30))
    return cols, np.column_stack(X)


def fit(d, trend):
    cols, X = design(d, trend)
    y = np.log(d.pop_total.values)
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    res = y - X @ b
    dof = max(1, len(y) - np.linalg.matrix_rank(X))
    cov = np.linalg.pinv(X.T @ X) * (res @ res / dof)
    return dict(zip(cols, b)), dict(zip(cols, np.sqrt(np.diag(cov)))), res


def predict(d, coef, trend):
    cols, X = design(d, trend)
    return np.exp(X @ np.array([coef.get(c, 0.0) for c in cols]))


def mape(a, p):
    return round(float(np.mean(np.abs(p - a) / a)) * 100, 1)


def pct(b):
    return round((float(np.exp(b)) - 1) * 100, 1)


def main():
    d = pd.read_csv(SRC, encoding="utf-8-sig")
    d["ts"] = pd.to_datetime(d.dt)
    d["month"] = d.ts.dt.month
    d["years"] = (d.ts - T0).dt.total_seconds() / (365.25 * 86400)
    d["rel"] = np.floor(d.kspo_rel_min / 60)
    d["other_big"] = (d.other_big_venues.fillna("") != "").astype(int)
    h = d.dropna(subset=["pop_total", "precip_mm", "feels_c"]).copy()
    h = h[h.pop_total > 0]

    # ---- 1) 시간별 모형: 시간 순서 검증 ----
    tr, te = h[h.dt < SPLIT], h[h.dt >= SPLIT]
    base = tr.groupby(["day_type", "hour"]).pop_total.median()
    p_base = te.set_index(["day_type", "hour"]).index.map(base).values.astype(float)
    day = te.hour.between(10, 22).values
    showwin = ((te.kspo_show == 1) & te.rel.between(-6, 5)).values
    trials = {}
    for trend in (False, True):
        c, _, _ = fit(tr, trend)
        p = predict(te, c, trend)
        trials[trend] = {"all": mape(te.pop_total.values[day], p[day]), "show": mape(te.pop_total.values[showwin], p[showwin]), "p": p}
    trend = trials[True]["show"] < trials[False]["show"]
    p = trials[trend]["p"]
    a = te.pop_total.values
    # 공연일 가장 붐비는 시각을 맞혔나(그날 10~22시 예측 최고 시각과 실제 최고 시각 차이)
    te2 = te.assign(p=p)
    pk = []
    for _, g in te2[(te2.kspo_show == 1) & te2.hour.between(10, 22)].groupby("date"):
        if len(g) >= 12:
            pk.append(abs(int(g.hour.iloc[g.p.values.argmax()]) - int(g.hour.iloc[g.pop_total.values.argmax()])))
    valid = {"train": f"{tr.dt.min()[:10]} ~ {tr.dt.max()[:10]}", "test": f"{te.dt.min()[:10]} ~ {te.dt.max()[:10]}",
             "testHours": int(day.sum()), "showHours": int(showwin.sum()), "showDays": len(pk),
             "mapeAll": trials[trend]["all"], "mapeAllBase": mape(a[day], p_base[day]),
             "mapeShow": trials[trend]["show"], "mapeShowBase": mape(a[showwin], p_base[showwin]),
             "peakHourWithin1": round(float(np.mean(np.array(pk) <= 1)), 2) if pk else None,
             "trendUsed": bool(trend)}

    coef, se, res = fit(h, trend)                                     # 화면에 쓸 계수는 모든 자료로
    sw = ((h.kspo_show == 1) & h.rel.between(-6, 5)).values
    q = lambda v, x: round(float(np.percentile(v, x)), 3)
    lv_src = h[h.hour.between(10, 22)].pop_total
    eff = lambda k, label: {"label": label, "pct": pct(coef[k]), "lo": pct(coef[k] - 1.96 * se[k]), "hi": pct(coef[k] + 1.96 * se[k])}
    hourly = {
        "base": {t: [round(float(coef[f"base|{t}|{x}"]), 4) for x in range(24)] for t in DT},
        "month": [0.0] + [round(float(coef[f"month|{m}"]), 4) for m in range(2, 13)],
        "trend": round(float(coef.get("trend", 0.0)), 5), "trendFrom": T0.strftime("%Y-%m-%d"),
        "trendCapYears": round(float(h.years.max()), 3),
        "show": {str(r): round(float(coef[f"show|{r}"]), 4) for r in RELS},
        "other": {k: round(float(coef[f"other|{k}"]), 4) for k in BLOCKS},
        "festival": round(float(coef["festival"]), 4),
        "rain": round(float(coef["rain"]), 4), "heavy": round(float(coef["heavy"]), 4),
        "cold": round(float(coef["cold"]), 4), "hot": round(float(coef["hot"]), 4),
        "wxHours": list(WX_HOURS), "residShow": {"lo": q(res[sw], 10), "hi": q(res[sw], 90)}, "resid": {"lo": q(res, 10), "hi": q(res, 90)},
        "n": int(len(h)), "period": f"{h.dt.min()[:10]} ~ {h.dt.max()[:10]}",
        "effects": [eff("show|-1", "KSPO DOME 공연 시작 1시간 전"), eff("show|0", "공연 시작 시각"), eff("show|-3", "공연 시작 3시간 전"),
                    eff("other|16-19", "다른 큰 공연장 공연(16~19시)"), eff("festival", "페스티벌(10~21시)"),
                    eff("rain", "비(시간당 0.5mm 이상)"), eff("heavy", "큰비(3mm 이상, 비 효과에 더해짐)"),
                    eff("cold", "추위(체감 0도 미만)"), eff("hot", "더위(체감 30도 이상)")],
    }
    levels = {"p50": int(lv_src.quantile(0.5)), "p80": int(lv_src.quantile(0.8)), "p95": int(lv_src.quantile(0.95)),
              "note": "과거 10~22시 생활인구의 50·80·95% 값. 절반 미만 = 여유, 80% 미만 = 보통, 95% 미만 = 붐빔, 그 이상 = 매우 붐빔"}

    # ---- 2) 하루 지하철 하차 모형 ----
    wx = d[d.hour.between(*WX_HOURS)].groupby("date").agg(rain_sum=("precip_mm", "sum"), feels_max=("feels_c", "max"), feels_min=("feels_c", "min"))
    g = d.groupby("date").agg(day_type=("day_type", "first"), month=("month", "first"), years=("years", "first"), show=("kspo_show", "max"),
                              other=("other_big", "max"), fest=("festival", "max"), off=("subway_off_total", "first")).join(wx).dropna(subset=["off", "rain_sum"])
    g = g[g.off > 0]
    cols = [f"dt|{t}" for t in DT] + [f"month|{m}" for m in range(2, 13)] + ["trend", "show", "other", "fest", "rain", "cold", "hot"]
    X = np.column_stack([(g.day_type == t).values for t in DT] + [(g.month == m).values for m in range(2, 13)] +
                        [g.years.values, g.show.values, g.other.values, g.fest.values, (g.rain_sum >= 5).values, (g.feels_max < 0).values, (g.feels_max >= 30).values]).astype(float)
    y = np.log(g.off.values)
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    r = y - X @ b
    cv = np.linalg.pinv(X.T @ X) * (r @ r / (len(y) - X.shape[1]))
    s = np.sqrt(np.diag(cv))
    ix = {c: i for i, c in enumerate(cols)}
    de = lambda k, label: {"label": label, "pct": pct(b[ix[k]]), "lo": pct(b[ix[k]] - 1.96 * s[ix[k]]), "hi": pct(b[ix[k]] + 1.96 * s[ix[k]])}
    daily = {"n": int(len(g)), "period": f"{g.index.min()} ~ {g.index.max()}",
             "r2": round(float(1 - (r @ r) / ((y - y.mean()) @ (y - y.mean()))), 2),
             "effects": [de("show", "KSPO DOME 공연이 있는 날"), de("other", "다른 큰 공연장(핸드볼경기장·올림픽홀) 공연이 있는 날"), de("fest", "페스티벌이 있는 날"),
                         de("rain", "비 오는 날(9~21시 합 5mm 이상)"), de("cold", "추운 날(낮 체감 최고 0도 미만)"), de("hot", "더운 날(낮 체감 최고 30도 이상)")]}

    # ---- 3) 역별 쏠림 ----
    st_cols = [c for c in d.columns if c.startswith("subway_off_") and c != "subway_off_total"]
    dd = d.groupby("date").agg(day_type=("day_type", "first"), show=("kspo_show", "max"), other=("other_big", "max"), fest=("festival", "max"),
                               **{c: (c, "first") for c in st_cols}).dropna(subset=st_cols, how="all")
    quiet = dd[(dd.show == 0) & (dd.other == 0) & (dd.fest == 0)]
    stations = {}
    for t in DT:
        s_show, s_base = dd[(dd.show == 1) & (dd.day_type == t)], quiet[quiet.day_type == t]
        if len(s_show) < 5 or len(s_base) < 5:
            continue
        ex = {c[len("subway_off_"):]: max(0.0, float(s_show[c].median() - s_base[c].median())) for c in st_cols}
        tot = sum(ex.values()) or 1
        stations[t] = {"showDays": int(len(s_show)), "baseDays": int(len(s_base)),
                       "list": sorted([{"name": k, "base": int(s_base[f"subway_off_{k}"].median()), "show": int(s_show[f"subway_off_{k}"].median()),
                                        "extra": int(round(v)), "share": round(v / tot, 3)} for k, v in ex.items()], key=lambda x: -x["share"])}

    hol = pd.read_csv(ROOT / "data" / "processed" / "holidays_kr.csv", encoding="utf-8-sig")
    out = {"built": pd.Timestamp.now().strftime("%Y-%m-%d"),
           "source": "올림픽공원이 있는 행정동의 서울 생활인구(시간별, 통신 자료 기반 추정) · 주변 5개 역 지하철 하차(일별) · 올림픽공원 행사 일정 · Open-Meteo 과거 기상(재분석)",
           "scopeNote": "생활인구는 공원 방문객만이 아니라 그 동에 있는 모든 사람(주민·직장인 포함)이에요. 공연의 영향은 평소와의 차이로 봐요.",
           "method": "ln(생활인구)를 요일 유형×시각, 월, 공연 시작 기준 시간, 다른 공연장, 페스티벌, 비·추위·더위로 설명하는 회귀(최소제곱)",
           "hourly": hourly, "valid": valid, "levels": levels, "daily": daily, "stations": stations,
           "holidays": sorted(hol[hol.date >= "2026-01-01"].date.tolist()),
           "weatherApi": {"lat": 37.5207, "lon": 127.1214, "note": "날씨 예보: 서울시 실시간 도시데이터(올림픽공원), 24시간 앞까지. 추위·더위는 예보 기온으로 봄(체감온도 예보 없음)"}}
    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"시간별 모형: {hourly['n']:,}시간({hourly['period']}), 검증 {valid['test']} 공연 시간대 오차 {valid['mapeShow']}% (기준 {valid['mapeShowBase']}%), "
          f"낮 전체 {valid['mapeAll']}% (기준 {valid['mapeAllBase']}%), 가장 붐비는 시각 ±1시간 적중 {valid['peakHourWithin1']} ({valid['showDays']}일), 추세 사용 {trend}")
    print("효과:", ", ".join(f"{e['label']} {e['pct']:+}%" for e in hourly["effects"]))
    print(f"하루 지하철({daily['n']}일, R² {daily['r2']}):", ", ".join(f"{e['label']} {e['pct']:+}%({e['lo']:+}~{e['hi']:+})" for e in daily["effects"]))
    for t, v in stations.items():
        print(f"역별 쏠림 {t}(공연 {v['showDays']}일/평소 {v['baseDays']}일):", ", ".join(f"{x['name']} {x['share']:.0%}(+{x['extra']:,})" for x in v["list"]))
    print(f"혼잡 단계: {levels['p50']:,} / {levels['p80']:,} / {levels['p95']:,} → {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
