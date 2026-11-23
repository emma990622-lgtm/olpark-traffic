"""
예매처(공식 판매처) 공연 정보로 web/data/events.json을 바로잡는다.
  입력: data/processed/show_official.csv  — 사람이 예매처 상세 페이지에서 옮겨 적은 표(출처 URL·확인일 포함)
        칸: title_key(공연명 일부), venue, date(*=모든 날), time(*=그대로), run_min(관람시간 분, 없으면 빈칸), run_text, seller, url, checked
  하는 일:
    1) 회차: 예매처의 날짜·시작 시각으로 바꾼다. 공연 일정 원본은 여러 날 회차를 첫날에 몰아 적은 경우가 있다
       (예: DAY6 12/18에 17·18·19시 → 예매처는 12/18 19시, 12/19 18시, 12/20 17시).
    2) 관람시간: runMin(분), runText, runSeller, runUrl, runChecked를 붙인다. 관객 화면 '예정 종료' = 시작 + runMin.
  scripts/04_build_web_data.py가 events.json을 다시 만들 때 끝에서 이 스크립트를 부른다.

  실행: python scripts\\27_official_shows.py
"""
import csv
import json
import unicodedata
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "processed" / "show_official.csv"
EV = ROOT / "web" / "data" / "events.json"
DOW = "월화수목금토일"


def norm(s):
    return "".join(unicodedata.normalize("NFKC", s or "").casefold().split())


def main():
    events = json.loads(EV.read_text(encoding="utf-8"))
    rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
    groups = {}
    for r in rows:
        groups.setdefault((r["title_key"], r["venue"]), []).append(r)
    changed = []
    for (key, venue), rs in groups.items():
        k = norm(key)
        hit = [e for e in events if e["venue"] == venue and k in norm(e["title"])]
        if not hit:
            print(f"! 일정에 없음: {key} ({venue})")
            continue
        def run_fields(r):
            f = {"runText": r["run_text"], "runSeller": r["seller"], "runUrl": r["url"], "runChecked": r["checked"]}
            if r["run_min"]:
                f["runMin"] = int(r["run_min"])
            return f
        if rs[0]["date"] == "*":
            for e in hit:
                e.update(run_fields(rs[0]))
            changed.append(f"{key}: 관람시간 {rs[0]['run_text']} ({len(hit)}일)")
            continue
        base = {k2: hit[0][k2] for k2 in ("venue", "seats", "title", "longRun")}
        events = [e for e in events if e not in hit]
        by_date = {}
        for r in rs:
            by_date.setdefault(r["date"], []).append(r)
        for d, rr in by_date.items():
            y, m, dd = map(int, d.split("-"))
            e = {"date": d, "dow": DOW[date(y, m, dd).weekday()], **base, "times": sorted(r["time"] for r in rr)}
            e.update(run_fields(rr[0]))
            events.append(e)
        old = sorted((e["date"], tuple(e["times"])) for e in hit)
        new = sorted((d, tuple(sorted(r["time"] for r in rr))) for d, rr in by_date.items())
        changed.append(f"{key}: 회차 {'그대로' if old == new else f'{old} → {new}'}, 관람시간 {rs[0]['run_text']}")
    events.sort(key=lambda e: (e["date"], e["venue"], e["times"][0] if e["times"] else ""))
    EV.write_text(json.dumps(events, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("\n".join(changed))
    print("저장:", EV)


if __name__ == "__main__":
    main()
