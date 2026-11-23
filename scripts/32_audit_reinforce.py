"""
데이터 검수 후 취소·휴연 오표기 회차(2024-10-14, 2025-01-04~05) 일괄 보정 스크립트.
외부 패키지(pandas·numpy) 없이 파이썬 표준 라이브러리만으로 실행되며,
data/processed/ 의 중간 집계표로부터 web/data/ 결과 JSON을 scripts/16, 24, 25, 30과 동일한 수식으로 재계산한다.

제외 대상:
  - 2024-10-14(월): 2024 오페라 투란도트 — 공식 일정상 월요일 휴연('14일 공연 없음', 공원 페이지 '월~금 19:30' 오표기)
  - 2025-01-04(토)~01-05(일): 로드 투 킹덤 : ACE OF ACE 콘서트 — 2024-12-02 주최 측 전 회차 사전 취소 발표
"""
import csv
import importlib
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

NO_SHOW_DATES = {"2024-10-14", "2025-01-04", "2025-01-05"}
MAIN = ["북2", "동2", "남2"]
ZONES = {"북2": ["P4", "P5"], "동2": ["P1B", "P2", "P테", "P그"], "남2": ["P1A", "P6", "P7"]}


def median(vals):
    s = sorted(vals)
    n = len(s)
    return 0.5 * (s[n // 2 - 1] + s[n // 2]) if n % 2 == 0 else s[n // 2]


def percentile(vals, p):
    """numpy.percentile 기본(linear) 방식과 동일한 백분위수."""
    s = sorted(vals)
    pos = (len(s) - 1) * (p / 100.0)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def sym_eig(A, tol=1e-12, max_sweeps=80):
    """대칭행렬 A(n×n) 고유분해(순환 Jacobi 방식, 표준 라이브러리 전용)."""
    n = len(A)
    D = [row[:] for row in A]
    V = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for _ in range(max_sweeps):
        off = sum(D[p][q] * D[p][q] for p in range(n) for q in range(p + 1, n))
        if math.sqrt(off) < tol:
            break
        for p in range(n):
            for q in range(p + 1, n):
                apq = D[p][q]
                if abs(apq) < 1e-15:
                    continue
                tau = (D[q][q] - D[p][p]) / (2.0 * apq)
                t = (1.0 / (tau + math.sqrt(1.0 + tau * tau))) if tau >= 0 else (-1.0 / (-tau + math.sqrt(1.0 + tau * tau)))
                c = 1.0 / math.sqrt(1.0 + t * t)
                s = t * c
                D[p][p] -= t * apq
                D[q][q] += t * apq
                D[p][q] = D[q][p] = 0.0
                for r in range(n):
                    if r != p and r != q:
                        drp, drq = D[r][p], D[r][q]
                        D[r][p] = D[p][r] = c * drp - s * drq
                        D[r][q] = D[q][r] = s * drp + c * drq
                for r in range(n):
                    vrp, vrq = V[r][p], V[r][q]
                    V[r][p] = c * vrp - s * vrq
                    V[r][q] = s * vrp + c * vrq
    return [D[i][i] for i in range(n)], V


def ols_pinv(X, y):
    """np.linalg.lstsq + np.linalg.pinv 와 동일한 최소제곱 계수·표준오차."""
    m, k = len(X), len(X[0])
    xtx = [[0.0] * k for _ in range(k)]
    xty = [0.0] * k
    for r in range(m):
        xr, yr = X[r], y[r]
        for i in range(k):
            xi = xr[i]
            if xi == 0.0:
                continue
            xty[i] += xi * yr
            for j in range(i, k):
                xtx[i][j] += xi * xr[j]
    for i in range(k):
        for j in range(i):
            xtx[i][j] = xtx[j][i]
    evals, V = sym_eig(xtx)
    cutoff = max(evals) * max(m, k) * 1e-12
    rank = sum(1 for ev in evals if ev > cutoff)
    pinv_diag = [1.0 / ev if ev > cutoff else 0.0 for ev in evals]
    diag_pinv = [
        sum(V[i][l] * V[i][l] * pinv_diag[l] for l in range(k) if pinv_diag[l] != 0.0)
        for i in range(k)
    ]
    vt_xty = [sum(V[j][l] * xty[j] for j in range(k)) * pinv_diag[l] for l in range(k)]
    b = [sum(V[i][l] * vt_xty[l] for l in range(k)) for i in range(k)]
    rss = sum((y[r] - sum(X[r][j] * b[j] for j in range(k) if X[r][j] != 0.0)) ** 2 for r in range(m))
    s2 = rss / (m - rank)
    se = [math.sqrt(max(0.0, s2 * diag_pinv[i])) for i in range(k)]
    return b, se


def filter_csv(path, pred):
    with path.open(encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        fields = r.fieldnames
        rows = [row for row in r if pred(row)]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return rows


def rebuild_aud_cars(show_cars_rows):
    """scripts/24_vehicle_use.py 의 대관 정산 인원 매칭을 보정된 공연일 기준으로 다시 계산."""
    ev_path = ROOT / "data/processed/event_days.csv"
    rent_path = ROOT / "data/raw/kspo_rent_info.csv"
    out_path = ROOT / "data/processed/aud_cars.csv"
    with ev_path.open(encoding="utf-8-sig", newline="") as f:
        kspo_dates = sorted({r["날짜"] for r in csv.DictReader(f) if r["공연장"] == "KSPO DOME"})
    by_date = {r["date"]: r for r in show_cars_rows}

    with rent_path.open(encoding="utf-8-sig", newline="") as f:
        rr = csv.reader(f)
        next(rr, None)
        rent_rows = list(rr)

    matched = []
    seen_dates = set()
    for q in rent_rows:
        fac, name, beg, end, act_raw = q[2], q[5], q[6], q[7], q[10]
        if "KSPO" not in fac or not act_raw.strip():
            continue
        act = float(act_raw)
        if act <= 0:
            continue
        b_s = str(int(float(beg)))
        e_s = str(int(float(end)))
        b_iso = f"{b_s[:4]}-{b_s[4:6]}-{b_s[6:8]}"
        e_iso = f"{e_s[:4]}-{e_s[4:6]}-{e_s[6:8]}"
        sd = [d for d in kspo_dates if b_iso <= d <= e_iso]
        if not sd:
            continue
        per = act / len(sd)
        for dt_iso in sd:
            if dt_iso in by_date and dt_iso not in seen_dates:
                seen_dates.add(dt_iso)
                z = by_date[dt_iso]
                matched.append({
                    "date": dt_iso,
                    "name": name,
                    "per": round(per, 1),
                    "act": round(act, 1),
                    "nshow": len(sd),
                    "cars": int(z["cars"]),
                    "net": round(float(z["net"]), 1),
                    "start": z["start"],
                })
    fields = ["date", "name", "per", "act", "nshow", "cars", "net", "start"]
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(matched)
    return matched


def clean_visitor_hourly():
    vh_path = ROOT / "data/processed/visitor_hourly.csv"
    with vh_path.open(encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        fields = r.fieldnames
        rows = list(r)
    changed = 0
    for row in rows:
        if row["date"] in NO_SHOW_DATES and row["kspo_show"] == "1":
            row["kspo_show"] = "0"
            row["kspo_title"] = ""
            row["kspo_start"] = ""
            row["kspo_shows_n"] = "0"
            row["kspo_rel_min"] = ""
            row["show_on"] = "0"
            vn = max(0, int(float(row["venues_n"] or 0)) - 1)
            st = max(0.0, float(row["seats_total"] or 0) - 15000.0)
            row["venues_n"] = str(vn)
            row["seats_total"] = f"{st:.1f}"
            changed += 1
    if changed:
        with vh_path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
    return changed


def rebuild_exit_gate(pairs_rows, wx_rows, show_cars_rows, today_kst):
    gate_path = ROOT / "web/data/exit_gate.json"
    eg = json.loads(gate_path.read_text(encoding="utf-8"))

    # 1) byEntry 재계산
    by_entry = {}
    for g in MAIN:
        sub = [r for r in pairs_rows if r["gin"] == g]
        q = {}
        n_sum = {o: 0 for o in MAIN}
        for r in sub:
            q.setdefault(r["date"], {})[r["gout"]] = float(r["median"])
            n_sum[r["gout"]] = n_sum.get(r["gout"], 0) + int(r["size"])
        opts = []
        for o in MAIN:
            others = [x for x in MAIN if x != o]
            vs = {}
            for x in others:
                diffs = [d[o] - d[x] for d in q.values() if o in d and x in d]
                if diffs:
                    vs[x] = {
                        "min": round(median(diffs), 1),
                        "fasterShare": round(sum(1 for v in diffs if v < 0) / len(diffs), 2),
                        "n": len(diffs),
                    }
            opts.append({
                "gate": o,
                "cars": n_sum.get(o, 0),
                "shows": sum(1 for d in q.values() if o in d),
                "vs": vs,
            })
        best = min(opts, key=lambda o: sum(v["min"] for v in o["vs"].values()))
        by_entry[g] = {"zones": ZONES[g], "best": best["gate"], "options": opts}

    # 2) weather 회귀·요약 재계산
    hours = sorted({r["start"][:2] for r in wx_rows})
    h_cols = hours[1:]
    z_cols = ["c"] + h_cols + ["wet", "cold", "we", "n100"]
    X = [
        [1.0]
        + [1.0 if r["start"][:2] == h else 0.0 for h in h_cols]
        + [
            1.0 if r["wet"] == "True" else 0.0,
            1.0 if r["cold"] == "True" else 0.0,
            1.0 if r["we"] == "True" else 0.0,
            float(r["n"]) / 100.0,
        ]
        for r in wx_rows
    ]
    effect = {}
    for yname in ("p50", "p90"):
        yv = [float(r[yname]) for r in wx_rows]
        b, se = ols_pinv(X, yv)
        for c in ("wet", "cold"):
            i = z_cols.index(c)
            effect.setdefault(c, {})[yname] = {
                "min": round(b[i], 1),
                "lo": round(b[i] - 1.96 * se[i], 1),
                "hi": round(b[i] + 1.96 * se[i], 1),
            }

    titles = sorted({r["title"] for r in wx_rows})
    t_cols = titles[1:]
    max_date = {}
    cnt_title = {}
    for r in wx_rows:
        t = r["title"]
        max_date[t] = max(max_date.get(t, ""), r["date"])
        cnt_title[t] = cnt_title.get(t, 0) + 1
    t_design_cols = ["c"] + t_cols + ["st", "we", "wet", "cold", "last", "n100"]
    XT = [
        [1.0]
        + [1.0 if r["title"] == tc else 0.0 for tc in t_cols]
        + [
            float(int(r["start"][:2])),
            1.0 if r["we"] == "True" else 0.0,
            1.0 if r["wet"] == "True" else 0.0,
            1.0 if r["cold"] == "True" else 0.0,
            1.0 if r["date"] == max_date[r["title"]] else 0.0,
            float(r["n"]) / 100.0,
        ]
        for r in wx_rows
    ]
    tour = {}
    for yname in ("p50", "p90"):
        yv = [float(r[yname]) for r in wx_rows]
        b, se = ols_pinv(XT, yv)
        for c in ("wet", "cold"):
            i = t_design_cols.index(c)
            tour.setdefault(c, {})[yname] = {
                "min": round(b[i], 1),
                "lo": round(b[i] - 1.96 * se[i], 1),
                "hi": round(b[i] + 1.96 * se[i], 1),
            }
    multi_rows = [r for r in wx_rows if cnt_title[r["title"]] > 1]
    for c in ("wet", "cold"):
        by_t = {}
        for r in multi_rows:
            by_t.setdefault(r["title"], []).append(r[c] == "True")
        tour[c]["tours"] = sum(1 for vs in by_t.values() if 0 < sum(vs) < len(vs))
        tour[c]["shows"] = sum(1 for r in multi_rows if r[c] == "True")

    win = [r for r in wx_rows if int(r["date"][5:7]) in (12, 1, 2)]
    win_cold = [r for r in win if r["cold"] == "True"]
    win_mild = [r for r in win if r["cold"] != "True"]
    winter = {
        "shows": len(win),
        "cold": len(win_cold),
        "coldP50": round(median([float(r["p50"]) for r in win_cold]), 0),
        "mildP50": round(median([float(r["p50"]) for r in win_mild]), 0),
        "coldP90": round(median([float(r["p90"]) for r in win_cold]), 0),
        "mildP90": round(median([float(r["p90"]) for r in win_mild]), 0),
    }
    wet_rows = [r for r in wx_rows if r["wet"] == "True"]
    dry_rows = [r for r in wx_rows if r["wet"] != "True"]
    after_end = importlib.import_module("30_exit_after_end").compute_after_end(ROOT, write_csv=True)

    eg["built"] = today_kst
    eg["shows"] = len(wx_rows)
    eg["cars"] = sum(int(r["cars"]) for r in show_cars_rows)
    eg["byEntry"] = by_entry
    eg["weather"] = {
        "shows": len(wx_rows),
        "wetShows": len(wet_rows),
        "coldShows": sum(1 for r in wx_rows if r["cold"] == "True"),
        "winter": winter,
        "effectTour": tour,
        "period": f"{min(r['date'] for r in wx_rows)} ~ {max(r['date'] for r in wx_rows)}",
        "effect": effect,
        "wetMedian": {
            "p50": round(median([float(r["p50"]) for r in wet_rows]), 0),
            "p90": round(median([float(r["p90"]) for r in wet_rows]), 0),
        },
        "dryMedian": {
            "p50": round(median([float(r["p50"]) for r in dry_rows]), 0),
            "p90": round(median([float(r["p90"]) for r in dry_rows]), 0),
        },
        "afterEnd": after_end,
    }
    gate_path.write_text(json.dumps(eg, ensure_ascii=False), encoding="utf-8")
    return eg


def rebuild_kspo_waves(today_kst):
    p = ROOT / "web/data/kspo_waves.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    waves = [w for w in d["list"] if w["date"] not in NO_SHOW_DATES]
    lags = [w["lagMin"] for w in waves]
    peaks = [w["peak15"] for w in waves]
    by_src = {}
    for w in waves:
        by_src[w["src"]] = by_src.get(w["src"], 0) + 1
    d["built"] = today_kst
    d["list"] = waves
    d["summary"] = {
        "n": len(waves),
        "bySource": by_src,
        "share2025": None,
        "skipped2025": [],
        "lagMed": int(median(lags)),
        "lagLo": int(percentile(lags, 10)),
        "lagHi": int(percentile(lags, 90)),
        "peakLo": int(percentile(peaks, 10)),
        "peakMed": int(median(peaks)),
        "peakHi": int(percentile(peaks, 90)),
        "rangeNote": "공연별 10~90% 범위",
    }
    label = f"2024년 3월~2025년 12월 {len(waves)}회"
    d["label"] = label
    d["source"] = f"한국체육산업개발 '올림픽공원 차량 이용현황'(문화 빅데이터 플랫폼) KSPO DOME 공연 {label}(사전 취소·휴연 오표기 제외), 빠진 달 없음·보정 없음"
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return d["summary"]


def clean_exit_curves_and_audience_car(today_kst):
    ec_path = ROOT / "web/data/exit_curves.json"
    ec = json.loads(ec_path.read_text(encoding="utf-8"))
    if "13:00" in ec.get("groups", {}):
        g13 = ec["groups"]["13:00"]
        if [x["date"] for x in g13.get("dates", [])] == ["2025-01-05"]:
            del ec["groups"]["13:00"]
            n24 = sum(sum(1 for x in g["dates"] if x["date"][:4] == "2024") for g in ec["groups"].values())
            n25 = sum(sum(1 for x in g["dates"] if x["date"][:4] == "2025") for g in ec["groups"].values())
            old_label = ec.get("label", "")
            ec["label"] = f"2024년 7월 {n24}회 + 2025년 {n25}회"
            if old_label and old_label in ec.get("source", ""):
                ec["source"] = ec["source"].replace(old_label, ec["label"])
            ec["built"] = today_kst
            ec_path.write_text(json.dumps(ec, ensure_ascii=False, indent=1), encoding="utf-8")

    ac_path = ROOT / "web/data/audience_car.json"
    ac = json.loads(ac_path.read_text(encoding="utf-8"))
    before = len(ac.get("shows", []))
    ac["shows"] = [s for s in ac.get("shows", []) if s.get("date") not in NO_SHOW_DATES]
    if len(ac["shows"]) != before:
        ac_path.write_text(json.dumps(ac, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    kst = timezone(timedelta(hours=9))
    today_kst = datetime.now(kst).strftime("%Y-%m-%d")

    wx_rows = filter_csv(ROOT / "data/processed/exit_weather_shows.csv", lambda r: r["date"] not in NO_SHOW_DATES)
    pairs_rows = filter_csv(ROOT / "data/processed/exit_gate_pairs.csv", lambda r: r["date"] not in NO_SHOW_DATES)
    sc_rows = filter_csv(ROOT / "data/processed/show_cars_vhcle.csv", lambda r: r["date"] not in NO_SHOW_DATES)
    aud_rows = rebuild_aud_cars(sc_rows)
    vh_changed = clean_visitor_hourly()

    eg = rebuild_exit_gate(pairs_rows, wx_rows, sc_rows, today_kst)
    waves_sum = rebuild_kspo_waves(today_kst)
    clean_exit_curves_and_audience_car(today_kst)
    importlib.import_module("31_arrival_profile").main()

    print(
        json.dumps(
            {
                "exit_gate_shows": eg["shows"],
                "exit_gate_cars": eg["cars"],
                "aud_cars_rows": len(aud_rows),
                "visitor_hourly_rows_cleaned": vh_changed,
                "kspo_waves": waves_sum,
                "effectTour": eg["weather"]["effectTour"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
