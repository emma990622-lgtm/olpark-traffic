"""
운영자 화면 '공연 후 출차 곡선'용: KSPO DOME 공연일과 큰 공연 없는 날의 15분 출차 흐름(12:00 ~ 다음날 01:00).
예전에는 2024년 7월 하루치 곡선(exits_2024_07.json)만 썼다. 이제 2024년 7월 + 2025년 공연을 시작 시각별로 묶어
중앙값과 가운데 50% 범위를 내고, 비교 기준도 같은 요일 유형(평일 / 주말·공휴일)의 큰 공연 없는 날 중앙값으로 바꾼다.

입력: data/raw/parking_inout_202407.csv (2024년 7월 전체)
      data/raw/kcisa_inout_2025.jsonl   (2025년, 못 받은 번호 덩어리가 없을 때만 씀. 받은 비율로 보정 → inout_common.py)
      data/processed/event_days.csv
출력: web/data/exit_curves.json
기준
  - 공원 주차장 동2문·남2문·북2문 구역(2024년 7월 자료와 같은 구역): 2025는 이 세 곳으로 들어온 차만
  - 0분·24시간 이상 주차는 뺀다(scripts/04와 같게)
  - 2025: 65,535줄로 잘린 8·9월은 뺀다. 시간순 저장인 10~12월은 그날 06~24시 입차 기록을 90% 넘게 받은 날만
  - 큰 공연 없는 날 = KSPO DOME·핸드볼경기장·올림픽홀에 공연이 없는 날
  - 입차 곡선도 같은 방식(15분마다 들어온 차). 공연 그룹마다 '실제' 관객 차 절반·90%가 들어온/빠진 시각(중앙값),
    전체 공연으로 '예상'(공연 시작 시각만 보고 미리 예측하는 값, 시작 기준 분의 25·50·75%)을 함께 저장
    - 출차 절반·90%: scripts/09 방식(출차가 몰리기 시작한 때 + 그때부터 절반·90%가 빠지기까지), 모든 출입구
    - 입차 절반·90%: inout_common.entry_timing(시작 6시간 전~30분 뒤 입차한 관객 차), 모든 출입구

  실행: python scripts\\18_exit_curves.py
"""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inout_common as ic  # noqa: E402

OUT = ic.ROOT / "web" / "data" / "exit_curves.json"
_spec = importlib.util.spec_from_file_location("ep", ic.ROOT / "scripts" / "09_exit_profile.py")
ep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ep)             # 출차 절반·90% 시각을 scripts/09와 똑같이 재려고
SLOT_START, SLOT_MIN, N_SLOTS = "12:00", 15, 52          # 12:00 ~ 다음날 00:45 시작 구간


day_kind = ic.day_kind


