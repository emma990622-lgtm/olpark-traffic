"""
주차장·역 → 각 공연장(KSPO DOME, 올림픽홀, 우리금융아트홀, 뮤즈라이브, 핸드볼경기장)
실제 도보 거리·시간을 TMAP 보행자 경로안내 API로 한 번 계산해 저장한다.
공연장 위치는 TMAP 장소 검색(POI)으로 찾는다. (걷는 길은 매일 같으므로 실시간으로 부를 필요가 없다)

  run_walk_tmap.bat 더블클릭 → TMAP 앱키 붙여넣기
  또는  set TMAP_APP_KEY=앱키  후  python scripts\\05_walk_times_tmap.py

결과: web/data/walk_tmap.json      (공연장별 위치 + 주차장·역에서 걷는 거리·시간)
      web/data/walk_routes.geojson (실제 걷는 길 선 좌표, 3D 지도에 그림. properties.to = 공연장)
표준 라이브러리만 사용. 키는 파일에 저장하지 않는다.
"""
import json
import math
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLACES = ROOT / "web" / "data" / "places.json"
OUT = ROOT / "web" / "data" / "walk_tmap.json"
GEO = ROOT / "web" / "data" / "walk_routes.geojson"
URL = "https://apis.openapi.sk.com/tmap/routes/pedestrian?version=1&format=json"
POI = "https://apis.openapi.sk.com/tmap/pois"

# 공연 목록의 공연장 이름 → TMAP에서 찾을 검색어 (앞에서부터 시도)
VENUES = {
    "올림픽홀": ["올림픽공원 올림픽홀", "올림픽홀"],
    "우리금융아트홀": ["우리금융아트홀", "올림픽공원 우리금융아트홀"],
    "뮤즈라이브": ["뮤즈라이브", "올림픽공원 뮤즈라이브"],
    "핸드볼경기장": ["티켓링크 라이브 아레나", "SK올림픽핸드볼경기장", "올림픽공원 핸드볼경기장"],
}
SAME_AS = {"뮤즈라이브": "올림픽홀"}   # 못 찾으면 같은 건물 좌표를 쓴다 (뮤즈라이브는 올림픽홀 안)


def dist(lat1, lng1, lat2, lng2):
    k = math.cos(math.radians(lat1))
    return math.hypot((lng1 - lng2) * 111320 * k, (lat1 - lat2) * 110540)


def headers(key):
    return {"appKey": key, "Content-Type": "application/json", "Accept": "application/json"}


def find_venue(key, words, dome):
    """TMAP 장소 검색으로 공연장 좌표 찾기. 공원(KSPO DOME 1.5km 안)에 있는 것만, 주차장·출입구는 뺀다."""
    for w in words:
        q = urllib.parse.urlencode({
            "version": 1, "searchKeyword": w, "count": 10,
            "reqCoordType": "WGS84GEO", "resCoordType": "WGS84GEO",
            "centerLon": dome["lng"], "centerLat": dome["lat"], "radius": 2,
        })
        req = urllib.request.Request(f"{POI}?{q}", headers=headers(key))
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read().decode("utf-8")
            pois = json.loads(raw)["searchPoiInfo"]["pois"]["poi"] if raw.strip() else []
        except Exception as e:
            print(f"    '{w}' 검색 실패 ({e})")
            pois = []
        for p in pois:
            name = p.get("name", "")
            if any(x in name for x in ("주차", "입구", "출입", "정류장", "매표")):
                continue
            lat, lng = float(p["noorLat"]), float(p["noorLon"])
            if dist(lat, lng, dome["lat"], dome["lng"]) <= 1500:
                return {"lat": round(lat, 6), "lng": round(lng, 6), "found": name}
        time.sleep(0.3)
    return None


def route(key, sx, sy, ex, ey, sname, ename):
    body = json.dumps({
        "startX": str(sx), "startY": str(sy), "endX": str(ex), "endY": str(ey),
        "reqCoordType": "WGS84GEO", "resCoordType": "WGS84GEO",
        "startName": sname, "endName": ename,
    }).encode("utf-8")
    req = urllib.request.Request(URL, data=body, method="POST", headers=headers(key))
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read().decode("utf-8"))
    p = d["features"][0]["properties"]          # 첫 번째 지점에 총거리·총시간이 들어 있다
    line = []                                     # LineString 조각들을 이어 붙여 한 줄로
    for f in d["features"]:
        if f["geometry"]["type"] == "LineString":
            for c in f["geometry"]["coordinates"]:
                if not line or line[-1] != c:
                    line.append(c)
    return int(p["totalDistance"]), round(int(p["totalTime"]) / 60), line


def main():
    key = os.environ.get("TMAP_APP_KEY") or input("TMAP(SK 오픈API) 앱키를 붙여넣고 Enter: ").strip()
    if not key:
        raise SystemExit("키가 비어 있습니다.")
    places = json.loads(PLACES.read_text(encoding="utf-8"))
    dome = places["dome"]

    # 1) 공연장 위치
    print("[1] 공연장 위치 찾기")
    venues = {"KSPO DOME": {"lat": dome["lat"], "lng": dome["lng"], "found": "기준 좌표"}}
    for name, words in VENUES.items():
        v = find_venue(key, words, dome)
        if not v and SAME_AS.get(name) in venues:
            v = dict(venues[SAME_AS[name]], found=f"{SAME_AS[name]}와 같은 건물")
        if v:
            venues[name] = v
            print(f"  {name}: {v['found']} ({v['lat']}, {v['lng']})")
        else:
            print(f"  {name}: 찾지 못함 → 웹앱에서는 KSPO DOME 기준으로 보여요")

    # 2) 주차장·역 → 각 공연장 걷는 길
    targets = [("lot", x["name"], x["lat"], x["lng"]) for x in places["lots"] if x.get("lat")]
    targets += [("station", s["name"], s["lat"], s["lng"]) for s in places["stations"]]
    out = {"measured": time.strftime("%Y-%m-%d"), "venues": {}}
    geo = {"type": "FeatureCollection", "features": []}
    cache = {}                                    # 같은 좌표 공연장(뮤즈라이브=올림픽홀)은 다시 안 부름
    for vname, v in venues.items():
        print(f"\n[2] → {vname}")
        items = {}
        for kind, name, lat, lng in targets:
            ck = (name, v["lat"], v["lng"])
            try:
                if ck not in cache:
                    cache[ck] = route(key, lng, lat, v["lng"], v["lat"], name, vname)
                    time.sleep(0.4)
                m, mins, line = cache[ck]
                items[name] = {"kind": kind, "meters": m, "minutes": mins}
                if len(line) >= 2:
                    geo["features"].append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": line},
                                            "properties": {"from": name, "to": vname, "kind": kind, "meters": m, "minutes": mins}})
                print(f"  {name}: {m}m, {mins}분")
            except Exception as e:
                print(f"  {name}: 실패 ({e})")
        out["venues"][vname] = {**v, "items": items}
    # 예전 형식도 함께 (KSPO DOME 기준)
    out["to"] = "KSPO DOME"
    out["items"] = out["venues"]["KSPO DOME"]["items"]
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    GEO.write_text(json.dumps(geo, ensure_ascii=False), encoding="utf-8")
    print(f"\n걷는 길 선 {len(geo['features'])}개 저장 → {GEO}")
    print(f"저장 → {OUT}\nClaude에게 '도보 계산 끝났어'라고 알려주세요.")


if __name__ == "__main__":
    main()
