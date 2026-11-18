"""
지도에 칠하는 실시간 도로 속도(서울시 실시간 도시데이터)가 맞는지 TMAP 실시간 교통과 비교한다.
두 곳은 데이터를 따로 모은다(서울시: TOPIS 수집, TMAP: 내비 이용 차량). 같은 시각에 같은 구간을 보고
속도와 소통 등급(원활·서행·정체)이 얼마나 비슷한지 잰다.

  run_verify_roads.bat 더블클릭 (TMAP 키는 set_keys.bat으로 저장해 두면 묻지 않음)
  공연 끝나는 시각에 한 번 더 돌리면 혼잡할 때도 맞는지 볼 수 있다.

자동 실행(GitHub Actions): python scripts/10_verify_roads_tmap.py --auto
  30분마다 깨어나서 아래 때에만 실제로 비교한다(아니면 바로 끝남).
   - 공연 끝나는 때: 오늘 KSPO DOME·핸드볼경기장 공연의 시작 2시간 30분 ~ 3시간 30분 뒤 (공연마다 한 번)
   - 평소 비교: 공연 없는 평일(월~목) 18:30 무렵 퇴근 시간 한 번
결과: web/data/road_check.json (운영자 화면에 요약이 나옴), 같은 내용을 data/processed/road_check_시각.csv로도 저장
"""
import csv
import datetime as dt
import json
import math
import os
import statistics as stt
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINKS = ROOT / "web" / "data" / "links.json"
OUT = ROOT / "web" / "data" / "road_check.json"
ROADS_API = "https://olpark-traffic.vercel.app/api/roads"
TMAP = "https://apis.openapi.sk.com/tmap/routes?version=1&format=json"
GRADE = {1: "원활", 2: "서행", 3: "정체", 4: "정체"}      # TMAP 혼잡도 1 원활, 2 서행, 3 지체, 4 정체
RANK = {"원활": 0, "서행": 1, "정체": 2}


def seoul_grade(spd):
    # 서울시 도시데이터 기준과 같은 경계(이 사이트 지도 범례): 25 이상 원활, 15~24 서행, 15 미만 정체
    return "원활" if spd >= 25 else "서행" if spd >= 15 else "정체"


def get_json(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))


def lerp(a, b, t):
    return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]


RAW_SAMPLES = []


def tmap(key, a, b):
    body = json.dumps({"startX": str(a[0]), "startY": str(a[1]), "endX": str(b[0]), "endY": str(b[1]),
                       "reqCoordType": "WGS84GEO", "resCoordType": "WGS84GEO",
                       "searchOption": "0", "trafficInfo": "Y"}).encode()
    d = get_json(TMAP, body, {"appKey": key, "Content-Type": "application/json", "Accept": "application/json"})
    if len(RAW_SAMPLES) < 5:                       # 응답 모양 확인용(키는 들어 있지 않음)
        RAW_SAMPLES.append(d)
    p = d["features"][0]["properties"]
    # 구간별 교통정보: [시작점, 끝점, 혼잡도, 속도] 형식. 점 개수로 가중 평균
    spd_w, cong_w, w = 0.0, 0.0, 0
    for f in d["features"]:
        if f["geometry"]["type"] != "LineString":
            continue
        for t in f["properties"].get("traffic") or []:
            if len(t) >= 3 and t[2]:
                n = max(1, int(t[1]) - int(t[0]))
                cong_w += float(t[2]) * n
                if len(t) >= 4 and t[3]:
                    spd_w += float(t[3]) * n
                w += n
    total_m, total_s = int(p["totalDistance"]), int(p["totalTime"])
    route_spd = total_m / max(total_s, 1) * 3.6
    cong = round(cong_w / w) if w else None
    if w and spd_w:
        return total_m, spd_w / w, cong, "구간 교통정보"
    return total_m, route_spd, cong, "경로 시간(신호 대기 포함)"


EVENTS = ROOT / "web" / "data" / "events.json"
BIG = ("KSPO DOME", "핸드볼경기장")
KST = dt.timezone(dt.timedelta(hours=9))


def auto_reason():
    """--auto일 때 지금 비교할 때인지 판단. 비교할 이유(문자열) 또는 None."""
    now = dt.datetime.now(KST).replace(tzinfo=None)
    today = now.strftime("%Y-%m-%d")
    done = []
    if OUT.exists():
        try:
            done = [h.get("reason", "") for h in json.loads(OUT.read_text(encoding="utf-8")).get("history", [])]
        except ValueError:
            pass
    shows = [(e["venue"], t) for e in json.loads(EVENTS.read_text(encoding="utf-8"))
             if e["date"] == today and e["venue"] in BIG for t in e["times"]]
    for venue, t in shows:
        start = dt.datetime.strptime(f"{today} {t}", "%Y-%m-%d %H:%M")
        if start + dt.timedelta(minutes=150) <= now <= start + dt.timedelta(minutes=210):
            r = f"공연 종료 무렵 {today} {t} {venue}"
            return None if r in done else r
    if not shows and now.weekday() <= 3 and dt.time(18, 15) <= now.time() <= dt.time(19, 20):
        r = f"평소 퇴근 시간 {today}"
        return None if r in done else r
    return None


