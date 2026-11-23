"""
웹앱(web/)이 읽는 JSON 파일을 만든다.  (pandas 필요)

  python scripts\\04_build_web_data.py

만드는 파일 (web/data/)
  events.json        공연 일정 (공연일 표 → 오늘 이후 + 2024-07 분석일)
  links.json         도로 58구간 (좌표, 이름)
  places.json        주차장·역·공연장 위치와 기본 정보
  exits_2024_07.json 2024년 7월 공연일·평일의 15분 출차 곡선 (시험용 실제 데이터)

2025 입출차가 다 받아지면 같은 방식으로 exits_2025.json(출구별)을 추가한다.
"""
import json
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW, PROC, OUT = ROOT / "data" / "raw", ROOT / "data" / "processed", ROOT / "web" / "data"
OUT.mkdir(parents=True, exist_ok=True)

DOME = (37.51916, 127.127514)   # KSPO DOME (위도, 경도)


def walk_min(lat, lng, to=DOME):
    """직선거리 × 1.3 ÷ 분당 75m. 실제 동선으로 다시 재야 하는 추정값."""
    r = 6371000
    p1, p2 = math.radians(lat), math.radians(to[0])
    dp, dl = p2 - p1, math.radians(to[1] - lng)
    d = 2 * r * math.asin(math.sqrt(math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2))
    return round(d), round(d * 1.3 / 75)


def dump(name, obj):
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("저장:", OUT / name)


# 1) 공연 일정 -------------------------------------------------------------
ev = pd.read_csv(PROC / "event_days.csv", encoding="utf-8-sig")
ev = ev[(ev["날짜"] >= pd.Timestamp.today().strftime("%Y-%m-%d")) |
        (ev["날짜"].str.startswith("2024-07"))]
events = []
for _, r in ev.iterrows():
    times = [t for t in str(r["시작시각들"]).split(";") if t and t != "nan"]
    events.append({
        "date": r["날짜"], "dow": r["요일"], "venue": r["공연장"],
        "seats": None if pd.isna(r["좌석규모_참고"]) else int(r["좌석규모_참고"]),
        "title": r["공연명"], "times": times, "longRun": bool(r["장기공연"]),
    })
dump("events.json", events)
# 위 events.json을 27이 다시 만든다: 관람시간(예매처·공원 공식 일정)과 손으로 적은 값(show_official.csv)까지 반영
import runpy  # noqa: E402
runpy.run_path(str(ROOT / "scripts" / "27_official_shows.py"), run_name="__main__")

# 2) 도로 58구간 ------------------------------------------------------------
lk = pd.read_csv(RAW / "olpark_links_58.csv", encoding="utf-8-sig")
links = []
for _, r in lk.iterrows():
    a = [float(v) for v in str(r["시작좌표(경도_위도)"]).split("_")]
    b = [float(v) for v in str(r["끝좌표(경도_위도)"]).split("_")]
    links.append({"id": str(r["LINK_ID"]), "road": r["도로명"], "from": r["시작지점"],
                  "to": r["끝지점"], "len": r["길이(m)"], "a": a, "b": b})
dump("links.json", links)

# 3) 장소: 주차장·역·공연장 ---------------------------------------------------
# 면수·요금·좌표: 서울시 실시간 도시데이터(PRK_STTS)·공영주차장 실시간(GetParkingInfo), 2026-11-18 수집값
places = {"dome": {"name": "KSPO DOME", "lat": DOME[0], "lng": DOME[1]}, "lots": [], "stations": []}
near = [
    ("park", "올림픽공원 주차장(동2문·남2문·북2문)", 2120, 37.517033, 127.126027, "10분당 600원, 하루 최대 20,000원", 600, 10, 20000, "합계만"),
    ("walk", "한성백제박물관 주차장", 142, 37.515347, 127.120798, "10분당 600원", 600, 10, None, "없음"),
    ("walk", "올림픽공원 남3문 주차장", 254, 37.5161214, 127.1184981, "10분당 600원", 600, 10, None, "없음"),
    ("walk", "올림픽공원 회관 외 주차장", 200, 37.5184393, 127.1161715, "10분당 600원", 600, 10, None, "없음"),
]
for kind, name, cap, lat, lng, fee, unit_won, unit_min, day_max, live in near:
    dist, wm = walk_min(lat, lng)
    places["lots"].append({"kind": kind, "name": name, "cap": cap, "lat": lat, "lng": lng,
                           "fee": fee, "won": unit_won, "per": unit_min, "dayMax": day_max,
                           "distM": dist, "walkMin": wm, "live": live})
