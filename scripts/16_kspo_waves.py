"""
KSPO DOME 공연 후 '출차가 가장 몰리는 15분'이 공연 시작 몇 분 뒤에 오고, 그때 몇 대가 나가는지 (공연별).
운영자 화면 '출차 최대 예상 시각'·'15분 최대 출차 참고 범위'와 관객 화면 참고 문구에 쓴다.

입력: data/raw/vhcle_use/*.csv  차량 이용현황(문화 빅데이터 플랫폼, 2024-03~, 7개 문) — 있으면 이것만 쓴다(2026-11-23~)
      없으면 아래 예전 방식:
      data/raw/parking_inout_202407.csv (2024년 7월 전체)
      data/raw/kcisa_inout_2025.jsonl   (2025년, 못 받은 번호 덩어리가 없을 때만 씀. 받은 비율로 보정 → inout_common.py)
                                        65,535줄로 잘린 8·9월, 공연 시간대를 90% 넘게 못 받은 10~12월 공연은 뺀다
      data/processed/event_days.csv
출력: web/data/kspo_waves.json
방법: 공연 시작 60분 뒤 ~ 360분 뒤 공원 주차장 출차를 15분(정각 기준) 단위로 세어 가장 많은 구간의 시각과 대수.
      (scripts/04가 2024년 7월만으로 만들던 exits_2024_07.json의 kspoWaves와 같은 방법)

  실행: python scripts\\16_kspo_waves.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inout_common as ic  # noqa: E402

OUT = ic.ROOT / "web" / "data" / "kspo_waves.json"


def wave(x, day, start):
    s = pd.Timestamp(f"{day} {start}")
    a = x[(x.out_time >= s + pd.Timedelta(minutes=60)) & (x.out_time < s + pd.Timedelta(minutes=360))]
    if a.empty:
        return None
    c = a.groupby(a.out_time.dt.floor("15min")).w.sum()
    peak = c.idxmax()
    return {"peakTime": peak.strftime("%H:%M"), "peak15": int(round(c.max())), "lagMin": int((peak - s).total_seconds() // 60)}


def main_vhcle():
    """차량 이용현황(빠짐없는 자료)으로: 보정·건너뛰기 없음."""
    shows = ic.kspo_shows("2024-03")
    d, months = ic.load_vhcle({x[0] for x in shows})
    dur = (d.out_time - d.in_time).dt.total_seconds() / 60
    d = d[(dur > 0) & (dur < 24 * 60) & d.igate.isin(ic.MAIN_GATES)]   # 0분·24시간 이상 제외, 동2·남2·북2문 입차(예전과 같은 구역)
    d["day"] = d.out_time.dt.strftime("%Y-%m-%d")
    by = dict(tuple(d.groupby("day")))
    waves = []
    for day, start, title in shows:
        if day not in by or len(by[day]) < 800 or day[:7] not in months:
            continue
        w = wave(by[day], day, start)
        if w:
            waves.append({"date": day, "start": start, "title": title, "src": day[:4], **w})
    lags = np.array([w["lagMin"] for w in waves])
    peaks = np.array([w["peak15"] for w in waves])
    by_src = {}
    for w in waves:
        by_src[w["src"]] = by_src.get(w["src"], 0) + 1
    summary = {"n": len(waves), "bySource": by_src, "share2025": None, "skipped2025": [],
               "lagMed": int(np.median(lags)), "lagLo": int(np.percentile(lags, 10)), "lagHi": int(np.percentile(lags, 90)),
               "peakLo": int(np.percentile(peaks, 10)), "peakMed": int(np.median(peaks)), "peakHi": int(np.percentile(peaks, 90)),
               "rangeNote": "공연별 10~90% 범위"}
    label = f"{months[0][:4]}년 {int(months[0][5:])}월~{months[-1][:4]}년 {int(months[-1][5:])}월 {len(waves)}회"
    out = {"built": pd.Timestamp.now().strftime("%Y-%m-%d"), "label": label,
           "method": "공연 시작 60~360분 뒤 출차를 15분(정각 기준) 단위로 세어 가장 많은 구간",
           "scope": "공원 주차장 전체 출차(관객 차 + 평소 방문 차), 동2문·남2문·북2문 구역",
           "source": f"한국체육산업개발 '올림픽공원 차량 이용현황'(문화 빅데이터 플랫폼) KSPO DOME 공연 {label}, 빠진 달 없음·보정 없음",
           "summary": summary, "list": waves}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{out['source']}: 출차 최대 시작 후 {summary['lagMed']}분(중앙값, {summary['lagLo']}~{summary['lagHi']}), "
          f"15분 {summary['peakLo']}~{summary['peakHi']}대(중앙값 {summary['peakMed']}) → {OUT}")


def main():
    if ic.has_vhcle():
        return main_vhcle()
    d24 = ic.load_2024()
    d25, cov = ic.load_2025()
    use25 = ic.enough_2025(cov)
    d = pd.concat([d24, d25] if use25 else [d24], ignore_index=True)
    dur = (d.out_time - d.in_time).dt.total_seconds() / 60
    d = d[(dur > 0) & (dur < 24 * 60)]                 # 0분·24시간 이상 체류 제외 (docs/data_scope.md, scripts/04와 같게)
    d = d[(d.src == "2024") | d.igate.isin(ic.MAIN_GATES)]   # 2024년 7월 자료와 같은 구역(동2·남2·북2문 입차)만 — 11·18과 같게
    d["day"] = d.out_time.dt.strftime("%Y-%m-%d")
    by = dict(tuple(d.groupby("day")))
    waves, skipped = [], []
    for day, start, title in ic.kspo_shows("2024-07"):
        if day not in by or len(by[day]) < 800:
            continue
        s = pd.Timestamp(f"{day} {start}")
        wt, ok, _ = ic.show_weights(by[day], s, before=360, after=360)
        if not ok:
            skipped.append(day)
            continue
        w = wave(by[day].assign(w=wt), day, start)
        if w:
            waves.append({"date": day, "start": start, "title": title, "src": day[:4], **w})
    if not waves:
        raise SystemExit("계산할 공연일이 없습니다.")
    lags = np.array([w["lagMin"] for w in waves])
    peaks = np.array([w["peak15"] for w in waves])
    many = len(waves) >= 10
    lo_p, hi_p = (10, 90) if many else (0, 100)
    n24 = sum(1 for w in waves if w["src"] == "2024")
    summary = {
        "n": len(waves), "bySource": {"2024": n24, "2025": len(waves) - n24},
        "share2025": round(ic.got_2025(cov) / ic.TOTAL_2025, 3) if use25 else None, "skipped2025": skipped,
        "lagMed": int(np.median(lags)), "lagLo": int(np.percentile(lags, lo_p)), "lagHi": int(np.percentile(lags, hi_p)),
        "peakLo": int(np.percentile(peaks, lo_p)), "peakMed": int(np.median(peaks)), "peakHi": int(np.percentile(peaks, hi_p)),
        "rangeNote": "공연별 10~90% 범위" if many else "공연별 최소~최대",
    }
    label = f"2024년 7월 {n24}회" + (f" + 2025년 {len(waves) - n24}회" if len(waves) > n24 else "")
    out = {"built": pd.Timestamp.now().strftime("%Y-%m-%d"), "label": label,
           "method": "공연 시작 60~360분 뒤 출차를 15분(정각 기준) 단위로 세어 가장 많은 구간",
           "scope": "공원 주차장 전체 출차(관객 차 + 평소 방문 차), 동2문·남2문·북2문 구역",
           "source": f"공원 주차장(동2문·남2문·북2문 구역) 입출차 기록 KSPO DOME 공연 {label}"
                     + (f" ({ic.note_2025(cov)})" if len(waves) > n24 else ""),
           "summary": summary, "list": waves}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{out['source']}: 출차 최대 시작 후 {summary['lagMed']}분(중앙값), 15분 {summary['peakLo']}~{summary['peakHi']}대 → {OUT}")
    if not use25:
        print(f"※ 2025 자료를 다 못 받아(못 받은 번호 덩어리가 있음, {ic.got_2025(cov) / ic.TOTAL_2025:.0%}) 2024년 7월만 썼어요.")
    elif skipped:
        print(f"※ 대수를 못 쓴 2025 공연(잘린 달·빈 시간대) {len(skipped)}회: {', '.join(skipped)}")


if __name__ == "__main__":
    main()
