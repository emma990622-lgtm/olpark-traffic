"""
공연일에 수집기(olpark-collector)가 5분마다 저장한 실시간 주차 합계로, 화면의 예상이 얼마나 맞았는지 비교한다.
인증키가 필요 없다(수집기 저장소의 CSV만 읽음).

  실행: python scripts/20_field_check.py 2026-11-21 --collector ../olpark-collector
        (공연 시작 시각은 web/data/events.json의 KSPO DOME 공연에서 찾는다. 없으면 --start 18:00)

입력
  <수집기>/data/<날짜>_*/summary.csv   수집시각, 주차합계_parking_sum (그날 폴더 여러 개를 이어 붙임)
  <수집기>/data/parking_night.csv       새벽 주차 합계(출차 기록 없는 장기 차량 보정용, 화면의 parkActual과 같게: 새벽 값 − 60대를 뺌)
  web/data/live_exit.json               출차 감지 규칙, 감지 뒤 걸린 시간, 입차 예상
  web/data/exit_curves.json             공연 시작 기준 출차 절반·90% 예상
출력
  data/processed/field_check_<날짜>.json, docs/field/<날짜>.md (사람이 읽는 요약)

비교하는 것
  1) 출차 시작 감지: 화면과 같은 규칙을 수집 자료에 적용한 감지 시각
  2) 출차 절반·90%: 감지 시각 + 과거 중앙값(예상) vs 주차 대수로 본 근사 실제
     근사 실제 = 시작 뒤 최고 대수에서 '빠져나간 양(최고 − 수집 끝 무렵 최저)'의 50%·90%가 줄어든 시각
  3) 입차 절반·90%: 시작 기준 과거 중앙값(예상) vs 근사 실제(수집 시작 무렵 최저에서 공연 전 최고까지 늘어난 양의 50%·90%)
  ※ 근사 실제는 공원 주차장 전체 대수로 잰 값이라 관객 차만 센 입출차 기록과 정의가 다르다. 정확한 비교는 나중에 입출차 기록이 개방되면 가능.
"""
import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web" / "data"
NIGHT_TRUE = 60                      # 새벽 실제 주차 약 60대(web/assets/common.js PARK_NIGHT_TRUE와 같게)


def hhmm(start_min, m):
    t = int(round(start_min + m)) % (24 * 60)
    return f"{t // 60:02d}:{t % 60:02d}"


