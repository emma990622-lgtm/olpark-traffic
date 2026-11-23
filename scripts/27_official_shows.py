"""
공연 일정 → web/data/events.json (관객 화면 '어떤 공연에 가세요?')
  입력: data/processed/event_days.csv   scripts/02가 만든 날짜별 공연(공원 공식 일정 + 예매처에서 읽은 시각·관람시간)
        data/processed/show_official.csv 사람이 예매처에서 직접 옮겨 적은 회차·관람시간(자동으로 못 읽은 공연만 씀)
            칸: title_key(공연명 일부), venue, date(*=모든 날), time(*=그대로), run_min(없으면 빈칸), run_text, seller, url, checked
  각 공연에 붙는 관람시간 칸 (화면 '예정 종료' = 시작 + runMin)
    runMin, runText  관람시간(분)·원문. 어디에도 안내가 없으면 runMin 없음
    runFrom          seller = 예매처 페이지에서 읽음 / park = 올림픽공원 공식 일정의 관람시간 칸
    runSeller, runUrl 예매처 이름·링크, runChecked 읽은 날
  scripts/28_update_shows.py(매일 자동)와 scripts/04_build_web_data.py가 부른다.

  실행: python scripts\\27_official_shows.py
"""
import csv
import json
import math
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DAYS = ROOT / "data" / "processed" / "event_days.csv"
SRC = ROOT / "data" / "processed" / "show_official.csv"
EV = ROOT / "web" / "data" / "events.json"
DOW = "월화수목금토일"
TODAY = datetime.now(timezone(timedelta(hours=9))).date().isoformat()


def norm(s):
    return "".join(unicodedata.normalize("NFKC", s or "").casefold().split())


def blank(v):
    return v is None or (isinstance(v, float) and math.isnan(v)) or str(v).strip() in ("", "nan")


def build():
    ev = pd.read_csv(DAYS, encoding="utf-8-sig")
    ev = ev[(ev["날짜"] >= TODAY) | (ev["날짜"].str.startswith("2024-07"))]  # 앞으로 공연 + 2024년 7월(지난 자료 비교용)
    events = []
    for _, r in ev.iterrows():
        e = {
            "date": r["날짜"], "dow": r["요일"], "venue": r["공연장"],
            "seats": None if pd.isna(r["좌석규모_참고"]) else int(r["좌석규모_참고"]),
            "title": r["공연명"], "times": [t for t in str(r["시작시각들"]).split(";") if t and t != "nan"],
            "longRun": bool(r["장기공연"]),
        }
        if not blank(r.get("관람시간출처")):
            if not blank(r.get("관람시간분")):
                e["runMin"] = int(r["관람시간분"])
                e["runText"] = str(r["관람시간원문"]).strip()
            e["runFrom"] = r["관람시간출처"]
            for k, c in (("runSeller", "예매처"), ("runUrl", "예매링크"), ("runChecked", "확인일")):
                if not blank(r.get(c)):
                    e[k] = str(r[c])
        events.append(e)
    return events


def apply_manual(events):
    """show_official.csv(사람이 옮겨 적은 값)는 예매처 페이지를 자동으로 못 읽은 공연에만 쓴다."""
    if not SRC.exists():
        return events, []
    rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
    groups = {}
    for r in rows:
        groups.setdefault((r["title_key"], r["venue"]), []).append(r)
    log = []
    for (key, venue), rs in groups.items():
        k = norm(key)
        hit = [e for e in events if e["venue"] == venue and k in norm(e["title"])]
        if not hit:
            continue
        if any(e.get("runFrom") == "seller" for e in hit):
            log.append(f"{key}: 예매처 자동 읽기 있음 — 손으로 적은 값 안 씀")
            continue

        def run_fields(r):
            f = {"runFrom": "seller", "runText": r["run_text"], "runSeller": r["seller"],
                 "runUrl": r["url"], "runChecked": r["checked"]}
            if r["run_min"]:
                f["runMin"] = int(r["run_min"])
            return f

        if rs[0]["date"] == "*":
            for e in hit:
                e.pop("runMin", None)
                e.update(run_fields(rs[0]))
            log.append(f"{key}: 관람시간 {rs[0]['run_text']} (손으로 적은 값)")
            continue
        base = {k2: hit[0][k2] for k2 in ("venue", "seats", "title", "longRun")}
        events = [e for e in events if e not in hit]
        by_date = {}
        for r in rs:
            by_date.setdefault(r["date"], []).append(r)
        for d, rr in by_date.items():
            if d < TODAY:
                continue
            y, m, dd = map(int, d.split("-"))
            e = {"date": d, "dow": DOW[date(y, m, dd).weekday()], **base, "times": sorted(r["time"] for r in rr)}
            e.update(run_fields(rr[0]))
            events.append(e)
        log.append(f"{key}: 회차·관람시간 손으로 적은 값으로")
    return events, log


def main():
    events, log = apply_manual(build())
    events.sort(key=lambda e: (e["date"], e["venue"], e["times"][0] if e["times"] else ""))
    EV.write_text(json.dumps(events, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    fut = [e for e in events if e["date"] >= TODAY]
    print("\n".join(log))
    print(f"저장: {EV} (앞으로 {len(fut)}일·공연장, 관람시간 있음 {sum('runMin' in e for e in fut)})")


if __name__ == "__main__":
    main()
