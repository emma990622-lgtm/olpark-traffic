"""
공연 정보 자동 수집 — GitHub Actions(.github/workflows/update_shows.yml)가 하루 두 번 돌린다. 인증키 필요 없음.

  1) 올림픽공원 공식 일정: 홈페이지 '일정안내'가 쓰는 주소(eventInfoListAjax.es)에서 지난달~6달 뒤를 받는다
     → data/raw/olpark_events_live.json  (공연명·장소·기간·시각 문구·관람시간(ndTm)·예매처 링크)
  2) 예매처 페이지: 앞으로 공연의 예매처 링크를 열어 관람시간과 회차별 시작 시각 문구를 읽는다
     → data/processed/show_seller.csv
     - NOL 티켓(인터파크): 페이지 안 상품 정보의 runningTime·interMissionTime·playTimeInfo
     - YES24 티켓: 상세정보 '관람시간: …', '공연시간 안내'
     - 멜론티켓: '관람시간', '공연시간'
     - 티켓링크 등 그 밖: 읽지 않음(화면은 공원 공식 일정의 관람시간을 출처와 함께 씀)
     페이지를 못 열거나 모양이 달라 못 읽으면 지난번에 읽은 값을 그대로 둔다(지어내지 않음).
  3) scripts/02 → data/processed/event_days.csv, scripts/27 → web/data/events.json

  실행: python scripts/28_update_shows.py            (받기 + 다시 만들기)
        python scripts/28_update_shows.py --offline  (받지 않고 가진 파일로 다시 만들기만)
"""
import csv
import html
import json
import re
import runpy
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIVE = ROOT / "data" / "raw" / "olpark_events_live.json"
SELLER = ROOT / "data" / "processed" / "show_seller.csv"
PARK_URL = "https://www.ksponco.or.kr/olympicpark/eventInfo/eventInfoListAjax.es"
KEEP = ("evtSeq", "plc", "title", "beginDt", "endDt", "tm", "ndTm", "evtLink", "rsvLink", "regDate")
SELLER_COLS = ["evtSeq", "title", "seller", "url", "ok", "run_min", "run_text", "time_text", "checked"]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TODAY = datetime.now(timezone(timedelta(hours=9))).date()


def get(url, data=None, ctype=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
    if ctype:
        req.add_header("Content-Type", ctype)
    last = None
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # 잠깐 끊긴 것일 수 있어 두 번 더
            last = e
            time.sleep(2 + i * 3)
    raise last


# 1) 공원 공식 일정 ---------------------------------------------------------------
def fetch_park():
    old = {e["evtSeq"]: e for e in json.loads(LIVE.read_text(encoding="utf-8"))} if LIVE.exists() else {}
    got, months = {}, []
    y, m = TODAY.year, TODAY.month - 1
    for _ in range(8):  # 지난달 ~ 6달 뒤
        if m < 1:
            y, m = y - 1, 12
        if m > 12:
            y, m = y + 1, 1
        months.append(f"{y}{m:02d}")
        m += 1
    for ym in months:
        try:
            body = json.dumps({"nowYM": ym, "plcCd": ""}).encode()
            res = json.loads(get(PARK_URL, body, "application/json;charset=UTF-8"))
        except Exception as e:
            print(f"! 공원 일정 {ym} 실패: {type(e).__name__} {e}")
            continue
        for e in (res[0] if res else []) + (res[1] if len(res) > 1 else []):
            got[e["evtSeq"]] = {k: e.get(k) for k in KEEP} | {"_fetched": TODAY.isoformat()}
    if not got:
        print("! 공원 일정을 하나도 못 받음 — 지난번 파일을 그대로 씀")
        return list(old.values())
    new = [s for s in got if s not in old]
    old.update(got)
    out = sorted(old.values(), key=lambda e: e["evtSeq"])
    LIVE.write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"공원 일정 {len(got)}개 받음({months[0]}~{months[-1]}), 새 공연 {len(new)}개 → {LIVE.name}")
    return out


# 2) 예매처 페이지 -----------------------------------------------------------------
def seller_of(link):
    """링크 → (예매처 이름, 읽을 주소, 종류). 읽지 못하는 곳은 종류 None"""
    link = (link or "").strip()
    m = re.search(r"(?:nol\.yanolja\.com/ticket/products|interpark\.com/goods)/(\d+)", link)
    if m:
        u = f"https://nol.yanolja.com/ticket/products/{m.group(1)}"
        return "NOL 티켓", u, ("nol", m.group(1))
    m = re.search(r"ticket\.yes24\.com/(perf|special)/(\d+)", link, re.I)
    if m:
        u = f"https://ticket.yes24.com/{m.group(1).capitalize()}/{m.group(2)}"
        return "YES24 티켓", u, ("yes24", m.group(2))
    m = re.search(r"ticket\.melon\.com/.*prodId=(\d+)", link)
    if m:
        u = f"https://ticket.melon.com/performance/index.htm?prodId={m.group(1)}"
        return "멜론티켓", u, ("melon", m.group(1))
    if "ticketlink" in link:
        return "티켓링크", link, None
    host = re.sub(r"^https?://(www\.)?", "", link).split("/")[0]
    return host, link, None


def clean(s):
    s = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s)
    s = re.sub(r"(\\+r)?\\+n|\\+r|<br\s*/?>|</p>\s*<p[^>]*>", " / ", s, flags=re.I)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    s = re.sub(r"\s*/\s*(/\s*)+", " / ", re.sub(r"[ \t ]+", " ", s))
    return s.strip(" /")


