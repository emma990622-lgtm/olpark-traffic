"""
입출차 원본을 읽는 공통 함수 (scripts/11, 15 등이 같이 쓴다).

  load_2024()  data/raw/parking_inout_202407.csv  2024년 7월 전체(빠짐없는 기록), 가중치 w = 1
  load_2025()  data/raw/kcisa_inout_2025.jsonl     2025년, 다운로드 중이면 받은 만큼. 가중치 w = 1 / (그 달을 받은 비율)

2025 자료의 '받은 비율' 추정
  - 기록 번호(LOCAL_ID, 예: B050-1872898)는 같은 달 기록끼리 이어진 번호 덩어리다(7월 마지막 번호 + 1 = 8월 첫 번호).
    한 달이 덩어리 여러 개일 수 있다.
  - 덩어리 안에서는 그 달 여러 날 기록이 고르게 섞여 있다(하루 기록의 번호가 덩어리 전체에 퍼져 있음).
  - 그래서 덩어리마다 받은 줄 수 ÷ 번호 폭 = 받은 비율, 가중치 = 1 ÷ 비율.
  - 덩어리들의 번호 폭을 모두 더한 값이 전체 줄 수(TOTAL_2025)와 거의 같으면 아예 못 받은 덩어리가 없다는 뜻이다
    → 그때만 2025 대수를 쓴다(enough_2025). 2026-11-20 주인 PC 자료: 번호 폭 합 2,410,970 / 2,411,225 = 99.99%.
  - 다운로드한 줄에는 똑같은 줄이 겹쳐 들어온 것이 많다(2,128,000줄 중 269,324줄). 번호(LOCAL_ID)로 하나만 남긴다.

2025 원본의 두 가지 함정 (scripts/17_check_2025.py 로 확인, docs/context.md 데이터 함정)
  1) 한 달이 65,535줄(옛 엑셀 한 장 한도)로 잘린 달이 있다: 2025년 8·9·11·12월. 보통 달은 19만~30만 줄.
     - 8·9월: 그 달 모든 날의 일부(약 4분의 1)만 남아 있다 → 대수는 못 쓴다(w = NaN). 시간·비율은 쓸 수 있다.
     - 11·12월: 기록이 시간순이라 그 달 앞쪽 며칠만 남아 있다 → 남은 날은 대수를 쓸 수 있고, 그 뒤 날은 기록이 없다.
  2) 10~12월 덩어리는 기록이 입차 시각 순서대로 번호가 붙어 있다(1~9월은 그 달 여러 날이 고르게 섞여 있음).
     → 못 받은 1,000줄 묶음 = 특정 시간대가 통째로 빔. 달 단위 보정이 틀리므로 공연마다 그 시간대를 받은 비율을 따로 잰다
       (ordered_ok / show_weights). 90% 넘게 받은 공연만 대수에 쓴다.
"""
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
EVENTS = ROOT / "data" / "processed" / "event_days.csv"
PAT = re.compile(r"입구:([^,]*), 입차시간:([^,]*), 출구:([^,]*), 출차시간:(.*)$")
TOTAL_2025 = 2411225                       # API_CPM_008 전체 줄 수(문화공공데이터광장 totalCount)
COLS = ["in_time", "out_time", "gate", "igate", "src", "w", "ord"]
MAIN_GATES = ("동2문", "남2문", "북2문")          # 2024년 7월 자료·2,120면 기준 구역(공공데이터포털 실시간 주차현황 설명)
# 공휴일(일요일처럼 본다) 2024-06 ~ 2025-12 (scripts/15, 18이 씀)
HOLIDAYS = set("""2024-06-06 2024-08-15 2024-09-16 2024-09-17 2024-09-18 2024-10-01 2024-10-03 2024-10-09 2024-12-25
2025-01-01 2025-01-27 2025-01-28 2025-01-29 2025-01-30 2025-03-03 2025-05-05 2025-05-06 2025-06-03 2025-06-06
2025-08-15 2025-10-03 2025-10-06 2025-10-07 2025-10-08 2025-10-09 2025-12-25""".split())
CAP_SPAN = 70000                           # 번호 폭이 이보다 작은 달 = 65,535줄로 잘린 달
_ORD = {"N": None, "T": None}              # 시간순 덩어리 기록의 (번호, 입차 시각) — load_2025가 채운다


