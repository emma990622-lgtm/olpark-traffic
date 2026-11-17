"""
도로 58구간의 실제 도로 모양(선 좌표)을 TMAP 자동차 경로로 한 번 받아 저장한다.
(서울시 도시데이터는 각 구간의 시작점·끝점만 준다)

  run_link_shapes.bat 더블클릭 → TMAP 앱키 붙여넣기
결과: web/data/link_shapes.geojson
"""
import json
import math
import os
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINKS = ROOT / "web" / "data" / "links.json"
OUT = ROOT / "web" / "data" / "link_shapes.geojson"
URL = "https://apis.openapi.sk.com/tmap/routes?version=1&format=json"
URL_WALK = "https://apis.openapi.sk.com/tmap/routes/pedestrian?version=1&format=json"


def dist(a, b):
    k = math.cos(math.radians(a[1]))
    return math.hypot((a[0] - b[0]) * 111320 * k, (a[1] - b[1]) * 110540)


def route(key, a, b, walk=False):
    p = {"startX": str(a[0]), "startY": str(a[1]), "endX": str(b[0]), "endY": str(b[1]),
         "reqCoordType": "WGS84GEO", "resCoordType": "WGS84GEO"}
    p.update({"startName": "a", "endName": "b"} if walk else {"searchOption": "0", "trafficInfo": "N"})
    body = json.dumps(p).encode()
    req = urllib.request.Request(URL_WALK if walk else URL, data=body, method="POST",
                                 headers={"appKey": key, "Content-Type": "application/json", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read().decode("utf-8"))
    line = []
    for f in d["features"]:
        if f["geometry"]["type"] == "LineString":
            for c in f["geometry"]["coordinates"]:
                if not line or line[-1] != c:
                    line.append(c)
    total = int(d["features"][0]["properties"].get("totalDistance", 0))
    return line, total


def main():
    key = os.environ.get("TMAP_APP_KEY") or input("TMAP(SK 오픈API) 앱키를 붙여넣고 Enter: ").strip()
    links = json.loads(LINKS.read_text(encoding="utf-8"))
    out = {"type": "FeatureCollection", "features": []}
    ok = skip = 0
    for l in links:
        ln = float(l["len"])
        limit = max(1.5 * ln, ln + 150)          # 구간 길이보다 많이 길면 돌아간 길로 보고 버린다
        got = None
        for walk in (False, True):               # 자동차 경로 → 안 되면 보행자 경로(인도는 도로를 따라 곧게 이어짐)
            try:
                line, total = route(key, l["a"], l["b"], walk)
                if len(line) >= 2 and total <= limit:
                    got = (line, total, "보행자" if walk else "자동차")
                    break
            except Exception as e:
                print(f"  {l['road']} {l['from']}→{l['to']} ({'보행자' if walk else '자동차'}): 실패 ({e})")
            time.sleep(0.3)
        if got:
            out["features"].append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": got[0]},
                                    "properties": {"id": l["id"], "road": l["road"], "meters": got[1], "via": got[2]}})
            ok += 1
        else:
            skip += 1
            print(f"  {l['road']} {l['from']}→{l['to']}: 직선 사용")
    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"\n도로 모양 {ok}개 저장, {skip}개는 직선 → {OUT}\nClaude에게 '도로 모양 끝났어'라고 알려주세요.")


if __name__ == "__main__":
    main()