def read_nol(h, gid):
    h = re.sub(r'\\+"', '"', h)
    if f'"goodsCode":"{gid}"' not in h:
        return None
    rt = re.search(r'"runningTime":"(\d*)"', h)
    im = re.search(r'"interMissionTime":"(\d*)"', h)
    pt = re.search(r'"playTimeInfo":"(.*?)"', h)
    run = int(rt.group(1)) if rt and rt.group(1) else 0
    inter = int(im.group(1)) if im and im.group(1) else 0
    run_text = f"{run}분" + (f"(인터미션 {inter}분)" if inter else "") if run else ""
    return run_text, clean(pt.group(1)) if pt else ""


def read_yes24(h, _):
    """PC(ticket.yes24.com)·모바일(m.ticket.yes24.com) 둘 다: 상세정보 '관람시간: …', '공연시간 (안내)'"""
    meta = re.search(r'<meta name="description" content="([^"]*)"', h)
    pt = re.search(r"<dt>\s*공연시간(?:\s*안내)?\s*</dt>\s*<dd>(.*?)</dd>", h, re.S)
    if not meta or "상세정보" not in meta.group(1) or not pt:
        return None
    rt = re.search(r"관람시간\s*:\s*(.*?)\s+(?:장소|출연|등급)\s*:", html.unescape(meta.group(1)) + " 장소:")
    return (rt.group(1).strip() if rt else ""), clean(pt.group(1))


def read_melon(h, _):
    if "box_consert_info" not in h:
        return None
    rt = re.search(r'<dt class="tit_info">\s*관람시간\s*</dt>\s*<dd class="txt_info">(.*?)</dd>', h, re.S)
    pt = re.search(r'<div class="box_concert_time">(.*?)</div>', h, re.S)
    t = clean(pt.group(1)) if pt else ""
    return (clean(rt.group(1)) if rt else ""), re.sub(r"^공연시간\s*/?\s*", "", t)


READERS = {"nol": read_nol, "yes24": read_yes24, "melon": read_melon}


def fetch_sellers(events):
    run_minutes = _run_minutes
    old = {r["evtSeq"]: r for r in csv.DictReader(open(SELLER, encoding="utf-8-sig"))} if SELLER.exists() else {}
    rows, n_ok, n_fail = {}, 0, 0
    for e in events:
        if (e.get("endDt") or "") < TODAY.isoformat():
            if str(e["evtSeq"]) in old:  # 지난 공연은 지난번 값 보관
                rows[str(e["evtSeq"])] = old[str(e["evtSeq"])]
            continue
        link = e.get("evtLink") or e.get("rsvLink")
        if not link:
            continue
        name, url, kind = seller_of(link)
        key = str(e["evtSeq"])
        row = {"evtSeq": key, "title": e["title"].strip(), "seller": name, "url": url, "ok": "0",
               "run_min": "", "run_text": "", "time_text": "", "checked": ""}
        if kind:
            got = None
            tries = [url] + ([url.replace("://ticket.", "://m.ticket.")] if kind[0] == "yes24" else [])
            for u in tries:  # YES24는 PC 페이지를 못 읽으면 모바일 페이지로
                try:
                    h = get(u)
                    got = READERS[kind[0]](h, kind[1])
                    if got is None:
                        t = re.search(r"<title[^>]*>(.*?)</title>", h, re.S)
                        print(f"! {name} {u} 모양이 달라 못 읽음: 길이 {len(h)}, 제목 {clean(t.group(1))[:40] if t else '-'}")
                except Exception as ex:
                    print(f"! {name} {u} 실패: {type(ex).__name__} {str(ex)[:80]}")
                time.sleep(1)
                if got is not None:
                    break
            if got is not None:
                rt, tt = got
                m = run_minutes(rt)
                row.update(ok="1", run_min=m or "", run_text=rt if m else "", time_text=tt, checked=TODAY.isoformat())
                n_ok += 1
            else:
                n_fail += 1
                if key in old and old[key].get("ok") == "1":
                    row = old[key]  # 못 읽었으면 지난번 값 유지
        rows[key] = row
    with open(SELLER, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SELLER_COLS)
        w.writeheader()
        for k in sorted(rows, key=int):
            w.writerow({c: rows[k].get(c, "") for c in SELLER_COLS})
    print(f"예매처 페이지 {n_ok}개 읽음, {n_fail}개 못 읽음 → {SELLER.name}")


def _run_minutes(text):  # scripts/02의 run_minutes와 같은 규칙
    t = str(text or "")
    m = re.search(r"(\d+)\s*시간(?:\s*(\d+)\s*분)?", t)
    v = int(m.group(1)) * 60 + int(m.group(2) or 0) if m else None
    if v is None:
        m = re.search(r"(\d{2,3})\s*분", t)
        v = int(m.group(1)) if m else None
    return v if v and 30 <= v <= 400 else None


def main():
    import os
    os.chdir(ROOT)
    if "--offline" not in sys.argv:
        events = fetch_park()
        fetch_sellers(events)
    runpy.run_path(str(ROOT / "scripts" / "02_build_events.py"), run_name="__main__")
    runpy.run_path(str(ROOT / "scripts" / "27_official_shows.py"), run_name="__main__")


if __name__ == "__main__":
    main()