# 환승주차: 실시간 빈자리 있음. 경로는 정거장 수만 확정, 소요시간은 자료 확보 후 채움
# 환승주차: 주차장→탈 역 도보는 TMAP 계산값(scripts/06, web/data/transfer_tmap.json)
# (이름, 면수, 요금 문구, 요금, 단위분, 탈 역, 지하철 경로, 내릴 역 key, 운영시간, 추천 여부/이유, 정거장 수, 환승 횟수)
transfer = [
    ("천호역 공영주차장", 1431, "5분당 360원", 360, 5, "천호역[수도권5호선]",
     "5호선 마천행 3정거장 → 올림픽공원역", "olympic5", "24시간", None, 3, 0),
    ("잠실역 공영주차장", 357, "5분당 440원", 440, 5, "잠실역[수도권8호선]",
     "8호선 1정거장 → 몽촌토성역 (또는 석촌역에서 9호선으로 갈아타 올림픽공원역)", "mongchon", "05:00~01:00", None, 1, 0),
    ("복정역 공영주차장", 362, "5분당 280원", 280, 5, "복정역[수도권8호선]",
     "8호선 7정거장 → 몽촌토성역 (또는 석촌역에서 9호선으로 갈아타 올림픽공원역)", "mongchon", "24시간", None, 7, 0),
    ("신천유수지 공영주차장", 192, "5분당 440원", 440, 5, "잠실나루역[수도권2호선]",
     "2호선 1정거장 → 잠실역에서 8호선 갈아타 1정거장 → 몽촌토성역", "mongchon", "24시간",
     "가장 가까운 역이 2호선이라 한 번 갈아타야 하고, 내려서도 23분을 더 걸어야 해요", 2, 1),
]
# 지하철 구간: (호선, [탈 역 → … → 내릴 역]) — /api/subway 의 공식 역간 운행시간과 맞춰 더한다
SEGMENTS = {
    "천호역 공영주차장": [("5", ["천호", "강동", "둔촌동", "올림픽공원"])],
    "잠실역 공영주차장": [("8", ["잠실", "몽촌토성"])],
    "복정역 공영주차장": [("8", ["복정", "장지", "문정", "가락시장", "송파", "석촌", "잠실", "몽촌토성"])],
    "신천유수지 공영주차장": [("2", ["잠실나루", "잠실"]), ("8", ["잠실", "몽촌토성"])],
}
tt = {}
if (OUT / "transfer_tmap.json").exists():
    tt = json.loads((OUT / "transfer_tmap.json").read_text(encoding="utf-8"))["lots"]
for name, cap, fee, won, per, board, route, st, hours, skip, stops, transfers in transfer:
    info = tt.get(name, {})
    walk_to = next((x for x in info.get("stations", []) if x["name"] == board), None)
    places["lots"].append({"kind": "transfer", "name": name, "cap": cap, "fee": fee, "won": won,
                           "per": per, "dayMax": None, "route": route, "station": st,
                           "board": board.split("[")[0], "toStationMin": walk_to["minutes"] if walk_to else None,
                           "toStationM": walk_to["meters"] if walk_to else None,
                           "lat": info.get("lat"), "lng": info.get("lng"), "hours": hours, "live": "있음",
                           "notRecommended": skip, "stops": stops, "transfers": transfers,
                           "segments": [{"line": ln, "stations": sts} for ln, sts in SEGMENTS.get(name, [])]})
for key, name, line, lat, lng in [
    ("olympic5", "올림픽공원역", "5·9호선", 37.516201, 127.130923),
    ("mongchon", "몽촌토성역", "8호선", 37.517409, 127.112359),
    ("hanseong", "한성백제역", "9호선", 37.516404, 127.116503),
]:
    dist, wm = walk_min(lat, lng)
    places["stations"].append({"key": key, "name": name, "line": line, "lat": lat, "lng": lng,
                               "distM": dist, "walkMin": wm})
places["lots"][0]["walkMin"] = max(places["lots"][0]["walkMin"], 5)
dump("places.json", places)

# 4) 2024년 7월 15분 출차 곡선 (시험용) ----------------------------------------
io = pd.read_csv(RAW / "parking_inout_202407.csv", encoding="cp949")
io["out"] = pd.to_datetime(io["출차일시"], errors="coerce")
io["in"] = pd.to_datetime(io["입차일시"], errors="coerce")
io = io.dropna(subset=["out", "in"])
dur = (io["out"] - io["in"]).dt.total_seconds() / 60
io = io[(dur > 0) & (dur < 24 * 60)]          # 0분·24시간 이상 제외 (docs/data_scope.md)

days = {}
for day in pd.date_range("2024-07-01", "2024-07-31").strftime("%Y-%m-%d"):
    s = pd.Timestamp(day + " 12:00")
    e = s + pd.Timedelta(hours=13)            # 12:00 ~ 다음날 01:00
    o = io[(io["out"] >= s) & (io["out"] < e)].set_index("out").resample("15min").size()
    i = io[(io["in"] >= s) & (io["in"] < e)].set_index("in").resample("15min").size()
    idx = pd.date_range(s, e, freq="15min", inclusive="left")
    days[day] = {"exits": o.reindex(idx, fill_value=0).astype(int).tolist(),
                 "entries": i.reindex(idx, fill_value=0).astype(int).tolist()}


def wave(day, start):
    """공연 시작 60분 뒤 ~ 360분 뒤 출차 중 최대 15분 구간(시각·대수).
    2024-07 자료는 출구 정보가 없고 공원 방문 차량이 섞여 있어, '절반이 빠지는 시간' 같은 값은
    흔들림이 커서 쓰지 않는다. 출구별 대기 시간은 2025 자료로 계산한다."""
    s = pd.Timestamp(f"{day} {start}")
    x = io[(io["out"] >= s + pd.Timedelta(minutes=60)) & (io["out"] < s + pd.Timedelta(minutes=360))]
    c = x.set_index("out").resample("15min").size()
    if c.empty:
        return None
    peak = c.idxmax()
    lag = int((peak - s).total_seconds() // 60)
    return {"peakTime": peak.strftime("%H:%M"), "peak15": int(c.max()), "lagMin": lag}


ev24 = [e for e in events if e["date"].startswith("2024-07")]
waves = {}
for e in ev24:
    if e["venue"] == "KSPO DOME" and e["times"]:
        waves[e["date"]] = {"title": e["title"], "start": e["times"][-1], **(wave(e["date"], e["times"][-1]) or {})}
dump("exits_2024_07.json", {"slotStart": "12:00", "slotMin": 15, "days": days, "kspoWaves": waves,
                            "note": "2024년 7월 실제 입출차(출구 정보 없음). 0분·24시간 이상 체류 제외."})