def load_2024():
    p = RAW / "parking_inout_202407.csv"
    if not p.exists():
        return pd.DataFrame(columns=COLS)
    o = pd.read_csv(p, encoding="cp949")
    o.columns = ["date", "in_time", "out_time"]
    o["in_time"] = pd.to_datetime(o.in_time, errors="coerce")
    o["out_time"] = pd.to_datetime(o.out_time, errors="coerce")
    o["gate"] = None
    o["igate"] = None
    o["src"] = "2024"
    o["w"] = 1.0
    o["ord"] = False
    return o.dropna(subset=["in_time", "out_time"])[COLS]


def block_coverage(nums, months, min_run=200, with_blocks=False):
    """기록 번호를 정렬해 '같은 달이 이어지는 번호 덩어리'로 나누고, 덩어리마다 받은 비율(받은 줄 ÷ 번호 폭)을 구한다.
    한 달이 여러 덩어리일 수 있다(다른 주차 시스템 기록이 따로 번호를 받은 것으로 보임).
    돌려주는 값: (줄마다 받은 비율 배열, 달별 요약 {'202503': {'got', 'span', 'ratio'}})
    with_blocks=True 이면 (…, 줄마다 덩어리 번호 배열)도 함께 돌려준다."""
    order = np.argsort(nums)
    n_sorted, m_sorted = nums[order], months[order]
    ratio_sorted = np.full(len(nums), np.nan)
    runs, i = [], 0
    while i < len(n_sorted):
        j = i
        while j + 1 < len(n_sorted) and m_sorted[j + 1] == m_sorted[i]:
            j += 1
        runs.append([i, j])
        i = j + 1
    # 다른 달 번호 몇 줄이 끼어 덩어리가 잘게 쪼개지면(늦게 등록된 기록 등) 작은 덩어리는 앞 덩어리에 붙인다
    merged = []
    for r in runs:
        if merged and r[1] - r[0] + 1 < min_run:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    summary = {}
    blk_sorted = np.zeros(len(nums), dtype=np.int64)
    for b, (i, j) in enumerate(merged):
        blk_sorted[i:j + 1] = b
        span = int(n_sorted[j] - n_sorted[i] + 1)
        got = j - i + 1
        ratio_sorted[i:j + 1] = min(1.0, got / span)
        m = pd.Series(m_sorted[i:j + 1]).mode()[0]
        v = summary.setdefault(m, {"got": 0, "span": 0, "blocks": 0})
        v["got"] += got
        v["span"] += span
        v["blocks"] += 1
    for v in summary.values():
        v["ratio"] = round(min(1.0, v["got"] / v["span"]), 4)
    ratio = np.empty(len(nums))
    ratio[order] = ratio_sorted
    if with_blocks:
        blk = np.empty(len(nums), dtype=np.int64)
        blk[order] = blk_sorted
        return ratio, dict(sorted(summary.items())), blk
    return ratio, dict(sorted(summary.items()))


