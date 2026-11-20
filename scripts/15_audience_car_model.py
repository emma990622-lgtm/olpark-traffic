"""
관객 성향(연령·성별)과 자가용 이용의 관계를 공연별 다중회귀분석으로 본다.

입력
  data/raw/seoul_living_pop_11710566.csv  서울시 행정동 단위 생활인구(내국인), 서울 열린데이터광장 OA-14991,
                                          올림픽공원이 있는 행정동(코드 11710566)만, 2024-06 ~ 2025-12, 시간대별·성별·5세 연령대별
                                          (olpark-collector 저장소 data/seoul-pop 갈래의 GitHub Actions로 받음, 인증키 필요 없음)
  data/processed/event_days.csv            공연 일정
  관객 차 대수 (둘 중 하나)
    - data/raw/kcisa_inout_2025.jsonl + parking_inout_202407.csv 가 있으면 직접 센다(2025는 받은 비율로 보정, inout_common.py.
      65,535줄로 잘린 8·9월, 관객 차 입차 시간대를 90% 넘게 못 받은 10~12월 공연은 뺀다)
    - 없으면 전에 원본으로 센 값(web/data/audience_car.json)을, 그것도 없으면 exit_profile.json의 cars(보정 없음)를 쓴다
출력
  web/data/audience_car.json

방법
  1) 관객 구성: 공연 날 공연 시간(시작 시각부터 3시간대) 생활인구 − 평소 같은 요일 생활인구(공원 큰 공연이 없는 날, 앞뒤 5주
     안 같은 요일의 중앙값; 모자라면 9·13·20주까지 넓힘). 늘어난 사람을 성별·연령대로 나눠 '관객 구성'으로 본다.
     늘어난 사람이 3,000명 미만이거나 비교일이 3일 미만이면(대부분 토요일 — 평소 토요일에도 공연이 있어서) 뺀다.
  2) 관객 차: scripts/09와 같은 기준(시작 3시간 전~20분 뒤 입차, 2시간 넘게 머물고 시작 1.5~7시간 사이 출차한 차).
  3) 회귀식: ln(관객 차) = b0 + b1·(평균 나이/10) + b2·(여성 비율) + b3·(금요일 여부)
     - 공연마다 관객 수를 알 수 없어(연계 데이터의 관람객수 칸이 비어 있음) '1명이 차로 올 확률'은 직접 못 구한다.
       대신 '같은 조건에서 관객 차가 몇 % 늘고 주는지'로 해석한다.
     - 오차 범위: 같은 가수 공연끼리 묶어 다시 뽑는 부트스트랩(3,000번) 95% 구간. 정확도: 한 공연씩 빼고 맞혀 보기.

  실행: python scripts\\15_audience_car_model.py
"""
import json
import math
from datetime import datetime, timedelta, timezone
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inout_common as ic  # noqa: E402

ROOT = ic.ROOT
POP = ROOT / "data" / "raw" / "seoul_living_pop_11710566.csv"
EXIT = ROOT / "web" / "data" / "exit_profile.json"
OUT = ROOT / "web" / "data" / "audience_car.json"
MIN_EXCESS, MIN_BASE = 3000, 3
SHOW_HOURS = 3
# 공휴일(일요일처럼 본다) 2024-06 ~ 2025-12
HOLIDAYS = set("""2024-06-06 2024-08-15 2024-09-16 2024-09-17 2024-09-18 2024-10-01 2024-10-03 2024-10-09 2024-12-25
2025-01-01 2025-01-27 2025-01-28 2025-01-29 2025-01-30 2025-03-03 2025-05-05 2025-05-06 2025-06-03 2025-06-06
2025-08-15 2025-10-03 2025-10-06 2025-10-07 2025-10-08 2025-10-09 2025-12-25""".split())
AGE_BANDS = [("10대 이하", 0, 20), ("20대", 20, 30), ("30대", 30, 40), ("40대", 40, 50), ("50대 이상", 50, 200)]
STOP = {"concert", "tour", "live", "world", "in", "seoul", "the", "fan", "con", "콘서트", "서울", "단독", "앵콜", "투어",
        "special", "asia", "encore", "앙코르", "of", "and", "기념", "전국", "공연", "주년", "2026", "2027", "2025", "2024",
        "연말", "신년", "크리스마스", "발매", "앨범", "쇼케이스", "팬미팅", "팬콘서트", "fan-con", "meet-up", "anniversary",
        "best", "showcase", "arena", "party", "festival", "페스티벌", "edition", "final", "앵콜"}


