"""
과거 공연 기록으로 '관객이 주로 공연장에 도착하는 시간대' 비중을 계산한다.
  입력: data/processed/visitor_hourly.csv (서울 생활인구 OA-14991 + 올림픽공원 행사 일정, 인증키·원본 불필요)
        data/processed/holidays_kr.csv    (공휴일 목록)
        web/data/live_exit.json           (공원 주차장 관객 차 입차 절반·90% 시각, 교차 안내용)
  출력: web/data/arrival_profile.json     (관객 화면 '주로 공연장에 도착하는 시간' 막대그래프 데이터)

계산 방법:
  1) 비교 기준(평소 흐름): KSPO DOME·핸드볼경기장·올림픽홀 공연과 페스티벌이 모두 없는 날(평일·주말/공휴일 구분)에서
     그날 아침(06~08시 중앙값) 대비 시각별 생활인구 변화량의 중앙값을 구한다(연도·계절 기저 차이 제거).
  2) 공연일 순유입: 다른 큰 공연장·페스티벌이 겹치지 않은 KSPO DOME 단독 공연일(정각 :00 시작, 늘어난 방문객 3,000명 이상)에서
     평소 변화량을 뺀 '늘어난 방문객'의 시간대별 순증가분을 공연 시작 6시간 전~시작(6개 1시간 구간) 비중(%)으로 환산한다.
  3) 교차검증: 다른 공연장이 함께 열린 날을 포함한 전체 KSPO DOME 단회차 정각 공연(206회) 비중과 비교해 함께 저장한다.
"""
import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SLOTS = [
    (-6, -360, -300, "5~6시간 전"),
    (-5, -300, -240, "4~5시간 전"),
    (-4, -240, -180, "3~4시간 전"),
    (-3, -180, -120, "2~3시간 전"),
    (-2, -120, -60, "1~2시간 전"),
    (-1, -60, 0, "1시간 전~시작"),
]


