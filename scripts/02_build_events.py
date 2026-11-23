"""올림픽공원 공식 공연 일정(2023~2026)을 '날짜×공연장' 표로 펼치고 시작 시각을 뽑는다.

입력: data/raw/olpark_events_2023_2026.json  (올림픽공원 홈페이지 일정안내 AJAX에서 받은 원본)
      data/raw/olpark_events_live.json       (scripts/28이 매일 새로 받는 같은 일정 — 같은 evtSeq면 이쪽이 우선)
      data/processed/show_seller.csv         (scripts/28이 예매처 페이지에서 읽은 공연 시각·관람시간, 있으면 우선)
출력: data/processed/event_days.csv          (날짜별 공연 1행)
"""
import csv, json, os, re, datetime as dt
import pandas as pd

SRC = "data/raw/olpark_events_2023_2026.json"
LIVE = "data/raw/olpark_events_live.json"
SELLER = "data/processed/show_seller.csv"
OUT = "data/processed/event_days.csv"

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


def parse_times(tm, beginDt, extended=False):
    """시간 문자열 → {날짜문자열 또는 요일번호: [시작시각...]} 또는 {'*': [...]} (모든 날 공통)
    extended=True(매일 받는 일정·예매처 문구)면 '12.24(목)'·'12월 13()'·'오후 5' 같은 표기도 읽는다.
    옛 원본은 지난 분석 결과가 바뀌지 않게 예전 방식(extended=False) 그대로."""
    s = normalize(tm, extended)
    date_mark = DATE_MARK if extended else OLD_MARK
    res = {}
    # 1) 날짜가 적힌 형식: '2024년 11월 15일(금) 20:00 / 11월 16일(토) 19:00'
    year = int(beginDt[:4]); first_month = int(beginDt[5:7])
    marks = list(re.finditer(date_mark, s))
    if marks:
        for i, m in enumerate(marks):
            seg = s[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(s)]
            times = [to_time(t) for t in re.finditer(TIME, seg)]
            times = [t for t in times if "08:00" <= t <= "23:59"]
            if not times:
                continue
            if m.group(4):  # 2026.11.21. 형식
                y, mo, da = int(m.group(4)), int(m.group(5)), int(m.group(6))
            elif m.group(7):  # 12.24(목) · 12.19 SAT 형식(연도 없음)
                mo, da = int(m.group(7)), int(m.group(8))
                y = year + 1 if mo < first_month else year
            else:
                mo, da = int(m.group(2)), int(m.group(3))
                y = int(m.group(1)) if m.group(1) else (year + 1 if mo < first_month else year)
            try:
                key = dt.date(y, mo, da).isoformat()
            except ValueError:
                continue
            res.setdefault(key, []).extend(times)
        # 날짜마다 시각이 붙어 있을 때만 날짜 방식으로 인정
        # ('12월 20일 ~ 12월 22일  금 20:00 / 토 18:00' 처럼 기간 뒤에 요일별 시각이 오는 경우는 요일 방식)
        if res and (len(res) >= 2 or len(marks) == 1):
            return res
        res = {}
        s = re.sub(r"(?:(?:" + date_mark + r")\s*(\([A-Za-z월화수목금토일]*\))?)" if extended else
                   r"(?:\d{4}\s*년\s*)?\d{1,2}\s*월\s*\d{1,2}\s*일\s*(\([월화수목금토일]\))?|\d{4}\.\d{1,2}\.\d{1,2}\.?\s*(\([A-Za-z월화수목금토일]+\))?", " ", s)
    # 요일 표기: (금) 19:00 / 토 18시 ...
    parts = re.split(r"/|,(?=\s*\(?[월화수목금토일])", s)
    found_wd = False
    for part in parts:
        wds = re.findall(r"\(?([월화수목금토일])\)?(?=[\s\d(,·~]|$)", part)
        times = [to_time(m) for m in re.finditer(TIME, part)]
        times = [t for t in times if "08:00" <= t <= "23:59"]
        if wds and times:
            found_wd = True
            for w in wds:
                res.setdefault(WD[w], []).extend(times)
    if not found_wd:
        times = [to_time(m) for m in re.finditer(TIME, s)]
        times = [t for t in times if "08:00" <= t <= "23:59"]
        if times:
            res["*"] = times
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
    b = dt.date.fromisoformat(e["beginDt"]); en = dt.date.fromisoformat(e["endDt"])
    span = (en - b).days + 1
    sel = SELLERS.get(int(e["evtSeq"]))
    live = "ndTm" in e  # 매일 받는 일정에서 온 공연
    times, time_src = {}, "park"
    if sel and sel.get("ok") == "1" and sel.get("time_text"):
        times, time_src = parse_times(sel["time_text"], e["beginDt"], True), "seller"
    if not times:  # 예매처 시각을 못 읽었으면 공식 일정 문구로
        times, time_src = parse_times(e["tm"], e["beginDt"], live), "park"
    run = run_info(e, sel)
    long_run = span > 7  # 몇 주씩 이어지는 뮤지컬·어린이 공연
    for v in venue(e["plc"]):
        d = b
        dated = any(isinstance(k, str) and k != "*" for k in times)
        while d <= en:
            wd = d.weekday()
            if dated:  # 날짜별 시각이 적혀 있으면 적힌 날짜만 공연일로 본다
                t = times.get(d.isoformat())
                if not t:
                    d += dt.timedelta(days=1); continue
            else:
                t = times.get(wd) or times.get("*")
            if not dated and long_run and wd not in times and "*" not in times:
                d += dt.timedelta(days=1); continue  # 요일 지정이 있는데 그 요일이 아니면 공연 없음
            if not dated and not long_run and times and "*" not in times and wd not in times and span > 3:
                d += dt.timedelta(days=1); continue  # 예: IU 3/2~3/10 은 토·일만
            rows.append({
                "날짜": d.isoformat(), "요일": "월화수목금토일"[wd], "공연장": v,
                "좌석규모_참고": CAPACITY.get(v), "공연명": e["title"].strip(), "evtSeq": e["evtSeq"],
                "시작시각들": ";".join(sorted(set(t))) if t else "",
                "마지막회차시작": max(t) if t else "",
                "장기공연": long_run, "시간원문": (e["tm"] or "").strip(),
                "시각출처": time_src if t else "",
                "관람시간분": run[0], "관람시간원문": run[1], "관람시간출처": run[2],
                "예매처": run[3], "예매링크": run[4], "확인일": run[5],
            })
            d += dt.timedelta(days=1)

df = pd.DataFrame(rows).sort_values(["날짜", "공연장"])
df.to_csv(OUT, index=False, encoding="utf-8-sig")
print("행", len(df), "기간", df["날짜"].min(), "~", df["날짜"].max())
print("시작시각 못 뽑은 행", (df["시작시각들"] == "").sum())
print(df[df["날짜"].between("2024-07-01", "2024-07-31") & ~df["장기공연"]].to_string(index=False, columns=["날짜", "요일", "공연장", "공연명", "시작시각들"]))
