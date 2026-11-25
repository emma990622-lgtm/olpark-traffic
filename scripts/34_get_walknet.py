"""
서울시 자치구별 도보 네트워크 공간정보(서울 열린데이터광장 OA-21208, 서비스 TbTraficWlkNet) 받기.

  - 서울시내 보행자도로를 노드·링크로 표현한 자료(매일 1회 갱신, 공공누리 1유형, 좌표 WGS84).
  - 링크마다 고가도로·지하철네트워크·교량·터널·육교·횡단보도·공원녹지·건물내 표시가 있어
    육교·지하도·횡단보도를 구분한 보행 안내에 쓴다.
  - 올림픽공원이 걸친 송파구·강동구를 받아 공원·주변 역(올림픽공원·몽촌토성·한성백제역) 둘레만 잘라 저장한다.

  인증키: 환경변수 SEOUL_API_KEY (값은 출력하지 않음). 키가 없는 곳에서는 실행하지 않는다.
    - 수집기 저장소(olpark-collector)의 GitHub Actions 'fetch_walknet'이 이 스크립트를 돌려 결과를 올린다.
    - 주인 컴퓨터: set SEOUL_API_KEY=… 뒤 python scripts\\34_get_walknet.py

  결과: data/raw/seoul_walknet_olpark.geojson (또는 --out 경로)
    - Point = 노드(NODE_ID, 유형 코드, 횡단보도·육교 표시)
    - LineString = 링크(LNKG_ID, 시작·끝 노드, 길이 m, 유형 코드, 고가·지하철·교량·터널·육교·횡단보도·공원·건물내 0/1)
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "seoul_walknet_olpark.geojson"
SERVICE = "TbTraficWlkNet"
SGGS = ["송파구", "강동구"]
# 올림픽공원 + 몽촌토성역·올림픽공원역·한성백제역 + 둘레 도로 (경도 서, 위도 남, 경도 동, 위도 북)
BBOX = (127.098, 37.500, 127.145, 37.536)
FLAGS = ["EXPN_CAR_RD", "SBWY_NTW", "BRG", "TNL", "OVRP", "CRSWK", "PARK", "BLDG"]
PAGE = 1000


def get(key, sgg, a, b):
    url = (f"http://openapi.seoul.go.kr:8088/{urllib.parse.quote(key)}/json/{SERVICE}/{a}/{b}/"
           f"{urllib.parse.quote(sgg)}")
    last = None
    for i in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                d = json.loads(r.read().decode("utf-8"))
            body = d.get(SERVICE) or {}
            code = (body.get("RESULT") or d.get("RESULT") or {}).get("CODE", "")
            if code and code != "INFO-000":
                raise RuntimeError(f"{code} {(body.get('RESULT') or d.get('RESULT') or {}).get('MESSAGE', '')}")
            return body
        except Exception as e:  # 잠깐 끊긴 것일 수 있어 세 번 더 (오류 문구에 키가 들어가지 않게 종류만 출력)
            last = e
            print(f"  {sgg} {a}~{b} 실패({type(e).__name__}) → {5 * (i + 1)}초 뒤 다시")
            time.sleep(5 * (i + 1))
    raise SystemExit(f"{sgg} {a}~{b}를 계속 못 받았어요: {type(last).__name__}")


def coords(wkt):
    nums = re.findall(r"(-?\d+\.\d+)\s+(-?\d+\.\d+)", wkt or "")
    return [[float(x), float(y)] for x, y in nums]


def inside(c):
    return BBOX[0] <= c[0] <= BBOX[2] and BBOX[1] <= c[1] <= BBOX[3]


def num(v):
    try:
        f = float(v)
        return int(f) if f == int(f) else f
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    key = os.environ.get("SEOUL_API_KEY", "").strip()
    if not key:
        sys.exit("환경변수 SEOUL_API_KEY 가 비어 있어요(키가 있는 곳에서만 실행).")

    feats, total, kept, dttm = [], {}, {"node": 0, "link": 0}, set()
    seen = set()  # 같은 노드·링크가 두 번 오기도 하고(구 경계), 두 구에 함께 들어 있기도 해서 한 번만 남긴다
    for sgg in SGGS:
        first = get(key, sgg, 1, PAGE)
        n = int(first.get("list_total_count") or 0)
        total[sgg] = n
        print(f"{sgg}: {n:,}줄")
        rows = first.get("row") or []
        for a in range(PAGE + 1, n + 1, PAGE):
            rows += get(key, sgg, a, min(a + PAGE - 1, n)).get("row") or []
            time.sleep(0.3)
        for r in rows:
            if r.get("WORK_DTTM"):
                dttm.add(r["WORK_DTTM"][:10])
            if r.get("NODE_TYPE") == "NODE":
                c = coords(r.get("NODE_WKT"))
                if not c or not inside(c[0]) or ("N", r.get("NODE_ID")) in seen:
                    continue
                seen.add(("N", r.get("NODE_ID")))
                feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": c[0]},
                              "properties": {"kind": "node", "id": num(r.get("NODE_ID")),
                                             "typeCd": r.get("NODE_TYPE_CD") or "",
                                             "ovrp": r.get("OVRP") or "", "crswk": r.get("CRSWK") or "",
                                             "sgg": r.get("SGG_NM"), "emd": r.get("EMD_NM")}})
                kept["node"] += 1
            elif r.get("NODE_TYPE") == "LINK":
                c = coords(r.get("LNKG_WKT"))
                if len(c) < 2 or not any(inside(p) for p in c) or ("L", r.get("LNKG_ID")) in seen:
                    continue
                seen.add(("L", r.get("LNKG_ID")))
                p = {"kind": "link", "id": num(r.get("LNKG_ID")), "typeCd": r.get("LNKG_TYPE_CD") or "",
                     "from": num(r.get("BGNG_LNKG_ID")), "to": num(r.get("END_LNKG_ID")),
                     "meters": num(r.get("LNKG_LEN")), "sgg": r.get("SGG_NM"), "emd": r.get("EMD_NM")}
                for f in FLAGS:
                    p[f.lower()] = r.get(f) or ""
                feats.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": c}, "properties": p})
                kept["link"] += 1

    kst = datetime.now(timezone(timedelta(hours=9)))
    out = {
        "type": "FeatureCollection",
        "metadata": {
            "source": "서울 열린데이터광장 '서울시 자치구별 도보 네트워크 공간정보'(OA-21208, TbTraficWlkNet), 공공누리 1유형",
            "fetched": kst.strftime("%Y-%m-%d %H:%M"),
            "workDates": sorted(dttm),
            "sgg": total,
            "bbox": BBOX,
            "kept": kept,
            "flags": "링크: expn_car_rd 고가도로, sbwy_ntw 지하철네트워크, brg 교량, tnl 터널, ovrp 육교, crswk 횡단보도, park 공원·녹지, bldg 건물내 (1=해당)",
            "codes": "노드·링크 유형 코드 표는 열린데이터광장 '도보네트워크_링크노드유형코드.xlsx'",
        },
        "features": feats,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"저장: {args.out} — 노드 {kept['node']:,}, 링크 {kept['link']:,} (수집일 {', '.join(sorted(dttm))})")


if __name__ == "__main__":
    main()
