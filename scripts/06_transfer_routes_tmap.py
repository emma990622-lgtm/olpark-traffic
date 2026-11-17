"""
환승주차 후보(역 공영주차장)의 좌표를 주소로 찾고, 주변 역까지 실제 도보 거리를 TMAP으로 계산한다.
→ 어느 역에서 지하철을 타면 되는지, 주차장에서 역까지 몇 분인지 정한다.

  run_transfer_tmap.bat 더블클릭 → TMAP 앱키 붙여넣기
결과: web/data/transfer_tmap.json
"""
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "data" / "transfer_tmap.json"
BASE = "https://apis.openapi.sk.com/tmap"

# 주차장 주소(서울시 공영주차장 정보)와 걸어서 갈 만한 역 후보
LOTS = {
    "천호역 공영주차장": ("서울 강동구 천호동 455", ["천호역 5호선", "천호역 8호선"]),
    "잠실역 공영주차장": ("서울 송파구 신천동 27", ["잠실역 8호선", "잠실역 2호선"]),
    "복정역 공영주차장": ("서울 송파구 장지동 600-2", ["복정역 8호선"]),
    "신천유수지 공영주차장": ("서울 송파구 오금로 1", ["잠실역 8호선", "석촌역 9호선", "석촌역 8호선", "몽촌토성역", "잠실나루역"]),
}


def call(key, url, body=None):
    req = urllib.request.Request(url, method="POST" if body else "GET",
                                 data=json.dumps(body).encode() if body else None,
                                 headers={"appKey": key, "Accept": "application/json",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def geocode(key, addr):
    q = urllib.parse.urlencode({"version": 1, "format": "json", "coordType": "WGS84GEO", "fullAddr": addr})
    c = call(key, f"{BASE}/geo/fullAddrGeo?{q}")["coordinateInfo"]["coordinate"][0]
    lat = c.get("lat") or c.get("newLat"); lon = c.get("lon") or c.get("newLon")
    return float(lat), float(lon)


def poi(key, word):
    q = urllib.parse.urlencode({"version": 1, "searchKeyword": word, "count": 1,
                                "resCoordType": "WGS84GEO", "reqCoordType": "WGS84GEO"})
    p = call(key, f"{BASE}/pois?{q}")["searchPoiInfo"]["pois"]["poi"][0]
    lat = p.get("frontLat") or p.get("noorLat"); lon = p.get("frontLon") or p.get("noorLon")
    return p.get("name", word), float(lat), float(lon)


def walk(key, a, b, an, bn):
    d = call(key, f"{BASE}/routes/pedestrian?version=1&format=json", {
        "startX": str(a[1]), "startY": str(a[0]), "endX": str(b[1]), "endY": str(b[0]),
        "reqCoordType": "WGS84GEO", "resCoordType": "WGS84GEO", "startName": an, "endName": bn})
    p = d["features"][0]["properties"]
    return int(p["totalDistance"]), round(int(p["totalTime"]) / 60)


def main():
    key = os.environ.get("TMAP_APP_KEY") or input("TMAP(SK 오픈API) 앱키를 붙여넣고 Enter: ").strip()
    out = {"measured": time.strftime("%Y-%m-%d"), "lots": {}}
    for name, (addr, stations) in LOTS.items():
        try:
            lat, lng = geocode(key, addr)
        except Exception as e:
            print(f"{name}: 주소 찾기 실패 ({e})"); continue
        item = {"addr": addr, "lat": lat, "lng": lng, "stations": []}
        print(f"{name}: {lat:.5f}, {lng:.5f}")
        for s in stations:
            try:
                sname, slat, slng = poi(key, s)
                m, mins = walk(key, (lat, lng), (slat, slng), name, sname)
                item["stations"].append({"query": s, "name": sname, "lat": slat, "lng": slng,
                                         "meters": m, "minutes": mins})
                print(f"   → {sname}: {m}m, {mins}분")
            except Exception as e:
                print(f"   → {s}: 실패 ({e})")
            time.sleep(0.4)
        item["stations"].sort(key=lambda x: x["meters"])
        out["lots"][name] = item
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n저장 → {OUT}\nClaude에게 '환승 계산 끝났어'라고 알려주세요.")


if __name__ == "__main__":
    main()
