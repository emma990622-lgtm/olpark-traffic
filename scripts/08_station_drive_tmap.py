"""
환승주차 역 주차장 → 올림픽공원 주차장, 자동차로 몇 분 걸리는지 TMAP으로 계산한다.
(역 주차장까지 와서 "여기 댈까, 공원까지 차로 더 갈까"를 비교하려는 값)

  1) 지금 시각 기준 소요시간: TMAP 자동차 경로안내 (실시간 교통 반영)
  2) 다가오는 공연별 예측: TMAP 타임머신 자동차 길안내 (공연 시작 1시간 30분 전 출발 기준)
     타임머신을 쓸 수 없는 키면 1)만 저장한다.

  run_station_drive.bat 더블클릭 → TMAP 앱키 붙여넣기
결과: web/data/station_drive.json
"""
import datetime as dt
import json
import os
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLACES = ROOT / "web" / "data" / "places.json"
EVENTS = ROOT / "web" / "data" / "events.json"
OUT = ROOT / "web" / "data" / "station_drive.json"
BASE = "https://apis.openapi.sk.com/tmap"
LEAD_MIN = 90            # 공연 시작 몇 분 전에 역 주차장에서 출발한다고 보나
DAYS_AHEAD = 21          # 앞으로 며칠 공연까지 예측하나
VENUES = ("KSPO DOME", "핸드볼경기장", "올림픽홀")   # 차가 많이 몰리는 공연장만 예측 (호출 수 절약)


def post(key, url, body):
    req = urllib.request.Request(url, method="POST", data=json.dumps(body).encode("utf-8"),
                                 headers={"appKey": key, "Accept": "application/json",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))


def totals(d):
    p = d.get("properties") or {}
    if "totalTime" not in p:
        p = d["features"][0]["properties"]
    return round(int(p["totalTime"]) / 60), round(int(p["totalDistance"]) / 1000, 1)


def drive_now(key, a, b):
    d = post(key, f"{BASE}/routes?version=1&format=json", {
        "startX": str(a[1]), "startY": str(a[0]), "endX": str(b[1]), "endY": str(b[0]),
        "reqCoordType": "WGS84GEO", "resCoordType": "WGS84GEO", "searchOption": "0", "trafficInfo": "N"})
    return totals(d)


def drive_at(key, a, b, when):
    d = post(key, f"{BASE}/routes/prediction?version=1&reqCoordType=WGS84GEO&resCoordType=WGS84GEO&sort=index", {
        "routesInfo": {
            "departure": {"name": "역 주차장", "lon": str(a[1]), "lat": str(a[0])},
            "destination": {"name": "올림픽공원 주차장", "lon": str(b[1]), "lat": str(b[0])},
            "predictionType": "departure", "predictionTime": when.strftime("%Y-%m-%dT%H:%M:00+0900"),
            "searchOption": "00", "tollgateCarType": "car", "trafficInfo": "N"}})
    return totals(d)


def main():
    key = os.environ.get("TMAP_APP_KEY") or input("TMAP(SK 오픈API) 앱키를 붙여넣고 Enter: ").strip()
    if not key:
        raise SystemExit("키가 비어 있습니다.")
    places = json.loads(PLACES.read_text(encoding="utf-8"))
    park = next(x for x in places["lots"] if x["kind"] == "park")
    dest = (park["lat"], park["lng"])
    lots = [x for x in places["lots"] if x["kind"] == "transfer" and x.get("lat")]
    now = dt.datetime.now()
    out = {"to": park["name"], "measured": now.strftime("%Y-%m-%d %H:%M"), "leadMin": LEAD_MIN,
           "now": {}, "predicted": {}}

    print("[1] 지금 기준")
    for l in lots:
        try:
            m, km = drive_now(key, (l["lat"], l["lng"]), dest)
            out["now"][l["name"]] = {"min": m, "km": km}
            print(f"  {l['name']} → 공원 주차장: {m}분, {km}km")
        except Exception as e:
            print(f"  {l['name']}: 실패 ({e})")
        time.sleep(0.4)

    print(f"\n[2] 공연별 예측 (시작 {LEAD_MIN}분 전 출발)")
    today = now.date().isoformat()
    last = (now.date() + dt.timedelta(days=DAYS_AHEAD)).isoformat()
    slots = sorted({f"{e['date']} {t}" for e in json.loads(EVENTS.read_text(encoding="utf-8"))
                    if today <= e["date"] <= last and e["venue"] in VENUES for t in e["times"]})
    ok = True
    for s in slots:
        when = dt.datetime.strptime(s, "%Y-%m-%d %H:%M") - dt.timedelta(minutes=LEAD_MIN)
        if when < now or not ok:
            continue
        for l in lots:
            try:
                m, km = drive_at(key, (l["lat"], l["lng"]), dest, when)
                out["predicted"].setdefault(s, {})[l["name"]] = m
            except Exception as e:
                print(f"  타임머신 길안내를 쓸 수 없어요 ({e}). 지금 기준 값만 저장합니다.")
                ok = False
                break
            time.sleep(0.4)
        if ok and s in out["predicted"]:
            print(f"  {s} 공연 ({when:%H:%M} 출발): " + ", ".join(f"{k.split()[0]} {v}분" for k, v in out["predicted"][s].items()))
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n저장 → {OUT}\nClaude에게 '역 운전시간 끝났어'라고 알려주세요.")


if __name__ == "__main__":
    main()