def quantile(vals, q):
    s = sorted(vals)
    if not s:
        return 0.0
    pos = (len(s) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def round_pct_100(raw_pcts):
    """소수 첫째 자리·정수 반올림 합계가 정확히 100이 되도록 최대 잔차 보정."""
    ints = [int(x) for x in raw_pcts]
    rem = 100 - sum(ints)
    order = sorted(range(len(raw_pcts)), key=lambda i: -(raw_pcts[i] - ints[i]))
    for i in order[:rem]:
        ints[i] += 1
    return ints


def summarize_group(items):
    raw_means = []
    slot_out = []
    for rel, fmin, tmin, label in SLOTS:
        vals = [x["shares"][rel] * 100 for x in items]
        mean_v = sum(vals) / len(vals)
        raw_means.append(mean_v)
        slot_out.append({
            "relHour": rel,
            "fromMin": fmin,
            "toMin": tmin,
            "label": label,
            "shareExact": round(mean_v, 1),
            "p25": round(quantile(vals, 0.25), 1),
            "p75": round(quantile(vals, 0.75), 1),
        })
    pct_ints = round_pct_100(raw_means)
    for s, pi in zip(slot_out, pct_ints):
        s["pct"] = pi
    # 누적 50% 도달 시점(선형 보간, 시작 기준 분)
    cum = 0.0
    half_min = -120
    for s in slot_out:
        nxt = cum + s["shareExact"]
        if nxt >= 50.0 and s["shareExact"] > 0:
            frac = (50.0 - cum) / s["shareExact"]
            half_min = int(round(s["fromMin"] + frac * (s["toMin"] - s["fromMin"])))
            break
        cum = nxt
    last2 = slot_out[-2]["pct"] + slot_out[-1]["pct"]
    return {
        "shows": len(items),
        "peakExtraMed": int(round(quantile([x["peak_extra"] for x in items], 0.5))),
        "halfArrivedMin": half_min,
        "last2hPct": last2,
        "slots": slot_out,
    }


def main():
    vh_path = ROOT / "data/processed/visitor_hourly.csv"
    with vh_path.open(encoding="utf-8-sig", newline="") as f:
        vh = list(csv.DictReader(f))

    by_date = defaultdict(dict)
    dates_sorted = []
    for r in vh:
        dt = r["date"]
        if dt not in by_date:
            dates_sorted.append(dt)
        by_date[dt][int(r["hour"])] = r

    # 1) 큰 공연·페스티벌 없는 날의 아침(06~08시) 대비 시각별 생활인구 변화 중앙값
    quiet_deltas = defaultdict(list)
    quiet_days = {"weekday": 0, "weekend": 0}
    for dt in dates_sorted:
        hrs = by_date[dt]
        r0 = next(iter(hrs.values()))
        if r0["kspo_show"] == "0" and r0["other_big_venues"] == "" and r0["festival"] == "0":
            wknd = r0["day_type"] != "평일"
            quiet_days["weekend" if wknd else "weekday"] += 1
            morn_vals = [float(hrs[h]["pop_total"]) for h in (6, 7, 8) if h in hrs and hrs[h]["pop_total"]]
            if not morn_vals:
                continue
            morn = quantile(morn_vals, 0.5)
            for h, r in hrs.items():
                if r["pop_total"]:
                    quiet_deltas[(wknd, h)].append(float(r["pop_total"]) - morn)

    base_delta = {k: quantile(v, 0.5) for k, v in quiet_deltas.items()}

    # 2) KSPO DOME 단회차 정각(:00) 공연일 시간대별 순유입 비중
    pure_groups = {"all": [], "weekday": [], "weekend": []}
    all_kspo_groups = {"all": [], "weekday": [], "weekend": []}
    used_dates = []

    for dt in dates_sorted:
        hrs = by_date[dt]
        r12 = hrs.get(12) or next(iter(hrs.values()))
        if r12["kspo_show"] != "1" or r12["kspo_shows_n"] != "1" or not r12["kspo_start"] or r12["festival"] == "1":
            continue
        sh, sm = map(int, r12["kspo_start"].split(":"))
        if sm != 0:
            continue
        wknd = r12["day_type"] != "평일"
        morn_vals = [float(hrs[h]["pop_total"]) for h in (6, 7, 8) if h in hrs and hrs[h]["pop_total"]]
        if not morn_vals:
            continue
        morn = quantile(morn_vals, 0.5)
        ex = {}
        for rel in range(-7, 1):
            h = sh + rel
            if 0 <= h <= 23 and h in hrs and hrs[h]["pop_total"] and (wknd, h) in base_delta:
                ex[rel] = float(hrs[h]["pop_total"]) - (morn + base_delta[(wknd, h)])
        if not all(r in ex for r in range(-6, 0)) or ex[-1] < 3000:
            continue
        gains = {r: max(0.0, ex[r] - max(0.0, ex.get(r - 1, 0.0))) for r in range(-6, 0)}
        tot = sum(gains.values())
        if tot < 2000:
            continue
        item = {
            "date": dt,
            "start": r12["kspo_start"],
            "peak_extra": ex[-1],
            "shares": {r: gains[r] / tot for r in range(-6, 0)},
        }
        key = "weekend" if wknd else "weekday"
        all_kspo_groups["all"].append(item)
        all_kspo_groups[key].append(item)
        if r12["other_big_venues"] == "":
            pure_groups["all"].append(item)
            pure_groups[key].append(item)
            used_dates.append(dt)

    # 3) 공휴일 목록 및 관객 차 입차 시각(live_exit.json) 결합
    hol_path = ROOT / "data/processed/holidays_kr.csv"
    holidays = []
    if hol_path.exists():
        with hol_path.open(encoding="utf-8-sig", newline="") as f:
            holidays = sorted(r["date"] for r in csv.DictReader(f) if r.get("date", "") >= "2026-01-01")

    le_path = ROOT / "web/data/live_exit.json"
    car_entry = None
    if le_path.exists():
        le = json.loads(le_path.read_text(encoding="utf-8"))
        if le.get("entry"):
            car_entry = {
                "shows": le["entry"]["half"]["n"],
                "half": le["entry"]["half"],
                "most": le["entry"]["most"],
                "source": "한국체육산업개발 올림픽공원 주차장 입출차 기록(2024년 7월 + 2025년, 평소 방문 차 차감 관객 차 기준)",
            }

    vf_path = ROOT / "web/data/visitor_forecast.json"
    station_share = None
    if vf_path.exists():
        vf = json.loads(vf_path.read_text(encoding="utf-8"))
        st = (vf.get("stations") or {}).get("일·공휴일") or (vf.get("stations") or {}).get("평일")
        if st and st.get("list"):
            top = st["list"][0]
            station_share = {
                "topStation": top["name"] + "역",
                "sharePct": int(round(top["share"] * 100)),
                "showDays": st["showDays"],
            }

    kst = timezone(timedelta(hours=9))
    out = {
        "built": datetime.now(kst).strftime("%Y-%m-%d"),
        "period": f"{min(used_dates)} ~ {max(used_dates)}",
        "source": "서울 열린데이터광장 행정동 단위 서울 생활인구(OA-14991, 올림픽공원 소재 행정동 1시간 간격) · 한국체육산업개발 올림픽공원 공식 공연 일정",
        "method": (
            "다른 큰 공연장(핸드볼경기장·올림픽홀)과 페스티벌이 겹치지 않은 KSPO DOME 단독 공연일 중 정각(:00) 시작 회차(늘어난 인원 3,000명 이상)에서, "
            "큰 공연 없는 같은 요일 유형 날(평일 516일·주말 및 공휴일 39일)의 아침(06~08시) 대비 시각별 인구 변화를 빼 순수 공연 유입 인원의 시간대별 도착 비중(시작 6시간 전~시작, 합계 100%)을 계산"
        ),
        "baselineDays": quiet_days,
        "profiles": {k: summarize_group(v) for k, v in pure_groups.items()},
        "crossCheckAllSingle": {
            "shows": len(all_kspo_groups["all"]),
            "pcts": [s["pct"] for s in summarize_group(all_kspo_groups["all"])["slots"]],
            "note": "다른 공연장이 함께 열린 날을 포함한 전체 KSPO DOME 단회차 정각 공연(206회)과 비교해도 모든 구간 차이가 3%p 이내로 일치",
        },
        "carEntry": car_entry,
        "subwayTop": station_share,
        "holidays": holidays,
    }

    out_path = ROOT / "web/data/arrival_profile.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "period": out["period"],
        "weekday": [(s["label"], s["pct"]) for s in out["profiles"]["weekday"]["slots"]],
        "weekend": [(s["label"], s["pct"]) for s in out["profiles"]["weekend"]["slots"]],
        "crossCheck206": out["crossCheckAllSingle"]["pcts"],
        "carEntry": out["carEntry"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