def day_type(t):
    s = t.strftime("%Y-%m-%d")
    if s in HOLIDAYS or t.dayofweek == 6:
        return "sun"
    return {4: "fri", 5: "sat"}.get(t.dayofweek, "wk")


def t_sf(t, df):
    """t 분포 한쪽 꼬리 확률(scipy가 없어도 되게 직접 계산)"""
    try:
        from scipy import stats
        return float(stats.t.sf(t, df))
    except ImportError:
        x = df / (df + t * t)
        return 0.5 * betainc(df / 2, 0.5, x) if t > 0 else 1 - 0.5 * betainc(df / 2, 0.5, x)


def betainc(a, b, x):
    """정규화 불완전 베타 함수 (Numerical Recipes 연분수)"""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbt = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x)
    if x > (a + 1) / (a + b + 2):
        return 1 - betainc(b, a, 1 - x)
    c, d, f = 1.0, 1 - (a + b) * x / (a + 1), 0.0
    d = 1 / (d if abs(d) > 1e-30 else 1e-30)
    f = d
    for m in range(1, 300):
        for num in (m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m)), -(a + m) * (a + b + m) * x / ((a + 2 * m) * (a + 2 * m + 1))):
            d = 1 + num * d
            d = 1 / (d if abs(d) > 1e-30 else 1e-30)
            c = 1 + num / c
            c = c if abs(c) > 1e-30 else 1e-30
            f *= c * d
            if num < 0 and abs(c * d - 1) < 1e-12:
                return math.exp(lbt) * f / a
    return math.exp(lbt) * f / a


def t_ppf(p, df):
    """t 분포 분위수(이분법)"""
    lo, hi = 0.0, 20.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if 1 - t_sf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def ols(y, X):
    X = np.column_stack([np.ones(len(y))] + X)
    n, k = X.shape
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    e = y - X @ b
    s2 = float(e @ e / (n - k))
    XtXi = np.linalg.inv(X.T @ X)
    se = np.sqrt(np.diag(s2 * XtXi))
    p = [2 * t_sf(abs(bb / ss), n - k) for bb, ss in zip(b, se)]
    r2 = 1 - float(e @ e) / float((y - y.mean()) @ (y - y.mean()))
    h = np.einsum("ij,jk,ik->i", X, XtXi, X)
    loo = e / (1 - h)
    null_loo = (y - y.mean()) * n / (n - 1)
    return {"b": b, "se": se, "p": p, "r2": r2, "s2": s2, "XtXi": XtXi, "df": n - k, "n": n,
            "looRmse": float(np.sqrt((loo ** 2).mean())), "nullRmse": float(np.sqrt((null_loo ** 2).mean())),
            "looAbsPct": float(np.median(np.abs(np.expm1(loo))))}


def tokens(title):
    t = re.sub(r"[\[\]［］〈〉<>‘’“”\"'＂()（）:：,·\-–—~!?＆&/]", " ", str(title)).lower()
    return {w for w in t.split() if len(w) >= 2 and w not in STOP and not re.fullmatch(r"\d+(th|rd|st|nd)?|\d{4}", w)}