def curve(x, day, col="out_time"):
    """그날 12:00 ~ 다음날 01:00 15분 출차(col=out_time) 또는 입차(col=in_time) 가중 대수"""
    s = pd.Timestamp(f"{day} {SLOT_START}")
    i = ((x[col] - s).dt.total_seconds() // (SLOT_MIN * 60)).astype(int).values
    m = (i >= 0) & (i < N_SLOTS)
    return np.bincount(i[m], weights=x.w.values[m], minlength=N_SLOTS)[:N_SLOTS]


def timing(dall, day, start, aud):
    """공연 하나의 관객 차 출차 절반·90%(09 방식)와 입차 절반·90%(시작 기준 분). 못 재면 None"""
    s = pd.Timestamp(f"{day} {start}")
    x = dall[(dall.oday == day) | (dall.iday == day)]
    r = {}
    if ic.ordered_ok(x, s, 180, 20)[0]:
        prof = ep.analyze(x[x.oday == day], day, start)
        if prof:
            r["exit50"], r["exit90"] = prof["surgeMin"] + prof["t50"], prof["surgeMin"] + prof["t90"]
    e = aud.entry(day, start)                 # 평소에도 있는 차를 뺀 관객 차 기준
    if e:
        r["in50"], r["in90"] = e["in50"], e["in90"]
    return r


KEYS = ("in50", "in90", "exit50", "exit90")


def stats(curves):
    a = np.array(curves)
    r = lambda q: [int(round(v)) for v in np.percentile(a, q, axis=0)]
    return {"med": r(50), "p25": r(25), "p75": r(75)}


def main():
    d24 = ic.load_2024()
    d25, cov = ic.load_2025()
    use25 = ic.enough_2025(cov)
    d = pd.concat([d24, d25] if use25 else [d24], ignore_index=True)
    aud = ic.Audience(d)
    dall = d[["in_time", "out_time", "gate", "src", "ord"]].copy()     # 절반·90% 시각용(모든 출입구, 09와 같게)
    dall["iday"] = dall.in_time.dt.strftime("%Y-%m-%d")
    dall["oday"] = dall.out_time.dt.strftime("%Y-%m-%d")
    dur = (d.out_time - d.in_time).dt.total_seconds() / 60
    d = d[(dur > 0) & (dur < 24 * 60) & ((d.src == "2024") | d.igate.isin(ic.MAIN_GATES))]
    d = d.sort_values("out_time").reset_index(drop=True)
    ot = d.out_time.values
    d_in = d.sort_values("in_time").reset_index(drop=True)
    it = d_in.in_time.values

    shows = {day: (start, title) for day, start, title in ic.kspo_shows("2024-07")}
    big = ic.big_event_days()
    days = sorted(set(d.in_time.dt.strftime("%Y-%m-%d")))
    show_rows, base = [], {"weekday": [], "weekend": []}
    base_src = {"weekday": {"2024": 0, "2025": 0}, "weekend": {"2024": 0, "2025": 0}}
    skipped = []
    for day in days:
        if day < "2024-07-01":
            continue
        s = pd.Timestamp(f"{day} {SLOT_START}")
        lo, hi = np.searchsorted(ot, np.datetime64(s), "left"), np.searchsorted(ot, np.datetime64(s + pd.Timedelta(hours=13)), "left")
        x = d.iloc[lo:hi]
        if len(x) < 300:
            continue
        w, ok, _ = ic.show_weights(x, pd.Timestamp(f"{day} 06:00"), before=0, after=18 * 60)
        if not ok:
            if day in shows and day >= "2025":
                skipped.append(day)
            continue
        c = curve(x.assign(w=w), day)
        if day in shows:
            start, title = shows[day]
            k = int(c.argmax())
            # 입차는 그날 12:00 ~ 다음날 01:00 사이에 '들어온' 차(나간 시각과 상관없이)
            lo2 = np.searchsorted(it, np.datetime64(s), "left")
            hi2 = np.searchsorted(it, np.datetime64(s + pd.Timedelta(hours=13)), "left")
            xi = d_in.iloc[lo2:hi2]
            wi, oki, _ = ic.show_weights(xi, pd.Timestamp(f"{day} 06:00"), before=0, after=18 * 60)
            show_rows.append({"date": day, "start": start, "title": title, "src": day[:4], "kind": day_kind(day),
                              "peak15": int(round(c[k])), "peakTime": (s + pd.Timedelta(minutes=SLOT_MIN * k)).strftime("%H:%M"),
                              "exits": [int(round(v)) for v in c],
                              "entries": [int(round(v)) for v in curve(xi.assign(w=wi), day, "in_time")] if oki else None,
                              **timing(dall, day, start, aud)})
        elif day not in big:
            base[day_kind(day)].append(c)
            base_src[day_kind(day)][day[:4]] += 1
    if not show_rows:
        raise SystemExit("계산할 공연일이 없습니다.")

    med = lambda v: int(round(float(np.median(v))))
    groups = {}
    for start in sorted({r["start"] for r in show_rows}):
        g = [r for r in show_rows if r["start"] == start]
        ent = [r["entries"] for r in g if r["entries"]]
        es = stats(ent) if ent else None
        actual = {k: {"med": med([r[k] for r in g if k in r]), "n": sum(k in r for r in g)} for k in KEYS if any(k in r for r in g)}
        groups[start] = {"n": len(g), "bySource": {"2024": sum(r["src"] == "2024" for r in g), "2025": sum(r["src"] == "2025" for r in g)},
                         **stats([r["exits"] for r in g]),
                         "inMed": es and es["med"], "inP25": es and es["p25"], "inP75": es and es["p75"], "inN": len(ent),
                         "actual": actual,
                         "dates": [{"date": r["date"], "title": r["title"], "peak15": r["peak15"], "peakTime": r["peakTime"],
                                    **{k: r[k] for k in KEYS if k in r}} for r in g]}
    # 예상: 공연 시작 시각만 보고 미리 예측(전체 공연의 시작 기준 분 25·50·75%)
    q = lambda v, p: int(round(float(np.percentile(v, p))))
    predict = {}
    for k in KEYS:
        v = [r[k] for r in show_rows if k in r]
        if len(v) >= 5:
            predict[k] = {"p25": q(v, 25), "med": q(v, 50), "p75": q(v, 75), "n": len(v)}
    baseline = {k: {"n": len(v), "bySource": base_src[k], **stats(v)} for k, v in base.items() if v}
    n24 = sum(r["src"] == "2024" for r in show_rows)
    label = f"2024년 7월 {n24}회" + (f" + 2025년 {len(show_rows) - n24}회" if len(show_rows) > n24 else "")
    out = {
        "built": pd.Timestamp.now().strftime("%Y-%m-%d"), "slotStart": SLOT_START, "slotMin": SLOT_MIN, "nSlots": N_SLOTS,
        "label": label, "zone": "동2문·남2문·북2문 구역",
        "source": "공원 주차장(동2문·남2문·북2문 구역) 입출차 기록, 2024년 7월"
                  + (f" + 2025년. {ic.note_2025(cov)}" if len(show_rows) > n24 else ""),
        "method": "15분마다 나간 차 대수(0분·24시간 이상 주차 제외). 공연은 시작 시각이 같은 날끼리 묶어 중앙값과 가운데 50%(4개 중 가운데 2개), "
                  "비교 기준은 같은 요일 유형(평일 / 주말·공휴일)의 큰 공연(KSPO DOME·핸드볼경기장·올림픽홀) 없는 날 중앙값",
        "timingMethod": ("실제 = 시작 시각이 같은 지난 공연에서 관객 차 절반·90%가 들어온(입차)·빠진(출차) 시각의 중앙값. "
                         "예상 = 공연 시작 시각만 보고 미리 예측한 값(전체 지난 공연의 시작 기준 시간 중앙값, 띠는 가운데 50%). "
                         "출차 관객 차 = 시작 3시간 전~20분 뒤 입차, 입차 관객 차 = 시작 6시간 전~30분 뒤 입차(둘 다 2시간 넘게 머물고 시작 1.5~7시간 사이 출차, 모든 출입구). "
                         "입차 시각은 같은 기준에 걸리는 평소 방문 차(큰 공연 없는 같은 요일 유형 날의 중앙값)를 빼고 잰 값. "
                         "곡선(입차·출차)은 관객 차만이 아니라 공원 주차장 전체 차"),
        "predict": predict,
        "groups": groups, "baseline": baseline, "skipped2025": skipped,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"KSPO DOME 공연 {label}, 시작 시각 {len(groups)}가지: "
          + ", ".join(f"{k} {v['n']}회" for k, v in groups.items()))
    print("예상(시작 기준 분, 중앙값): " + ", ".join(f"{k} {v['med']}" for k, v in predict.items()))
    print("비교 기준(큰 공연 없는 날): " + ", ".join(f"{k} {v['n']}일" for k, v in baseline.items()) + f" → {OUT}")
    if not use25:
        print(f"※ 2025 자료를 다 못 받아(못 받은 번호 덩어리가 있음, {ic.got_2025(cov) / ic.TOTAL_2025:.0%}) 2024년 7월만 썼어요.")
    elif skipped:
        print(f"※ 그날 기록이 모자라 뺀 2025 공연 {len(skipped)}회: {', '.join(skipped)}")


if __name__ == "__main__":
    main()