def main():
    reason = "직접 실행"
    if "--auto" in sys.argv:
        reason = auto_reason()
        if not reason:
            print("지금은 비교할 때가 아니라 끝냅니다.")
            return
        print(f"자동 비교: {reason}")
    key = os.environ.get("TMAP_APP_KEY") or input("TMAP(SK 오픈API) 앱키를 붙여넣고 Enter: ").strip()
    if not key:
        raise SystemExit("키가 비어 있습니다.")
    links = {l["id"]: l for l in json.loads(LINKS.read_text(encoding="utf-8"))}
    live = get_json(ROADS_API)
    print(f"서울시 도로 자료 시각: {live.get('roadTime')}  (지금 {dt.datetime.now(KST):%H:%M})")
    rows = []
    for r in live.get("links", []):
        l = links.get(str(r["id"]))
        if not l or r.get("spd") is None:
            continue
        ln = float(l["len"])
        got = None
        for t0, t1 in ((0.1, 0.9), (0.25, 0.95), (0.0, 1.0)):     # 교차로 끝점에 붙지 않게 안쪽에서 시작
            try:
                m, spd, cong, src = tmap(key, lerp(l["a"], l["b"], t0), lerp(l["a"], l["b"], t1))
            except Exception as e:
                print(f"  {l['road']} {l['from']}→{l['to']}: TMAP 실패 ({e})")
                break
            if m <= 1.5 * ln * (t1 - t0) + 150:                 # 돌아가는 길이면 같은 구간이 아님
                got = (spd, cong, src)
                break
            time.sleep(0.3)
        time.sleep(0.3)
        if not got:
            continue
        spd, cong, src = got
        tg = GRADE.get(cong) if cong else seoul_grade(spd)
        sg = r.get("idx") or seoul_grade(r["spd"])
        rows.append({"id": l["id"], "road": l["road"], "from": l["from"], "to": l["to"],
                     "seoulSpd": r["spd"], "seoulIdx": sg, "tmapSpd": round(spd, 1), "tmapIdx": tg,
                     "gap": RANK.get(sg, 0) - RANK.get(tg, 0), "len": round(ln), "tmapSrc": src})
        print(f"  {l['road']:6} {l['from'][:10]:10}→{l['to'][:10]:10} 서울시 {r['spd']:>3}km/h {sg}  |  TMAP {spd:5.1f}km/h {tg}")
    if not rows:
        raise SystemExit("비교할 수 있는 구간이 없습니다.")
    same = sum(1 for x in rows if x["seoulIdx"] == x["tmapIdx"])
    near = sum(1 for x in rows if abs(x["gap"]) <= 1)
    diffs = [abs(x["seoulSpd"] - x["tmapSpd"]) for x in rows]
    a = [x["seoulSpd"] for x in rows]
    b = [x["tmapSpd"] for x in rows]
    corr = None
    if len(rows) > 3 and stt.pstdev(a) and stt.pstdev(b):
        ma, mb = stt.mean(a), stt.mean(b)
        corr = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (len(a) * stt.pstdev(a) * stt.pstdev(b))
    now = dt.datetime.now(KST).replace(tzinfo=None)
    out = {"checked": now.strftime("%Y-%m-%d %H:%M"), "reason": reason, "roadTime": live.get("roadTime"), "n": len(rows),
           "total": len(live.get("links", [])), "sameGrade": round(same / len(rows), 3),
           "within1": round(near / len(rows), 3), "medAbsDiff": round(stt.median(diffs), 1),
           "corr": round(corr, 2) if corr is not None else None,
           "seoulSlower": sum(1 for x in rows if x["gap"] > 0), "seoulFaster": sum(1 for x in rows if x["gap"] < 0),
           "worst": sorted(rows, key=lambda x: -abs(x["seoulSpd"] - x["tmapSpd"]))[:8]}
    long_ = [x for x in rows if x["len"] >= 300]           # 짧은 구간은 끝 교차로 신호 대기에 크게 흔들림
    if long_:
        out["long300"] = {"n": len(long_),
                          "sameGrade": round(sum(x["seoulIdx"] == x["tmapIdx"] for x in long_) / len(long_), 3),
                          "within1": round(sum(abs(x["gap"]) <= 1 for x in long_) / len(long_), 3),
                          "medAbsDiff": round(stt.median(abs(x["seoulSpd"] - x["tmapSpd"]) for x in long_), 1)}
    out["tmapSrc"] = {k: sum(1 for x in rows if x["tmapSrc"] == k) for k in {x["tmapSrc"] for x in rows}}
    (ROOT / "data" / "raw").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "raw" / "tmap_traffic_sample.json").write_text(json.dumps(RAW_SAMPLES, ensure_ascii=False)[:400000], encoding="utf-8")
    hist = []
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8"))
            hist = old.get("history", [])
        except ValueError:
            pass
    hist = (hist + [{k: out.get(k) for k in ("checked", "reason", "n", "sameGrade", "within1", "medAbsDiff", "corr")}])[-40:]
    out["history"] = hist
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    proc = ROOT / "data" / "processed"
    proc.mkdir(parents=True, exist_ok=True)
    with open(proc / f"road_check_{now:%Y%m%d_%H%M}.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\n비교한 구간 {len(rows)}/{out['total']}개")
    print(f"  소통 등급이 같은 구간 {same}개({same / len(rows):.0%}), 한 단계 차이까지 {near / len(rows):.0%}")
    print(f"  속도 차이 중앙값 {out['medAbsDiff']}km/h" + (f", 상관계수 {out['corr']}" if corr is not None else ""))
    if "long300" in out:
        print(f"  300m 넘는 구간만: {out['long300']['n']}개, 등급 같음 {out['long300']['sameGrade']:.0%}, 한 단계까지 {out['long300']['within1']:.0%}")
    print(f"  TMAP 속도 출처: {out['tmapSrc']}")
    print(f"저장 → {OUT}\nClaude에게 '도로 검증 끝났어'라고 알려주세요.")


if __name__ == "__main__":
    main()