def composition():
    pop = pd.read_csv(POP, dtype={"기준일ID": str, "행정동코드": str})
    grp = [c for c in pop.columns if c.startswith(("남자", "여자"))]
    lo_age = {g: int(re.search(r"(\d+)세", g).group(1)) for g in grp}
    span = {g: (10 if "0세부터9세" in g else 5 if "부터" in g else 10) for g in grp}   # 70세 이상은 75로 둔다
    mid = {g: lo_age[g] + span[g] / 2 for g in grp}
    cube = {k: g.set_index("시간대구분")[grp].sort_index() for k, g in pop.groupby("기준일ID")}
    days = pd.DataFrame({"k": sorted(cube)})
    days["t"] = pd.to_datetime(days.k)
    days["ty"] = days.t.map(day_type)
    big = ic.big_event_days()
    days["big"] = days.t.dt.strftime("%Y-%m-%d").isin(big)
    ev = pd.read_csv(ic.EVENTS, encoding="utf-8-sig")
    other = ev[ev["공연장"].isin(["핸드볼경기장", "올림픽홀"])].groupby("날짜").size().to_dict()
    rows = []
    for day, start, title in ic.kspo_shows("2024-06"):
        k = day.replace("-", "")
        if k not in cube:
            continue
        t = pd.Timestamp(day)
        ty = day_type(t)
        for W in (35, 63, 91, 140):
            m = (abs((days.t - t).dt.days) <= W) & (days.ty == ty) & ~days.big
            if m.sum() >= MIN_BASE:
                break
        h = int(start[:2])
        H = [x for x in range(h, h + SHOW_HOURS) if x <= 23]
        row = {"date": day, "start": start, "title": title, "dayType": ty, "baseDays": int(m.sum()), "baseWindowDays": W,
               "otherVenues": int(other.get(day, 0))}
        if m.sum() < MIN_BASE:
            rows.append(row | {"ok": False, "why": "비교할 평소 같은 요일이 모자람"})
            continue
        base = pd.concat([cube[d] for d in days[m].k]).groupby(level=0).median()
        exc = (cube[k].loc[H] - base.loc[H]).mean()
        total = float(exc.sum())
        pos = exc.clip(lower=0)
        row |= {"excess": round(total)}
        if total < MIN_EXCESS:
            rows.append(row | {"ok": False, "why": f"늘어난 사람이 {MIN_EXCESS:,}명 미만"})
            continue
        female = float(pos[[g for g in grp if g.startswith("여자")]].sum() / pos.sum())
        ages = {name: round(float(pos[[g for g in grp if a <= lo_age[g] < b]].sum() / pos.sum()), 3) for name, a, b in AGE_BANDS}
        mean_age = float((pos * pd.Series(mid)).sum() / pos.sum())
        rows.append(row | {"ok": True, "female": round(female, 3), "ages": ages, "meanAge": round(mean_age, 1)})
    return rows


def cars_by_show():
    """{날짜: (대수, 출처)}"""
    raw = ic.RAW / "kcisa_inout_2025.jsonl"
    if raw.exists() and (ic.RAW / "parking_inout_202407.csv").exists():
        d, cov, got = ic.load_all()
        if ic.enough_2025(cov):                            # 못 받은 번호 덩어리가 없으면 원본에서 직접 센다
            d["day"] = d.in_time.dt.strftime("%Y-%m-%d")
            by = dict(tuple(d.groupby("day")))
            out, skipped = {}, []
            for day, start, _ in ic.kspo_shows("2024-07"):
                if day not in by:
                    continue
                s = pd.Timestamp(f"{day} {start}")
                wt, ok, _ = ic.show_weights(by[day], s, before=180, after=20)   # 관객 차 입차 시간대
                if not ok:
                    skipped.append(day)
                    continue
                w, n = ic.audience_cars(by[day].assign(w=wt), day, start)
                if n >= 100 and w == w:
                    out[day] = (round(w), "raw-weighted" if day >= "2025" else "raw")
            if skipped:
                print(f"※ 관객 차를 못 센 2025 공연 {len(skipped)}회(잘린 달·빈 시간대): {', '.join(skipped)}")
            return out, f"입출차 원본에서 직접 셈. {ic.note_2025(cov)}"
    # 원본이 없는 곳(클라우드 등): 전에 원본으로 센 값이 있으면 그대로 쓴다
    if OUT.exists():
        prev = json.loads(OUT.read_text(encoding="utf-8"))
        old = {r["date"]: (r["cars"], r["carsSrc"]) for r in prev.get("shows", [])
               if r.get("cars") and r.get("carsSrc") in ("raw", "raw-weighted")}
        if old:
            return old, prev["sources"]["cars"]
    ex = json.loads(EXIT.read_text(encoding="utf-8"))
    out = {r["date"]: (r["cars"], "exit_profile") for r in ex["list"]}
    return out, "출차 분석(exit_profile.json)의 공연별 관객 차 대수(2025는 받은 만큼 그대로, 보정 없음)"