def load_points(collector, day, start_dt):
    rows = []
    for f in sorted(Path(collector, "data").glob(f"{day}_*/summary.csv")):
        with open(f, encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                v = (r.get("주차합계_parking_sum") or "").strip()
                if not v:
                    continue
                try:
                    t = datetime.strptime(r["수집시각"][:19], "%Y-%m-%d %H:%M:%S")
                    rows.append((t, float(v)))
                except ValueError:
                    continue
    rows = sorted(set(rows))
    ghost = 0
    night = Path(collector, "data", "parking_night.csv")
    if night.exists():
        last = None
        for line in night.read_text(encoding="utf-8-sig").strip().splitlines():
            p = line.split(",")
            if len(p) >= 3 and p[0] <= day and p[2].strip().isdigit():
                last = (p[0], p[1], int(p[2]))
        if last:
            ghost = max(0, last[2] - NIGHT_TRUE)
    pts = [{"m": (t - start_dt).total_seconds() / 60, "v": max(0.0, s - ghost), "sum": s, "t": t.strftime("%H:%M")} for t, s in rows]
    return pts, ghost


def detect(pts, R):
    """web/assets/live_exit.js detectExit와 같은 규칙"""
    M = float("-inf")
    for i, p in enumerate(pts):
        if p["m"] >= 0:
            M = max(M, p["v"])
        if p["m"] < R["earliestMin"] or M < R["minPeak"]:
            continue
        j = next((k for k in range(i - 1, -1, -1) if pts[k]["m"] <= p["m"] - R["windowMin"] + 1), None)
        if j is None or p["m"] - pts[j]["m"] > R["windowMin"] + 6:
            continue
        if pts[j]["v"] - p["v"] < R["ratio"] * M:
            continue
        nx = next((q for q in pts[i + 1:] if q["m"] >= p["m"] + 4), None)
        if nx is None:
            return {"state": "checking", "m": p["m"], "M": M}
        if nx["v"] < p["v"]:
            return {"state": "found", "m": p["m"], "M": M, "drop": pts[j]["v"] - p["v"]}
    return {"state": "none", "M": M if M > float("-inf") else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("day")
    ap.add_argument("--collector", default=str(ROOT.parent / "olpark-collector"))
    ap.add_argument("--start", default="")
    a = ap.parse_args()
    start, title = a.start, ""
    if not start:
        ev = json.loads((WEB / "events.json").read_text(encoding="utf-8"))
        e = next((x for x in ev if x["date"] == a.day and x["venue"] == "KSPO DOME" and x.get("times")), None)
        if not e:
            raise SystemExit(f"{a.day}에 KSPO DOME 공연이 없어요. --start HH:MM 으로 시작 시각을 주세요.")
        start, title = e["times"][0], e["title"]
    start_dt = datetime.strptime(f"{a.day} {start}", "%Y-%m-%d %H:%M")
    s0 = start_dt.hour * 60 + start_dt.minute
    pts, ghost = load_points(a.collector, a.day, start_dt)
    if len(pts) < 10:
        raise SystemExit(f"{a.day} 수집 자료가 모자라요({len(pts)}개). 수집기 저장소를 최신으로 받았는지 확인하세요.")
    L = json.loads((WEB / "live_exit.json").read_text(encoding="utf-8"))
    C = json.loads((WEB / "exit_curves.json").read_text(encoding="utf-8"))
    R, A, E, P = L["rule"], L["after"], L.get("entry"), C.get("predict", {})

    out = {"date": a.day, "start": start, "title": title, "built": datetime.now().strftime("%Y-%m-%d %H:%M"),
           "points": len(pts), "from": pts[0]["t"], "to": pts[-1]["t"], "ghost": ghost,
           "gapsOver10min": sum(1 for x, y in zip(pts, pts[1:]) if y["m"] - x["m"] > 10),
           "note": "근사 실제는 공원 주차장 전체 대수(실시간 값 − 장기 주차 보정)로 잰 값이라 관객 차만 센 입출차 기록과 정의가 달라요. "
                   "지난 공연 한 회(2025-03-01)로 시험했을 때 근사 실제가 입출차 기록 기준보다 출차는 30분쯤 이르게 나왔어요. 방향을 보는 참고값이에요."}
    lines = [f"# 현장 검증(자동) {a.day} {title}".strip(), "",
             f"- 공연 시작 {start}, 수집 {out['from']}~{out['to']} ({len(pts)}개 값, 10분 넘는 빈칸 {out['gapsOver10min']}곳)",
             f"- 실시간 주차 합계에서 장기 주차 보정 {ghost:,}대를 뺀 값으로 계산", ""]

    # ---- 입차 ----
    pre = [p for p in pts if p["m"] <= 30]
    if E and len(pre) >= 6 and pre[0]["m"] <= -90:
        base = min(p["v"] for p in pre[: max(3, len(pre) // 3)])
        peak = max(p["v"] for p in pre)
        rise = peak - base
        ent = {"base": round(base), "peak": round(peak), "rise": round(rise), "firstMin": round(pre[0]["m"])}
        if rise >= 100:
            for key, f, pred in (("half", 0.5, E["half"]), ("most", 0.9, E["most"])):
                hit = next((p for p in pre if p["v"] >= base + f * rise), None)
                ent[key] = {"pred": pred["med"], "predRange": [pred["p25"], pred["p75"]], "obs": hit and round(hit["m"]),
                            "diff": hit and round(hit["m"] - pred["med"])}
            lines += ["## 입차 (공연 전)", "", "| | 예상(지난 공연 중앙값) | 근사 실제 | 차이 |", "| --- | --- | --- | --- |"]
            for key, lab in (("half", "관객 차 절반이 들어옴"), ("most", "관객 차 90%가 들어옴")):
                x = ent[key]
                lines.append(f"| {lab} | {hhmm(s0, x['pred'])} (보통 {hhmm(s0, x['predRange'][0])}~{hhmm(s0, x['predRange'][1])}) | "
                             f"{hhmm(s0, x['obs']) if x['obs'] is not None else '—'} | {('%+d분' % x['diff']) if x['diff'] is not None else '—'} |")
            lines += ["", f"- 수집 시작 무렵 최저 {ent['base']:,}대 → 공연 전 최고 {ent['peak']:,}대(늘어난 양 {ent['rise']:,}대). "
                          f"수집이 시작 {abs(ent['firstMin'])}분 전부터라 그 전에 들어온 차는 '늘어난 양'에 안 잡혀 근사 실제가 늦게 나올 수 있어요.", ""]
        else:
            lines += ["## 입차 (공연 전)", "", f"- 공연 전에 늘어난 양이 {round(rise)}대뿐이라 비교하지 않았어요.", ""]
        out["entry"] = ent
    else:
        lines += ["## 입차 (공연 전)", "", "- 공연 90분 전부터의 수집 값이 없어 비교하지 못했어요.", ""]

    # ---- 출차 ----
    det = detect(pts, R)
    ex = {"state": det["state"], "peakAfterStart": det.get("M") and round(det["M"])}
    lines += ["## 출차 (공연 뒤)", ""]
    if det["state"] == "found":
        dm = det["m"]
        after = [p for p in pts if p["m"] >= dm]
        low = min(p["v"] for p in after)
        gone = det["M"] - low
        ex.update({"detMin": round(dm), "detTime": hhmm(s0, dm), "low": round(low), "gone": round(gone), "lastMin": round(pts[-1]["m"])})
        lines += [f"- **출차 시작 감지: {hhmm(s0, dm)}** (시작 +{round(dm)}분). 시작 뒤 최고 {round(det['M']):,}대에서 {R['windowMin']}분 동안 {round(det['drop'])}대 줄어듦(기준 {round(R['ratio'] * det['M'])}대).",
                  "", "| | 감지 뒤 예상 | 시작 시각만 본 예상 | 근사 실제 | 감지 뒤 예상과 차이 |", "| --- | --- | --- | --- | --- |"]
        for key, f, aft, pk, lab in (("half", 0.5, A["half"], "exit50", "절반이 빠짐"), ("most", 0.9, A["most"], "exit90", "90%가 빠짐")):
            hit = next((p for p in pts if p["m"] >= 0 and p["v"] <= det["M"] - f * gone and p["m"] >= dm - R["windowMin"]), None)
            pre_pred = P.get(pk, {}).get("med")
            x = {"predLive": round(dm + aft["med"]), "predBefore": pre_pred, "obs": hit and round(hit["m"]),
                 "diffLive": hit and round(hit["m"] - (dm + aft["med"])), "diffBefore": hit and pre_pred is not None and round(hit["m"] - pre_pred)}
            ex[key] = x
            lines.append(f"| {lab} | {hhmm(s0, x['predLive'])} | {hhmm(s0, pre_pred) if pre_pred is not None else '—'} | "
                         f"{hhmm(s0, x['obs']) if x['obs'] is not None else '—'} | {('%+d분' % x['diffLive']) if x['diffLive'] is not None else '—'} |")
        lines += ["", f"- 근사 실제의 기준: 시작 뒤 최고 {round(det['M']):,}대 → 수집 끝 무렵 최저 {round(low):,}대(빠져나간 양 {round(gone):,}대). "
                      f"수집이 시작 +{ex['lastMin']}분에 끝나서, 그 뒤에도 차가 더 빠졌다면 근사 실제가 실제보다 이르게 나와요.", ""]
    elif det["state"] == "checking":
        lines += ["- 수집 끝 무렵에 감지 조건에 걸렸지만 다음 값이 없어 확정하지 못했어요.", ""]
    else:
        lines += [f"- 출차 시작이 감지되지 않았어요(시작 뒤 최고 {ex['peakAfterStart'] or 0:,}대, 기준: {R['windowMin']}분 동안 최고 대수의 {int(R['ratio'] * 100)}% 이상 감소).", ""]
    out["exit"] = ex
    lines += ["## 읽을 때 주의", "", f"- {out['note']}",
              "- 현장에서 누른 '관객이 나오기 시작했어요' 시각과 브라우저 기록(CSV)이 있으면 그것이 더 정확한 기준이에요.", ""]

    (ROOT / "data" / "processed").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "processed" / f"field_check_{a.day}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    (ROOT / "docs" / "field").mkdir(parents=True, exist_ok=True)
    (ROOT / "docs" / "field" / f"{a.day}.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
