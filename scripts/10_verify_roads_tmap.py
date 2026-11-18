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
    """TMAP 자동차 경로. 경로를 이루는 도로 조각마다 이름·거리·소요시간(실시간 교통 반영)이 온다.
    구간별 혼잡도(traffic) 배열은 이 키로는 오지 않아서, 같은 이름 도로 조각의 거리÷시간으로 속도를 구한다."""
    body = json.dumps({"startX": str(a[0]), "startY": str(a[1]), "endX": str(b[0]), "endY": str(b[1]),
                       "reqCoordType": "WGS84GEO", "resCoordType": "WGS84GEO",
                       "searchOption": "0", "trafficInfo": "Y"}).encode()
    d = get_json(TMAP, body, {"appKey": key, "Content-Type": "application/json", "Accept": "application/json"})
    if len(RAW_SAMPLES) < 5:                       # 응답 모양 확인용(키는 들어 있지 않음)
        RAW_SAMPLES.append(d)
    segs = [(f["properties"].get("name", ""), int(f["properties"].get("distance") or 0), int(f["properties"].get("time") or 0))
            for f in d["features"] if f["geometry"]["type"] == "LineString"]
    return int(d["features"][0]["properties"]["totalDistance"]), segs


def road_speed(segs, road):
    """경로 중 비교 구간과 같은 이름의 도로 조각만 모아 속도(km/h). 너무 짧으면 None."""
    names = {x for x in road.replace(".", " ").split() if x}
    use = [(m, t) for n, m, t in segs if n and (n == road or n in names) and m > 0 and t > 0]
    dist = sum(m for m, _ in use)
    secs = sum(t for _, t in use)
    return (dist / secs * 3.6, dist) if secs else (None, dist)


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


def corridors(links_list, min_len=600):
    """같은 도로에서 앞 구간의 끝 지점 = 다음 구간의 시작 지점으로 이어지는 구간들을 묶은 긴 도로(600m 이상).
    짧은 구간은 끝 교차로 신호 대기에 크게 흔들려서, 긴 도로의 '이동시간'으로 비교해야 공정하다."""
    by_from = {}
    for l in links_list:
        by_from.setdefault((l["road"], l["from"]), []).append(l)
    out = []
    for l in links_list:
        if any(x["road"] == l["road"] and x["to"] == l["from"] and x["from"] != l["to"] for x in links_list):
            continue                                    # 중간 구간이면 시작점이 아님
        c, nodes = [l], {l["from"], l["to"]}
        while True:                                     # 이미 지난 지점으로 되돌아가는 구간은 잇지 않음
            nx = [x for x in by_from.get((c[-1]["road"], c[-1]["to"]), []) if x["to"] not in nodes]
            if not nx:
                break
            c.append(nx[0])
            nodes.add(nx[0]["to"])
        total = sum(float(x["len"]) for x in c)
        if total >= min_len:
            out.append(c)
    return out


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
        for t0, t1 in ((0.0, 1.0), (0.1, 0.9)):
            try:
                _, segs = tmap(key, lerp(l["a"], l["b"], t0), lerp(l["a"], l["b"], t1))
            except Exception as e:
                print(f"  {l['road']} {l['from']}→{l['to']}: TMAP 실패 ({e})")
                break
            spd, dist = road_speed(segs, l["road"])
            if spd and dist >= max(80, 0.4 * ln * (t1 - t0)):   # 같은 도로를 충분히 달린 경우만
                got = (spd, None, f"같은 도로 {dist}m")
                break
            time.sleep(0.3)
        time.sleep(0.3)
        if not got:
            continue
        spd, cong, src = got
        tg = seoul_grade(spd)
        sg = r.get("idx") or seoul_grade(r["spd"])
        rows.append({"id": l["id"], "road": l["road"], "from": l["from"], "to": l["to"],
                     "seoulSpd": r["spd"], "seoulIdx": sg, "tmapSpd": round(spd, 1), "tmapIdx": tg,
                     "gap": RANK.get(sg, 0) - RANK.get(tg, 0), "len": round(ln), "tmapSrc": "같은 도로 조각"})
        print(f"  {l['road']:6} {l['from'][:10]:10}→{l['to'][:10]:10} 서울시 {r['spd']:>3}km/h {sg}  |  TMAP {spd:5.1f}km/h {tg}")
    # 긴 도로 이동시간 비교: 서울시 = 구간마다 길이÷속도를 더한 시간, TMAP = 같은 길을 달리는 경로 시간
    spd_by_id = {str(r["id"]): r.get("spd") for r in live.get("links", [])}
    cor_rows = []
    print("\n[긴 도로 이동시간 비교]")
    for c in corridors(list(links.values())):
        if any(not spd_by_id.get(x["id"]) for x in c):
            continue
        total = sum(float(x["len"]) for x in c)
        seoul_min = sum(float(x["len"]) / 1000 / spd_by_id[x["id"]] * 60 for x in c)
        try:
            tm, segs = tmap(key, c[0]["a"], c[-1]["b"])
            body_t = sum(t for _, _, t in segs)
        except Exception as e:
            print(f"  {c[0]['road']}: TMAP 실패 ({e})")
            continue
        time.sleep(0.4)
        if tm > 1.3 * total + 100:
            print(f"  {c[0]['road']} {c[0]['from']}→{c[-1]['to']}: TMAP이 다른 길로 돌아가서 뺌")
            continue
        tmap_min = body_t / 60
        diff = (tmap_min - seoul_min) / seoul_min if seoul_min else 0
        cor_rows.append({"road": c[0]["road"], "from": c[0]["from"], "to": c[-1]["to"], "links": len(c), "len": round(total),
                         "seoulMin": round(seoul_min, 1), "tmapMin": round(tmap_min, 1), "diff": round(diff, 2)})
        print(f"  {c[0]['road']:5} {c[0]['from'][:9]}→{c[-1]['to'][:9]} {round(total)}m  서울시 {seoul_min:4.1f}분  TMAP {tmap_min:4.1f}분  ({diff:+.0%})")
    if not rows and not cor_rows:
        raise SystemExit("비교할 수 있는 구간이 없습니다.")
    if not rows:
        rows = [{"id": "", "road": "", "from": "", "to": "", "seoulSpd": 0, "seoulIdx": "", "tmapSpd": 0, "tmapIdx": "", "gap": 0, "len": 0, "tmapSrc": ""}]
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
    if cor_rows:
        ad = [abs(x["diff"]) for x in cor_rows]
        out["corridors"] = {"n": len(cor_rows), "medAbsDiff": round(stt.median(ad), 2),
                            "within30": round(sum(a <= 0.3 for a in ad) / len(ad), 2), "rows": cor_rows}
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
    hist = (hist + [{**{k: out.get(k) for k in ("checked", "reason", "n", "sameGrade", "within1", "medAbsDiff", "corr")},
                     "corridorDiff": out.get("corridors", {}).get("medAbsDiff")}])[-40:]
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
    if "corridors" in out:
        print(f"  긴 도로 {out['corridors']['n']}개: 이동시간 차이 중앙값 {out['corridors']['medAbsDiff']:.0%}, 30% 안쪽 {out['corridors']['within30']:.0%}")
    print(f"저장 → {OUT}\nClaude에게 '도로 검증 끝났어'라고 알려주세요.")


if __name__ == "__main__":
    main()