def main():
    comp = composition()
    cars, cars_src = cars_by_show()
    for r in comp:
        if r["date"] in cars:
            r["cars"], r["carsSrc"] = cars[r["date"]]
    D = pd.DataFrame([r for r in comp if r.get("ok") and r.get("cars")])
    D = D[D.dayType.isin(["fri", "sun"])].reset_index(drop=True)      # 평일(월~목) 공연은 관객 차 기록이 없거나 매우 적음
    y = np.log(D.cars.values.astype(float))
    X = [D.meanAge.values / 10, D.female.values, (D.dayType == "fri").astype(float).values]
    names = ["age10", "female", "fri"]
    fit = ols(y, X)

    # 같은 가수끼리 묶어 부트스트랩
    D["artist"] = D.title.map(lambda s: " ".join(sorted(tokens(s)))[:20])
    arts = D.artist.unique()
    rng = np.random.default_rng(20261120)
    boots = []
    for _ in range(3000):
        pick = rng.choice(arts, len(arts))
        x = pd.concat([D[D.artist == a] for a in pick])
        if x.dayType.nunique() < 2 or len(x) < 8:
            continue
        try:
            boots.append(ols(np.log(x.cars.values.astype(float)),
                             [x.meanAge.values / 10, x.female.values, (x.dayType == "fri").astype(float).values])["b"])
        except np.linalg.LinAlgError:
            pass
    boots = np.array(boots)
    coef = {}
    labels = {"age10": "관객 평균 나이 10살 많을 때", "female": "여성 비율 10%p 높을 때", "fri": "금요일 공연(주말 대비)"}
    unit = {"age10": 1.0, "female": 0.1, "fri": 1.0}
    for i, nm in enumerate(names, start=1):
        lo, hi = np.percentile(boots[:, i], [2.5, 97.5])
        u = unit[nm]
        coef[nm] = {"label": labels[nm], "b": round(float(fit["b"][i]), 4), "se": round(float(fit["se"][i]), 4),
                    "p": round(float(fit["p"][i]), 4), "bootLo": round(float(lo), 4), "bootHi": round(float(hi), 4),
                    "pct": round(math.expm1(fit["b"][i] * u) * 100), "pctLo": round(math.expm1(lo * u) * 100),
                    "pctHi": round(math.expm1(hi * u) * 100)}
    improve = 1 - fit["looRmse"] / fit["nullRmse"]
    meaningful = bool(coef["age10"]["p"] < 0.05 and coef["age10"]["bootLo"] > 0 and improve >= 0.1)
    t80 = t_ppf(0.9, fit["df"])

    def predict(mean_age, female, fri):
        x = np.array([1.0, mean_age / 10, female, float(fri)])
        m = float(x @ fit["b"])
        s = math.sqrt(fit["s2"] * (1 + float(x @ fit["XtXi"] @ x)))
        return round(math.exp(m)), round(math.exp(m - t80 * s)), round(math.exp(m + t80 * s))

    # 앞으로 열릴 KSPO DOME 공연: 같은 가수의 지난 공연 관객 구성이 있으면 예상 관객 차를 붙인다
    events = json.loads((ROOT / "web" / "data" / "events.json").read_text(encoding="utf-8"))
    past = [r for r in comp if r.get("ok")]
    upcoming = []
    today = (datetime.now(timezone.utc) + timedelta(hours=9)).strftime("%Y-%m-%d")   # 한국 날짜(시간대 자료 없이)
    for e in events:
        if e.get("venue") != "KSPO DOME" or not e.get("times") or e["date"] < today:
            continue
        tk = tokens(e["title"])
        match = [r for r in past if tk & tokens(r["title"]) and r["date"] < e["date"]]
        if not match:
            upcoming.append({"date": e["date"], "title": e["title"], "match": []})
            continue
        ma = float(np.mean([r["meanAge"] for r in match]))
        fe = float(np.mean([r["female"] for r in match]))
        ty = day_type(pd.Timestamp(e["date"]))
        pred, lo, hi = predict(ma, fe, ty in ("fri", "wk"))
        upcoming.append({"date": e["date"], "title": e["title"], "dayType": ty,
                         "match": [{"date": r["date"], "title": r["title"]} for r in match][-4:],
                         "meanAge": round(ma, 1), "female": round(fe, 3),
                         "ages": {k: round(float(np.mean([r["ages"][k] for r in match])), 3) for k, _, _ in AGE_BANDS},
                         "pred": pred, "lo": lo, "hi": hi})

    presets = []
    for label, ma, fe in [("10~20대 여성 팬 중심 (아이돌 공연 등)", 25, 0.92), ("20~30대 중심, 남녀 섞임", 30, 0.70),
                          ("30~40대 중심", 38, 0.75), ("50대 이상 중심 (트로트·원로 가수 등)", 55, 0.80)]:
        presets.append({"label": label, "meanAge": ma, "female": fe,
                        "sun": dict(zip(["pred", "lo", "hi"], predict(ma, fe, False))),
                        "fri": dict(zip(["pred", "lo", "hi"], predict(ma, fe, True)))})

    out = {
        "built": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "meaningful": meaningful,
        "sources": {
            "population": "서울시 행정동 단위 생활인구(내국인), 서울 열린데이터광장 OA-14991 · 올림픽공원이 있는 행정동(코드 11710566) · KT 통신 자료 기반 추정",
            "populationPeriod": "2024-06 ~ 2025-12",
            "cars": cars_src,
            "events": "올림픽공원 공식 행사 일정",
        },
        "method": {
            "composition": (f"공연 날 공연 시간(시작부터 {SHOW_HOURS}시간대) 생활인구에서 평소 같은 요일(공원 큰 공연이 없는 날, 앞뒤 5주 안팎) "
                            "중앙값을 뺀 '늘어난 사람'을 성별·연령대로 나눔"),
            "cars": "시작 3시간 전~20분 뒤에 들어와 2시간 넘게 머문 공원 주차장 차(관객 차로 봄)",
            "model": "ln(관객 차) = b0 + b1·(평균 나이 ÷ 10) + b2·(여성 비율) + b3·(금요일이면 1)",
            "ci": "같은 가수 공연끼리 묶어 다시 뽑는 부트스트랩 3,000번, 95% 구간",
            "excluded": "토요일 공연(평소 토요일에도 공연이 있어 비교할 날이 거의 없음), 늘어난 사람이 3,000명 미만인 날, 월~목 공연",
            "limits": ("공연별 관객 수를 몰라 '관객 1명이 차로 올 확률'은 직접 구하지 못했고, 같은 조건에서 관객 차가 몇 % 늘고 주는지로 해석함. "
                       "생활인구는 통신 자료로 추정한 값이라 같은 날 다른 공연장 관객도 섞일 수 있음. 주차장이 차면(2,120면) 더 오는 차는 세지 못함."),
        },
        "model": {
            "n": fit["n"], "artists": int(len(arts)), "r2": round(fit["r2"], 3),
            "looRmse": round(fit["looRmse"], 3), "nullRmse": round(fit["nullRmse"], 3), "improve": round(improve, 3),
            "looMedianErrPct": round(fit["looAbsPct"] * 100),
            "b": [round(float(v), 5) for v in fit["b"]], "s2": round(fit["s2"], 5),
            "XtXi": [[round(float(v), 6) for v in r] for r in fit["XtXi"]], "t80": round(t80, 4),
            "coef": coef,
        },
        "presets": presets,
        "upcoming": upcoming,
        "shows": comp,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"관객 구성 계산된 공연 {sum(1 for r in comp if r.get('ok'))}회 / 회귀에 쓴 공연 {fit['n']}회(가수 {len(arts)}팀), 관객 차: {cars_src}")
    print(f"R² {fit['r2']:.2f}, 한 공연씩 빼고 맞혀 본 오차 {fit['looRmse']:.3f} (평균만 쓸 때 {fit['nullRmse']:.3f}, {improve:.0%} 줄어듦)")
    for nm, c in coef.items():
        print(f"  {c['label']}: 관객 차 {c['pct']:+d}% (95% {c['pctLo']:+d}~{c['pctHi']:+d}%), p={c['p']:.3f}")
    print("의미 있는 결과" if meaningful else "아직 뚜렷하지 않음", "→", OUT)
    for u in upcoming:
        if u["match"]:
            print(f"  {u['date']} {u['title'][:24]}: 평균 {u['meanAge']}세, 예상 관객 차 {u['pred']}대 ({u['lo']}~{u['hi']})")


if __name__ == "__main__":
    main()
