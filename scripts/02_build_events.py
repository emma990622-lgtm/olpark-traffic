"""올림픽공원 공식 공연 일정(2023~2026)을 '날짜×공연장' 표로 펼치고 시작 시각을 뽑는다.

입력: data/raw/olpark_events_2023_2026.json  (올림픽공원 홈페이지 일정안내 AJAX에서 받은 원본)
      data/raw/olpark_events_live.json       (scripts/28이 매일 새로 받는 같은 일정 — 같은 evtSeq면 이쪽이 우선)
      data/processed/show_seller.csv         (scripts/28이 예매처 페이지에서 읽은 공연 시각·관람시간, 있으면 우선)
출력: data/processed/event_days.csv          (날짜별 공연 1행)
"""
import csv, json, os, re, datetime as dt

SRC = "data/raw/olpark_events_2023_2026.json"
LIVE = "data/raw/olpark_events_live.json"
SELLER = "data/processed/show_seller.csv"
HOLIDAYS_CSV = "data/processed/holidays_kr.csv"
OUT = "data/processed/event_days.csv"

# 사전 취소·휴연이 공식 확인된 공연/날짜 제외
# - evtSeq 4910: 로드 투 킹덤 : ACE OF ACE 콘서트 (2025-01-04~05, 2024-12-02 전 회차 취소 공지)
# - (4841, 2024-10-14): 2024 오페라 투란도트 월요일 휴연('14일 공연 없음', 공원 페이지 '월~금' 오표기)
CANCELLED_EVT_SEQS = {4910}
NO_SHOW_SEQ_DATES = {(4841, "2024-10-14")}

# 공연장 이름 통일 (홈페이지 표기가 제각각)
def venue(plc):
    p = plc.replace(" ", "")
    hits = []
    if "KSPO" in p.upper() or "체조" in p: hits.append("KSPO DOME")
    if "핸드볼" in p or "티켓링크" in p: hits.append("핸드볼경기장")
    if "올림픽홀" in p: hits.append("올림픽홀")
    if "우리금융" in p or "역도" in p: hits.append("우리금융아트홀")
    if "88잔디" in p or "잔디마당" in p: hits.append("88잔디마당")
    if "수변무대" in p: hits.append("88호수수변무대")
    if "뮤즈라이브" in p: hits.append("뮤즈라이브")
    if "K-아트홀" in p or "K아트홀" in p: hits.append("K-아트홀")
    return hits or ["기타"]

# 좌석 규모(참고값). KSPO DOME 15,000석은 운영사 공식 표기, 나머지는 KOPIS 공연시설 상세로 재확인 필요
CAPACITY = {"KSPO DOME": 15000, "핸드볼경기장": 5000, "올림픽홀": 3000, "우리금융아트홀": 1200,
            "88잔디마당": None, "88호수수변무대": None, "뮤즈라이브": 300, "K-아트홀": None, "기타": None}

# 날짜 표기: '2026년 12월 13일', '12월 13()'(일 빠짐), '2026.12.18.', '12.24(목)', '12.19 SAT'
DATE_MARK = (r"(?:(\d{4})\s*년\s*)?(\d{1,2})\s*월\s*(\d{1,2})\s*(?:일|(?=\s*\())"
             r"|(\d{4})\.(\d{1,2})\.(\d{1,2})\.?"
             r"|(?<![\d.:])(\d{1,2})\.(\d{1,2})(?=\.?\s*(?:\(|[A-Za-z]{3}\b|[월화수목금토일]))")
OLD_MARK = r"(?:(\d{4})\s*년\s*)?(\d{1,2})\s*월\s*(\d{1,2})\s*일|(\d{4})\.(\d{1,2})\.(\d{1,2})\.?|(?!)(\d)(\d)"  # 예전 방식(7·8번 칸은 자리만)
WD = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}
TIME = r"(\d{1,2})\s*(?::|;|시)\s*(\d{2})?|(\d{1,2})\s*(PM|AM|pm|am)"


def load_holidays():
    if not os.path.exists(HOLIDAYS_CSV):
        return set()
    with open(HOLIDAYS_CSV, encoding="utf-8-sig") as f:
        r = csv.reader(f)
        next(r, None)
        return {row[0].strip() for row in r if row and row[0].strip()}


HOLIDAY_DATES = load_holidays()


def to_time(m):
    """정규식 매치 → 'HH:MM'"""
    if m.group(1):
        h = int(m.group(1)); mi = int(m.group(2) or 0)
        if 1 <= h <= 9:  # '오후 3시, 7시 30분'의 '7시'처럼 오후가 생략된 경우 (오전 1~9시 공연은 없음)
            h += 12
    else:
        h = int(m.group(3)); mi = 0
        if m.group(4).lower() == "pm" and h < 12: h += 12
    return f"{h:02d}:{mi:02d}"


