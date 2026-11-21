"""
기상청 지상(종관, ASOS) 시간자료 — 서울(108) — 받기. 주인 컴퓨터에서 실행(인증키 DATAGO_KEY 필요, 출력하지 않음).
  공공데이터포털 '기상청_지상(종관, ASOS) 시간자료 조회서비스'(15057210) 활용신청 필요.
  결과: data/raw/weather_asos_108.csv (시각, 기온, 강수량, 풍속, 습도, 적설, 체감온도)
  체감온도 = 기상청 겨울철 체감온도식(기온 10도 이하·풍속 1.3m/s 이상일 때), 그 밖에는 기온.
  이미 받은 달은 건너뛰고 새 달만 받는다. 어제까지만 제공된다.
  실행: python scripts\\26_get_asos.py [시작 YYYY-MM]   (기본 2024-01)
"""
import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/raw/weather_asos_108.csv"
URL = "https://apis.data.go.kr/1360000/AsosHourlyInfoService/getWthrDataList"
STN = "108"
COLS = ["tm", "ta", "rn", "ws", "hm", "dsnw", "feels"]


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def feels(t, ws):
    if t is None:
        return None
    if ws is None or t > 10 or ws < 1.3:
        return t
    v = (ws * 3.6) ** 0.16
    return round(13.12 + 0.6215 * t - 11.37 * v + 0.3965 * t * v, 1)


def month_rows(key, y, m):
    first = date(y, m, 1)
    last = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
    last = min(last, date.today() - timedelta(days=1))
    if last < first:
        return []
    k = key if "%" in key else urllib.parse.quote(key, safe="")
    q = urllib.parse.urlencode({"pageNo": 1, "numOfRows": 999, "dataType": "JSON", "dataCd": "ASOS", "dateCd": "HR",
                                "startDt": first.strftime("%Y%m%d"), "startHh": "00",
                                "endDt": last.strftime("%Y%m%d"), "endHh": "23", "stnIds": STN})
    for i in range(4):
        try:
            with urllib.request.urlopen(f"{URL}?serviceKey={k}&{q}", timeout=60) as r:
                raw = r.read().decode("utf-8", errors="replace")
            j = json.loads(raw)
            break
        except ValueError:
            if "SERVICE_KEY" in raw or "등록되지 않은" in raw:
                raise SystemExit("인증키가 아직 이 서비스에 등록되지 않았어요. 활용신청 승인 뒤 1~2시간 지나 다시 실행해 주세요.")
            time.sleep(3 * (i + 1))
        except Exception:
            time.sleep(3 * (i + 1))
    else:
        raise SystemExit(f"{y}-{m:02d} 받기 실패(인터넷 또는 서버 문제). 잠시 뒤 다시 실행해 주세요.")
    h = j.get("response", {}).get("header", {})
    if h.get("resultCode") not in ("00", None):
        raise SystemExit(f"기상청 응답 오류: {h.get('resultCode')} {h.get('resultMsg')}")
    items = j["response"]["body"]["items"]["item"]
    out = []
    for it in items:
        t, ws = num(it.get("ta")), num(it.get("ws"))
        out.append([it.get("tm"), t, num(it.get("rn")) or 0.0, ws, num(it.get("hm")), num(it.get("dsnw")), feels(t, ws)])
    return out


def main():
    key = os.environ.get("DATAGO_KEY", "").strip()
    if not key:
        raise SystemExit("DATAGO_KEY 환경변수가 없어요. set_keys.bat을 먼저 실행해 주세요.")
    start = sys.argv[1] if len(sys.argv) > 1 else "2024-01"
    have = {}
    if OUT.exists():
        with open(OUT, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                have[r["tm"]] = [r[c] for c in COLS]
    done = {k[:7] for k in have}
    y, m = map(int, start.split("-"))
    today = date.today()
    while (y, m) <= (today.year, today.month):
        ym = f"{y}-{m:02d}"
        is_cur = (y, m) == (today.year, today.month) or (y, m) == ((today - timedelta(days=1)).year, (today - timedelta(days=1)).month)
        if ym not in done or is_cur:
            rows = month_rows(key, y, m)
            for r in rows:
                have[r[0]] = r
            print(f"{ym}: {len(rows)}시간")
            time.sleep(0.5)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(COLS)
        for k in sorted(have):
            w.writerow(have[k])
    print(f"저장: {OUT.relative_to(ROOT)} ({len(have)}시간, 서울 108 지점)")


if __name__ == "__main__":
    main()
