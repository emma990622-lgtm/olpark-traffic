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


def dist(a, b):
    k = math.cos(math.radians(a[1]))
    return math.hypot((a[0] - b[0]) * 111320 * k, (a[1] - b[1]) * 110540)


def route(key, a, b):
    body = json.dumps({"startX": str(a[0]), "startY": str(a[1]), "endX": str(b[0]), "endY": str(b[1]),
                       "reqCoordType": "WGS84GEO", "resCoordType": "WGS84GEO",
                       "searchOption": "0", "trafficInfo": "N"}).encode()
    req = urllib.request.Request(URL, data=body, method="POST",
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
        try:
            line, total = route(key, l["a"], l["b"])
            # 돌아가는 길로 잡히면(구간 길이의 2배 초과) 쓰지 않고 직선으로 둔다
            if len(line) >= 2 and total <= max(2 * float(l["len"]), float(l["len"]) + 300):
                out["features"].append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": line},
                                        "properties": {"id": l["id"], "road": l["road"], "meters": total}})
                ok += 1
            else:
                skip += 1
                print(f"  {l['road']} {l['from']}→{l['to']}: 경로가 너무 돌아가서 직선 사용 ({total}m)")
        except Exception as e:
            skip += 1
            print(f"  {l['road']} {l['from']}→{l['to']}: 실패 ({e})")
        time.sleep(0.3)
    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"\n도로 모양 {ok}개 저장, {skip}개는 직선 → {OUT}\nClaude에게 '도로 모양 끝났어'라고 알려주세요.")


if __name__ == "__main__":
    main()