def normalize(tm, extended=False):
    """'오후 7시 30분', '7PM', '07:00:00PM' 같은 표기를 'HH:MM'으로 바꾼다."""
    s = tm or ""
    pm = lambda h: h + 12 if h < 12 else h
    s = re.sub(r"(\d{1,2}):(\d{2}):\d{2}\s*PM", lambda m: f"{pm(int(m.group(1))):02d}:{m.group(2)}", s, flags=re.I)
    s = re.sub(r"오후\s*(\d{1,2})\s*시\s*(\d{1,2})\s*분", lambda m: f"{pm(int(m.group(1))):02d}:{int(m.group(2)):02d}", s)
    s = re.sub(r"오후\s*(\d{1,2})\s*시(?:\s*반)?", lambda m: f"{pm(int(m.group(1))):02d}:{'30' if '반' in m.group(0) else '00'}", s)
    s = re.sub(r"오후\s*(\d{1,2}):(\d{2})", lambda m: f"{pm(int(m.group(1))):02d}:{m.group(2)}", s)
    if extended:
        s = re.sub(r"오후\s*(\d{1,2})(?![\d:시])", lambda m: f"{pm(int(m.group(1))):02d}:00", s)  # '오후 5'(시 빠짐)
    s = re.sub(r"(\d{1,2})\s*:\s*(\d{2})\s*PM", lambda m: f"{pm(int(m.group(1))):02d}:{m.group(2)}", s, flags=re.I)
    s = re.sub(r"(\d{1,2})\s*PM", lambda m: f"{pm(int(m.group(1))):02d}:00", s, flags=re.I)
    return s


def _mark_to_iso(m, year, first_month):
    if m.group(4):  # 2026.11.21. 형식
        y, mo, da = int(m.group(4)), int(m.group(5)), int(m.group(6))
    elif m.group(7):  # 12.24(목) · 12.19 SAT 형식(연도 없음)
        mo, da = int(m.group(7)), int(m.group(8))
        y = year + 1 if mo < first_month else year
    else:
        mo, da = int(m.group(2)), int(m.group(3))
        y = int(m.group(1)) if m.group(1) else (year + 1 if mo < first_month else year)
    try:
        return dt.date(y, mo, da).isoformat()
    except ValueError:
        return None


