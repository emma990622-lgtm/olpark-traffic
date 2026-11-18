"""
한국체육산업개발 '주차장 혼잡도 정보'(공공데이터포털 15164156) 전체 받기.
구역별(동2문·남2문·북2문 등) 원활·혼잡·만차 기록이 날짜·시각과 함께 들어 있다.
→ 공원 주차장이 실제로 만차였던 날·시각을 확인하고, 입출차 기록으로 센 주차 대수(예: 2024-07-21 최대 2,213대)와 맞춰 본다.

  run_congestion.bat 더블클릭 → 공공데이터포털 인증키 붙여넣기 (set_keys.bat에 저장해 두면 묻지 않음)
결과: data/raw/kspo_parking_congestion.csv
키는 파일에 저장하지 않는다.
"""
import csv
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "kspo_parking_congestion.csv"
URL = "https://api.odcloud.kr/api/15164156/v1/uddi:34862174-8dc7-4230-9d35-ea44801c18f1"
PER = 1000


def get(key, page):
    # 공공데이터포털 키는 '인코딩'(%가 들어 있음)과 '디코딩' 두 가지가 있어 둘 다 받도록 처리
    k = key if "%" in key else urllib.parse.quote(key, safe="")
    url = f"{URL}?page={page}&perPage={PER}&returnType=JSON&serviceKey={k}"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    key = os.environ.get("DATAGO_KEY") or input("공공데이터포털 인증키(일반 인증키)를 붙여넣고 Enter: ").strip()
    if not key:
        raise SystemExit("키가 비어 있습니다.")
    first = get(key, 1)
    total = int(first.get("totalCount") or 0)
    rows = list(first.get("data") or [])
    print(f"전체 {total:,}건")
    page = 2
    while len(rows) < total:
        d = get(key, page)
        got = d.get("data") or []
        if not got:
            break
        rows += got
        print(f"  {len(rows):,} / {total:,}")
        page += 1
    if not rows:
        raise SystemExit("받은 자료가 없습니다. 키가 이 데이터에 '활용신청' 승인됐는지 확인하세요.")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cols = list(rows[0].keys())
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    days = sorted({str(r.get("등록일")) for r in rows})
    print(f"저장 → {OUT}  ({len(rows):,}건, {days[0]} ~ {days[-1]})")
    from collections import Counter
    print("구역:", dict(Counter(r.get("주차구역") for r in rows)))
    print("혼잡도:", dict(Counter(r.get("혼잡도") for r in rows)))
    print("Claude에게 '혼잡도 받았어'라고 알려주세요.")


if __name__ == "__main__":
    main()
