"""올림픽공원 공식 공연 일정(2023~2026)을 '날짜×공연장' 표로 펼치고 시작 시각을 뽑는다.

입력: data/raw/olpark_events_2023_2026.json  (올림픽공원 홈페이지 일정안내 AJAX에서 받은 원본)
출력: data/processed/event_days.csv          (날짜별 공연 1행)
"""
import json, re, datetime as dt
import pandas as pd

SRC = "data/raw/olpark_events_2023_2026.json"
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


def normalize(tm):
    """'오후 7시 30분', '7PM', '07:00:00PM' 같은 표기를 'HH:MM'으로 바꾼다."""
    s = tm or ""
    pm = lambda h: h + 12 if h < 12 else h
    s = re.sub(r"(\d{1,2}):(\d{2}):\d{2}\s*PM", lambda m: f"{pm(int(m.group(1))):02d}:{m.group(2)}", s, flags=re.I)
    s = re.sub(r"오후\s*(\d{1,2})\s*시\s*(\d{1,2})\s*분", lambda m: f"{pm(int(m.group(1))):02d}:{int(m.group(2)):02d}", s)
    s = re.sub(r"오후\s*(\d{1,2})\s*시(?:\s*반)?", lambda m: f"{pm(int(m.group(1))):02d}:{'30' if '반' in m.group(0) else '00'}", s)
    s = re.sub(r"오후\s*(\d{1,2}):(\d{2})", lambda m: f"{pm(int(m.group(1))):02d}:{m.group(2)}", s)
    s = re.sub(r"(\d{1,2})\s*:\s*(\d{2})\s*PM", lambda m: f"{pm(int(m.group(1))):02d}:{m.group(2)}", s, flags=re.I)
    s = re.sub(r"(\d{1,2})\s*PM", lambda m: f"{pm(int(m.group(1))):02d}:00", s, flags=re.I)
    return s


def parse_times(tm, beginDt):
    """시간 문자열 → {날짜문자열 또는 요일번호: [시작시각...]} 또는 {'*': [...]} (모든 날 공통)"""
    s = normalize(tm)
    res = {}
    # 1) 날짜가 적힌 형식: '2024년 11월 15일(금) 20:00 / 11월 16일(토) 19:00'
    year = int(beginDt[:4]); first_month = int(beginDt[5:7])
    marks = list(re.finditer(r"(?:(\d{4})\s*년\s*)?(\d{1,2})\s*월\s*(\d{1,2})\s*일|(\d{4})\.(\d{1,2})\.(\d{1,2})\.?", s))
    if marks:
        for i, m in enumerate(marks):
            seg = s[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(s)]
            times = [to_time(t) for t in re.finditer(TIME, seg)]
            times = [t for t in times if "08:00" <= t <= "23:59"]
            if not times:
                continue
            if m.group(4):  # 2026.11.21. 형식
                y, mo, da = int(m.group(4)), int(m.group(5)), int(m.group(6))
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
        s = re.sub(r"(?:\d{4}\s*년\s*)?\d{1,2}\s*월\s*\d{1,2}\s*일\s*(\([월화수목금토일]\))?|\d{4}\.\d{1,2}\.\d{1,2}\.?\s*(\([A-Za-z월화수목금토일]+\))?", " ", s)
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


rows = []
for e in json.load(open(SRC, encoding="utf-8")):
    b = dt.date.fromisoformat(e["beginDt"]); en = dt.date.fromisoformat(e["endDt"])
    span = (en - b).days + 1
    times = parse_times(e["tm"], e["beginDt"])
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
            })
            d += dt.timedelta(days=1)

df = pd.DataFrame(rows).sort_values(["날짜", "공연장"])
df.to_csv(OUT, index=False, encoding="utf-8-sig")
print("행", len(df), "기간", df["날짜"].min(), "~", df["날짜"].max())
print("시작시각 못 뽑은 행", (df["시작시각들"] == "").sum())
print(df[df["날짜"].between("2024-07-01", "2024-07-31") & ~df["장기공연"]].to_string(index=False, columns=["날짜", "요일", "공연장", "공연명", "시작시각들"]))