def parse_times(tm, beginDt, extended=False):
    """시간 문자열 → {날짜문자열 또는 요일번호 또는 'HOL': [시작시각...]} 또는 {'*': [...]} (모든 날 공통)
    extended=True(매일 받는 일정·예매처 문구)면 '12.24(목)'·'12월 13()'·'오후 5'·'수목금'·'주말 및 공휴일'·요일+특정일 혼합도 읽는다.
    옛 원본은 지난 분석 결과가 바뀌지 않게 예전 방식(extended=False) 그대로."""
    s = normalize(tm, extended)
    year = int(beginDt[:4]); first_month = int(beginDt[5:7])
    off_dates = set()
    if extended:
        # '2월 10일 공연없음' 같은 특정일 휴연을 먼저 따로 기록하고 지운다
        def _pop_off(m):
            mo, da = int(m.group(2)), int(m.group(3))
            y = int(m.group(1)) if m.group(1) else (year + 1 if mo < first_month else year)
            try:
                off_dates.add(dt.date(y, mo, da).isoformat())
            except ValueError:
                pass
            return " "
        s = re.sub(r"(?:(\d{4})\s*년\s*)?(\d{1,2})\s*월\s*(\d{1,2})\s*일(?:\s*\([월화수목금토일]\))?\s*(?:공연\s*)?(?:없음|휴관|휴연)", _pop_off, s)
        # '(월 공연없음)', '월요일 공연 없음'의 요일은 공연일이 아님
        s = re.sub(r"\(?\s*[월화수목금토일](?:요일)?\s*(?:공연\s*)?(?:없음|휴관|휴연)\s*\)?", " ", s)
    date_mark = DATE_MARK if extended else OLD_MARK
    res = {}
    # 1) 날짜가 적힌 형식: '2024년 11월 15일(금) 20:00 / 11월 16일(토) 19:00'
    marks = list(re.finditer(date_mark, s))
    if marks:
        date_spans = []
        for i, m in enumerate(marks):
            seg_end = marks[i + 1].start() if i + 1 < len(marks) else len(s)
            seg = s[m.end(): seg_end]
            # extended=True에서 '/' 뒤에 일반 요일 규칙이 이어지면 그 앞까지만 해당 날짜 시각으로 본다
            if extended and "/" in seg:
                seg_first = seg.split("/", 1)[0]
                seg = seg_first
                seg_end = m.end() + len(seg_first)
            times = [to_time(t) for t in re.finditer(TIME, seg)]
            times = [t for t in times if "08:00" <= t <= "23:59"]
            if not times:
                continue
            key = _mark_to_iso(m, year, first_month)
            if not key:
                continue
            res.setdefault(key, []).extend(times)
            date_spans.append((m.start(), seg_end))
        if not extended:
            # 날짜마다 시각이 붙어 있을 때만 날짜 방식으로 인정
            # ('12월 20일 ~ 12월 22일  금 20:00 / 토 18:00' 처럼 기간 뒤에 요일별 시각이 오는 경우는 요일 방식)
            if res and (len(res) >= 2 or len(marks) == 1):
                return res
            res = {}
            s = re.sub(r"(?:\d{4}\s*년\s*)?\d{1,2}\s*월\s*\d{1,2}\s*일\s*(\([월화수목금토일]\))?|\d{4}\.\d{1,2}\.\d{1,2}\.?\s*(\([A-Za-z월화수목금토일]+\))?", " ", s)
        else:
            # extended=True: 날짜별 시각 조각을 지운 뒤에도 요일별 기본 규칙('화,수,목,금,일 ...')이 남아 있으면 함께 살린다
            if res and (len(res) >= 2 or len(marks) == 1):
                chars = list(s)
                for a, b in date_spans:
                    for idx in range(a, b):
                        chars[idx] = " "
                rem = "".join(chars)
                rem = re.sub(r"(?:" + date_mark + r")\s*(\([A-Za-z월화수목금토일]*\))?", " ", rem)
                s = rem
            else:
                res = {}
                s = re.sub(r"(?:(?:" + date_mark + r")\s*(\([A-Za-z월화수목금토일]*\))?)", " ", s)
    # 요일 표기: (금) 19:00 / 토 18시 / 수목금 19시 30분 / 주말 및 공휴일 14시 ...
    if extended:
        # 문의 전화번호('문의 : 010 ...') 등 안내 문구 뒤쪽 숫자가 시각으로 오인되지 않게 자른다
        s = re.split(r"\*(?:단체|휠체어|문의)|문의\s*:", s)[0]
        s = re.sub(r"([월화수목금토일])요일", r"\1", s)
        s = s.replace("공휴일", " __HOL__ ")
        s = s.replace("주말", " 토, 일 ")
        s = re.sub(r"(?<![가-힣])([월화수목금토일]{2,})(?=[\s\d(,·~)]|$)", lambda m: ",".join(m.group(1)), s)
    parts = re.split(r"/|,(?=\s*(?:\(?[월화수목금토일]|__HOL__))", s)
    found_wd = False
    carry = []  # '토, 일 오후 5시'처럼 쉼표로 나뉜 요일은 다음 조각의 시각을 같이 쓴다(매일 받는 일정만)
    for part in parts:
        wds = re.findall(r"\(?([월화수목금토일])\)?(?=[\s\d(,·~]|$)", part)
        has_hol = extended and ("__HOL__" in part)
        tokens = [WD[w] for w in wds] + (["HOL"] if has_hol else [])
        times = [to_time(m) for m in re.finditer(TIME, part)]
        times = [t for t in times if "08:00" <= t <= "23:59"]
        if extended:
            if tokens and not times:
                carry += tokens
                continue
            tokens, carry = carry + tokens, []
        if tokens and times:
            found_wd = True
            for tok in tokens:
                res.setdefault(tok, []).extend(times)
    if not found_wd and not res:
        times = [to_time(m) for m in re.finditer(TIME, s)]
        times = [t for t in times if "08:00" <= t <= "23:59"]
        if times:
            res["*"] = times
    for od in off_dates:
        res[od] = []
    return res


def run_minutes(text):
    """'총 120분', '약 120분 (인터미션 20분)', '2시간 30분' → 분. 못 읽거나 '-'면 None"""
    t = str(text or "")
    m = re.search(r"(\d+)\s*시간(?:\s*(\d+)\s*분)?", t)
    v = int(m.group(1)) * 60 + int(m.group(2) or 0) if m else None
    if v is None:
        m = re.search(r"(\d{2,3})\s*분", t)
        v = int(m.group(1)) if m else None
    return v if v and 30 <= v <= 400 else None


def load_events():
    """기존 원본 + 매일 받는 일정(같은 evtSeq면 새것). 매일 받는 쪽에만 관람시간(ndTm)·예매처 링크가 있다."""
    ev = {e["evtSeq"]: e for e in json.load(open(SRC, encoding="utf-8"))}
    if os.path.exists(LIVE):
        for e in json.load(open(LIVE, encoding="utf-8")):
            ev[e["evtSeq"]] = e
    return list(ev.values())