def load_2025(min_ratio=0.2):
    """2025 입출차. 돌려주는 값: (표[in_time, out_time, gate(출구), igate(입구), src, w, ord], 달별 요약)
    w  = 대수 가중치(1 ÷ 받은 비율). NaN = 대수에 못 씀(받은 비율 min_ratio 미만, 65,535줄로 잘려 일부만 남은 달,
         시간순 덩어리 — 시간순 덩어리는 공연마다 show_weights로 채운다)
    ord = 시간순 덩어리(10~12월) 기록인가"""
    p = RAW / "kcisa_inout_2025.jsonl"
    if not p.exists():
        return pd.DataFrame(columns=COLS), {}
    rows, seen = [], set()
    with open(p, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue                           # 받는 중이라 마지막 줄이 잘렸을 수 있다
            lid = d.get("LOCAL_ID") or ""
            if lid in seen:
                continue                           # 똑같은 줄이 겹쳐 받아진 것
            seen.add(lid)
            m = PAT.search(d.get("DESCRIPTION") or "")
            if not m:
                continue
            try:
                num = int(lid.split("-")[1])
            except (IndexError, ValueError):
                num = None
            rows.append([x.strip() for x in m.groups()] + [num, (d.get("TITLE") or "")[:6]])
    df = pd.DataFrame(rows, columns=["in_gate", "in_time", "out_gate", "out_time", "num", "month"])
    df = df[df.num.notna()].reset_index(drop=True)
    df["num"] = df.num.astype(np.int64)
    ratio, cov, blk = block_coverage(df.num.values, df.month.values, with_blocks=True)
    df["in_time"] = pd.to_datetime(df.in_time, errors="coerce")
    df["out_time"] = pd.to_datetime(df.out_time, errors="coerce")
    df["gate"] = df.out_gate.str.extract(r"^(\S+?문)")[0]
    df["igate"] = df.in_gate.str.extract(r"^(\S+?문)")[0]
    df["src"] = "2025"
    df["blk"] = blk
    df["ratio"] = ratio
    df = df.dropna(subset=["in_time", "out_time"]).sort_values("num").reset_index(drop=True)
    # 덩어리마다: 번호 순서대로 입차 시각이 거의 늘 늘어나면 '시간순', 번호 폭이 작으면 '잘린 달'
    df["ord"] = False
    df["capped"] = False
    for b, g in df.groupby("blk"):
        steps = np.diff(g.in_time.values.astype("datetime64[s]").astype(np.int64))
        ordered = len(steps) > 100 and float((steps < 0).mean()) < 0.01
        span = int(g.num.iloc[-1] - g.num.iloc[0] + 1)
        df.loc[g.index, "ord"] = ordered
        df.loc[g.index, "capped"] = span <= CAP_SPAN
        m = g.month.mode()[0]
        if m in cov:
            cov[m]["layout"] = "시간순" if ordered else "섞임"
            cov[m]["capped"] = bool(span <= CAP_SPAN)
    use = (~df["ord"]) & (~df["capped"]) & (df.ratio >= min_ratio)
    df["w"] = np.where(use, 1.0 / df.ratio, np.nan)
    o = df[df["ord"]]
    _ORD["N"] = o.num.values.astype(np.float64)
    _ORD["T"] = np.maximum.accumulate(o.in_time.values.astype("datetime64[s]").astype(np.int64)).astype(np.float64)
    return df[COLS], cov


def ordered_ok(x, s, before=180, after=20, need=0.9):
    """x(그 공연 계산에 쓸 기록) 중 시간순 덩어리 기록이 있으면, 공연 시작 s 기준 [before분 전, after분 뒤] 입차 기록을
    얼마나 받았는지 잰다(번호가 입차 시각 순서라 그 시간대 번호 폭 = 있어야 할 줄 수). 같은 날 자정까지만 본다.
    돌려주는 값: (믿을 수 있나, 받은 비율 또는 None)"""
    if "ord" not in x or not x["ord"].fillna(False).astype(bool).any() or _ORD["N"] is None or len(_ORD["N"]) == 0:
        return True, None
    N, T = _ORD["N"], _ORD["T"]
    t0 = s - pd.Timedelta(minutes=before)
    t1 = min(s + pd.Timedelta(minutes=after), s.normalize() + pd.Timedelta(hours=23, minutes=59, seconds=59))
    a, b = float(t0.value // 10**9), float(t1.value // 10**9)
    got = int(np.searchsorted(T, b, "right") - np.searchsorted(T, a, "left"))
    expect = float(np.interp(b, T, N) - np.interp(a, T, N)) + 1
    if got == 0 or expect < 50:
        return False, 0.0
    c = min(1.0, got / expect)
    return c >= need, round(c, 3)


def show_weights(x, s, before=180, after=20, need=0.9):
    """공연 하나의 기록 x에 대수 가중치를 매긴다. 시간순 덩어리 기록은 그 공연 시간대를 받은 비율로 채운다.
    돌려주는 값: (가중치 배열, 이 공연 대수를 믿을 수 있나, 시간순 덩어리 받은 비율 또는 None)"""
    w = x.w.values.astype(float).copy()
    ordm = x["ord"].fillna(False).values.astype(bool) if "ord" in x else np.zeros(len(x), dtype=bool)
    ok, c = ordered_ok(x, s, before, after, need)
    if ordm.any():
        w[ordm] = (1.0 / c) if ok else np.nan
    return w, bool(ok and not np.isnan(w).any()), c


def enough_2025(cov):
    """2025 대수를 쓸 수 있나: 아예 못 받은 번호 덩어리가 없을 때(덩어리 번호 폭 합이 전체 줄 수의 99% 이상).
    덩어리 안에서 못 받은 줄은 받은 비율로 보정한다(달별 또는 공연별)."""
    return sum(v["span"] for v in cov.values()) >= 0.99 * TOTAL_2025


def got_2025(cov):
    """받은 줄 수(겹친 줄 뺀 값)"""
    return sum(v["got"] for v in cov.values())


def note_2025(cov):
    """화면·자료 설명에 붙일 2025 보정 설명 (짧게)"""
    mon = lambda ms: "·".join(m[4:].lstrip("0") for m in ms)
    cut = [m for m, v in cov.items() if v.get("capped") and v.get("layout") != "시간순"]
    ordered = [m for m, v in cov.items() if v.get("layout") == "시간순"]
    cut_ord = [m for m in ordered if cov[m].get("capped")]
    t = f"2025 자료 {got_2025(cov) / TOTAL_2025:.0%} 받음(겹친 줄 뺀 값), 받은 비율로 보정"
    if cut:
        t += f". {mon(cut)}월은 원본이 한 달 65,535줄로 잘려 대수에서 뺌"
    if ordered:
        t += f". {mon(ordered)}월은 공연 시간대 기록을 90% 넘게 받은 공연만"
        if cut_ord:
            t += f"({mon(cut_ord)}월은 원본이 잘려 앞쪽 며칠만 있음)"
    return t


def load_all():
    """(2024 + 2025 합친 표, 2025 달별 받은 비율, 2025 받은 줄 수)"""
    d25, cov = load_2025()
    d = pd.concat([d25, load_2024()], ignore_index=True)
    return d, cov, got_2025(cov)


def kspo_shows(min_year="2024-07"):
    """KSPO DOME 공연일 중 시작 시각이 하루 한 번인 날 (날짜, 시작, 공연명). 하루 종일 하는 페스티벌은 뺀다."""
    ev = pd.read_csv(EVENTS, encoding="utf-8-sig")
    out = []
    for _, r in ev[ev["공연장"] == "KSPO DOME"].iterrows():
        ts = str(r["시작시각들"]).split(";")
        if len(ts) != 1 or not re.match(r"^\d{1,2}:\d{2}$", ts[0]) or r["날짜"] < min_year:
            continue
        if "페스티벌" in str(r["공연명"]):
            continue
        out.append((r["날짜"], ts[0].zfill(5), str(r["공연명"])))
    return out


def big_event_days():
    """공원 큰 공연장(KSPO DOME·핸드볼경기장·올림픽홀)에 공연이 있는 날짜 집합 (비교 기준일에서 뺄 때)"""
    ev = pd.read_csv(EVENTS, encoding="utf-8-sig")
    return set(ev[ev["공연장"].isin(["KSPO DOME", "핸드볼경기장", "올림픽홀"])]["날짜"])


def audience_cars(x, day, start):
    """scripts/09와 같은 관객 차 기준: 시작 3시간 전~20분 뒤 입차, 2시간 넘게 머물고, 시작 1.5~7시간 사이 출차.
    돌려주는 값: (가중 대수, 받은 대수)"""
    s = pd.Timestamp(f"{day} {start}")
    rin = (x.in_time - s).dt.total_seconds() / 60
    rout = (x.out_time - s).dt.total_seconds() / 60
    a = x[(rin >= -180) & (rin <= 20) & (rout >= 90) & (rout <= 420) & (rout - rin >= 120)]
    return float(a.w.sum(skipna=False)), int(len(a))


ENTRY_FROM, ENTRY_TO = -360, 30              # 입차 분석에서 관객 차로 보는 입차 시간(공연 시작 기준 분)


def entry_timing(x, s, lo=ENTRY_FROM, hi=ENTRY_TO):
    """공연 관객 차가 들어온 시각: 시작 6시간 전~30분 뒤에 들어와 2시간 넘게 머물고 시작 1.5~7시간 사이에 나간 차.
    (출차 분석의 관객 차는 3시간 전부터지만, 공연날 아침·낮에 미리 오는 차가 많아 입차는 6시간 전부터 본다)
    돌려주는 값: {'in50': 절반이 들어온 때, 'in90': 90%가 들어온 때(시작 기준 분), 'n': 대수} 또는 None(150대 미만)"""
    rin = ((x.in_time - s).dt.total_seconds() / 60).values
    rout = ((x.out_time - s).dt.total_seconds() / 60).values
    a = rin[(rin >= lo) & (rin <= hi) & (rout >= 90) & (rout <= 420) & (rout - rin >= 120)]
    if len(a) < 150:
        return None
    return {"in50": int(round(float(np.percentile(a, 50)))), "in90": int(round(float(np.percentile(a, 90)))), "n": int(len(a))}

