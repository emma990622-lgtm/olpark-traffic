"""
주차장·역 → KSPO DOME 실제 도보 거리·시간을 TMAP 보행자 경로안내 API로 한 번 계산해 저장한다.
(걷는 길은 매일 같으므로 실시간으로 부를 필요가 없다)

  run_walk_tmap.bat 더블클릭 → TMAP 앱키 붙여넣기
  또는  set TMAP_APP_KEY=앱키  후  python scripts\\05_walk_times_tmap.py

결과: web/data/walk_tmap.json  (웹앱이 있으면 이 값을, 없으면 직선거리 추정값을 쓴다)
      web/data/walk_routes.geojson  (실제 걷는 길 선 좌표, 3D 지도에 그림)
표준 라이브러리만 사용. 키는 파일에 저장하지 않는다.
"""
import json
import os
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLACES = ROOT / "web" / "data" / "places.json"
OUT = ROOT / "web" / "data" / "walk_tmap.json"
GEO = ROOT / "web" / "data" / "walk_routes.geojson"
URL = "https://apis.openapi.sk.com/tmap/routes/pedestrian?version=1&format=json"


def route(key, sx, sy, ex, ey, sname, ename):
    body = json.dumps({
        "startX": str(sx), "startY": str(sy), "endX": str(ex), "endY": str(ey),
        "reqCoordType": "WGS84GEO", "resCoordType": "WGS84GEO",
        "startName": sname, "endName": ename,
    }).encode("utf-8")
    req = urllib.request.Request(URL, data=body, method="POST", headers={
        "appKey": key, "Content-Type": "application/json", "Accept": "application/json"})
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
    targets = [("lot", x["name"], x["lat"], x["lng"]) for x in places["lots"] if x.get("lat")]
    targets += [("station", s["name"], s["lat"], s["lng"]) for s in places["stations"]]
    out = {"to": "KSPO DOME", "measured": time.strftime("%Y-%m-%d"), "items": {}}
    geo = {"type": "FeatureCollection", "features": []}
    for kind, name, lat, lng in targets:
        try:
            m, mins, line = route(key, lng, lat, dome["lng"], dome["lat"], name, "KSPO DOME")
            out["items"][name] = {"kind": kind, "meters": m, "minutes": mins}
            if len(line) >= 2:
                geo["features"].append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": line},
                                        "properties": {"from": name, "kind": kind, "meters": m, "minutes": mins}})
            print(f"  {name}: {m}m, {mins}분")
        except Exception as e:
            print(f"  {name}: 실패 ({e})")
        time.sleep(0.5)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    GEO.write_text(json.dumps(geo, ensure_ascii=False), encoding="utf-8")
    print(f"걷는 길 선 {len(geo['features'])}개 저장 → {GEO}")
    print(f"저장 → {OUT}\nClaude에게 '도보 계산 끝났어'라고 알려주세요.")


if __name__ == "__main__":
    main()