def load_seller():
    if not os.path.exists(SELLER):
        return {}
    return {int(r["evtSeq"]): r for r in csv.DictReader(open(SELLER, encoding="utf-8-sig"))}


def run_info(e, sel):
    """관람시간: 예매처 페이지 > 올림픽공원 공식 일정. (분, 원문, 출처, 예매처, 링크, 확인일)"""
    ok = sel and sel.get("ok") == "1"
    seller, url = (sel or {}).get("seller", ""), (sel or {}).get("url", "")
    if ok and sel.get("run_min"):
        return int(sel["run_min"]), sel["run_text"], "seller", seller, url, sel["checked"]
    if "ndTm" not in e:  # 옛 원본에만 있는 공연(관람시간 칸이 없음)
        return None, "", "", seller, url, ""
    park = (e.get("ndTm") or "").strip()
    if run_minutes(park):
        return run_minutes(park), park, "park", seller, url, e.get("_fetched", "")
    if ok:  # 예매처 페이지를 읽었는데 관람시간이 비어 있음
        return None, "", "seller", seller, url, sel["checked"]
    return None, "", "park", seller, url, e.get("_fetched", "")


SELLERS = load_seller()
rows = []
for e in load_events():
    seq = int(e["evtSeq"])
    if seq in CANCELLED_EVT_SEQS:
        continue
    b = dt.date.fromisoformat(e["beginDt"]); en = dt.date.fromisoformat(e["endDt"])
    span = (en - b).days + 1
    sel = SELLERS.get(seq)
    live = "ndTm" in e  # 매일 받는 일정에서 온 공연
    times, time_src = {}, "park"
    if sel and sel.get("ok") == "1" and sel.get("time_text"):
        times, time_src = parse_times(sel["time_text"], e["beginDt"], True), "seller"
    if not times:  # 예매처 시각을 못 읽었으면 공식 일정 문구로
        times, time_src = parse_times(e["tm"], e["beginDt"], live), "park"
    run = run_info(e, sel)
    long_run = span > 7  # 몇 주씩 이어지는 뮤지컬·어린이 공연
    has_wd = any(isinstance(k, int) or k in ("*", "HOL") for k in times)
    dated_only = any(isinstance(k, str) and k not in ("*", "HOL") for k in times) and not has_wd
    for v in venue(e["plc"]):
        d = b
        while d <= en:
            iso = d.isoformat()
            if (seq, iso) in NO_SHOW_SEQ_DATES:
                d += dt.timedelta(days=1); continue
            wd = d.weekday()
            if iso in times:  # 특정일 지정(또는 특정일 공연없음=[])이 있으면 그 규칙이 우선
                t = times[iso]
                if not t:
                    d += dt.timedelta(days=1); continue
            elif dated_only:  # 날짜별 시각만 적혀 있으면 적힌 날짜만 공연일로 본다
                d += dt.timedelta(days=1); continue
            else:
                t = times.get(wd) or (times.get("HOL") if iso in HOLIDAY_DATES else None) or times.get("*")
                if not t and long_run:
                    d += dt.timedelta(days=1); continue  # 장기공연에 해당 요일 시각이 없으면 공연 없음
                if not t and not long_run and times and span > 3:
                    d += dt.timedelta(days=1); continue  # 예: IU 3/2~3/10 은 토·일만
            cap = CAPACITY.get(v)
            rows.append({
                "날짜": iso, "요일": "월화수목금토일"[wd], "공연장": v,
                "좌석규모_참고": "" if cap is None else f"{float(cap):.1f}",
                "공연명": e["title"].strip(), "evtSeq": seq,
                "시작시각들": ";".join(sorted(set(t))) if t else "",
                "마지막회차시작": max(t) if t else "",
                "장기공연": long_run, "시간원문": (e["tm"] or "").strip(),
                "시각출처": time_src if t else "",
                "관람시간분": "" if run[0] is None else f"{float(run[0]):.1f}",
                "관람시간원문": run[1], "관람시간출처": run[2],
                "예매처": run[3], "예매링크": run[4], "확인일": run[5],
            })
            d += dt.timedelta(days=1)

# 날짜·공연장 순 정렬(기존 pandas 출력과 줄바꿈·소수점 서식 일치)
rows.sort(key=lambda r: (r["날짜"], r["공연장"]))
FIELDS = ["날짜", "요일", "공연장", "좌석규모_참고", "공연명", "evtSeq", "시작시각들", "마지막회차시작",
          "장기공연", "시간원문", "시각출처", "관람시간분", "관람시간원문", "관람시간출처", "예매처", "예매링크", "확인일"]
with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
dates = [r["날짜"] for r in rows]
print("행", len(rows), "기간", min(dates), "~", max(dates))
print("시작시각 못 뽑은 행", sum(1 for r in rows if r["시작시각들"] == ""))
