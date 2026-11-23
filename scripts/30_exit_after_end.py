"""
과거 KSPO DOME 공연의 실제 종료 시각(공연 시간) 대비 관객 차 50%·90% 출차 소요 시간 계산.
  입력: data/processed/exit_weather_shows.csv  (scripts/25가 만든 공연 171회 출차 시각 요약, 취소·휴연 제외)
        data/processed/show_runtime_known.csv  (언론 현장·성료 기사, 후기, 공식 공지로 확인한 공연 시간·특이사항)
  출력: data/processed/exit_after_end_shows.csv (종료 시각 확인 공연 회차별 종료 시각·출차 소요 분)
        web/data/exit_gate.json 안 weather.afterEnd 갱신 (외부 라이브러리 없이 표준 라이브러리만 사용)

신뢰 기준:
  - confidence가 '기사', '기사(여러 회차 묶음)', '단일 후기'이고 actual_min 숫자가 있는 회차만 계산에 포함.
  - 예매처 예정 관람시간('공식(예정만)'), 회차 불명 간접 언급('기사(간접)'), 상한 없는 범위('기사(범위만)'),
    녹화본 길이('대리값'), 취소('공식(취소)'), 휴연('공식(휴연)'), 시작 지연('공식(시작지연)')은 CSV에 기록하되 계산에서는 제외.
"""
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRUSTED = ("기사", "기사(여러 회차 묶음)", "단일 후기")


def quantile(vals, q):
    s = sorted(vals)
    pos = (len(s) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def add_minutes_clock(hhmm, mins):
    h, m = map(int, hhmm.split(":"))
    tot = h * 60 + m + int(round(mins))
    day_plus, rem = divmod(tot, 1440)
    eh, em = divmod(rem, 60)
    prefix = "익일 " if day_plus > 0 else ""
    return f"{prefix}{eh:02d}:{em:02d}"


def summarize(rows):
    a50 = [r["after50"] for r in rows]
    a90 = [r["after90"] for r in rows]
    runs = [r["actual_min"] for r in rows]
    tours = {}
    for r in rows:
        tours.setdefault(r["title"], []).append(r)
    tour_p50 = [quantile([x["after50"] for x in xs], 0.5) for xs in tours.values()]
    tour_p90 = [quantile([x["after90"] for x in xs], 0.5) for xs in tours.values()]
    return {
        "shows": len(rows),
        "tours": len(tours),
        "runtimeMed": round(quantile(runs, 0.5), 1),
        "p50": {
            "med": round(quantile(a50, 0.5), 1),
            "p25": round(quantile(a50, 0.25), 1),
            "p75": round(quantile(a50, 0.75), 1),
        },
        "p90": {
            "med": round(quantile(a90, 0.5), 1),
            "p25": round(quantile(a90, 0.25), 1),
            "p75": round(quantile(a90, 0.75), 1),
        },
        "tourMed": {
            "p50": round(quantile(tour_p50, 0.5), 1),
            "p90": round(quantile(tour_p90, 0.5), 1),
        },
    }


def compute_after_end(root=ROOT, write_csv=True):
    shows_path = root / "data/processed/exit_weather_shows.csv"
    known_path = root / "data/processed/show_runtime_known.csv"
    with shows_path.open(encoding="utf-8-sig", newline="") as f:
        shows = {(r["date"], r["start"]): r for r in csv.DictReader(f)}
    with known_path.open(encoding="utf-8-sig", newline="") as f:
        known = list(csv.DictReader(f))

    matched = []
    for k in known:
        conf = (k.get("confidence") or "").strip()
        amin_raw = (k.get("actual_min") or "").strip()
        if conf not in TRUSTED or not amin_raw:
            continue
        s = shows.get((k["date"].strip(), k["start"].strip()))
        if not s:
            continue
        amin = float(amin_raw)
        p50 = float(s["p50"])
        p90 = float(s["p90"])
        wet = str(s["wet"]).strip().lower() == "true"
        cold = str(s["cold"]).strip().lower() == "true"
        matched.append({
            "date": s["date"],
            "start": s["start"],
            "title": s["title"],
            "n": int(float(s["n"])),
            "actual_min": int(round(amin)),
            "end_clock": add_minutes_clock(s["start"], amin),
            "p50": round(p50, 2),
            "p90": round(p90, 2),
            "after50": round(p50 - amin, 2),
            "after90": round(p90 - amin, 2),
            "wet": wet,
            "cold": cold,
            "confidence": conf,
            "source": k["source"].strip(),
        })

    if not matched:
        raise RuntimeError("종료 시각이 확인된 공연 매칭 결과가 없습니다.")

    if write_csv:
        out_csv = root / "data/processed/exit_after_end_shows.csv"
        fields = [
            "date", "start", "title", "n", "actual_min", "end_clock",
            "p50", "p90", "after50", "after90", "wet", "cold", "confidence", "source",
        ]
        with out_csv.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(matched)

    all_stat = summarize(matched)
    dry_stat = summarize([r for r in matched if not r["wet"]])
    return {
        "source": (
            f"언론 현장·성료 기사와 관람 후기에서 실제 공연 시간이 확인된 KSPO DOME 공연 "
            f"{all_stat['shows']}회({all_stat['tours']}개 투어, 예매처 예정 관람시간·간접 언급·대리값 제외)"
        ),
        "trustedConfidence": list(TRUSTED),
        "all": all_stat,
        "dry": dry_stat,
    }


def main():
    after_end = compute_after_end(ROOT, write_csv=True)
    gate_path = ROOT / "web/data/exit_gate.json"
    data = json.loads(gate_path.read_text(encoding="utf-8"))
    data["weather"]["afterEnd"] = after_end
    kst = timezone(timedelta(hours=9))
    data["built"] = datetime.now(kst).strftime("%Y-%m-%d")
    gate_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(after_end, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
