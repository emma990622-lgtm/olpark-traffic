"""
입출차 원본을 읽는 공통 함수 (scripts/11, 15 등이 같이 쓴다).

  load_2024()  data/raw/parking_inout_202407.csv  2024년 7월 전체(빠짐없는 기록), 가중치 w = 1
  load_2025()  data/raw/kcisa_inout_2025.jsonl     2025년, 다운로드 중이면 받은 만큼. 가중치 w = 1 / (그 달을 받은 비율)

2025 자료의 '받은 비율' 추정
  - 기록 번호(LOCAL_ID, 예: B050-1872898)는 같은 달 기록끼리 이어진 번호 덩어리다(7월 마지막 번호 + 1 = 8월 첫 번호).
    한 달이 덩어리 여러 개일 수 있다.
  - 덩어리 안에서는 그 달 여러 날 기록이 고르게 섞여 있다(하루 기록의 번호가 덩어리 전체에 퍼져 있음).
  - 그래서 덩어리마다 받은 줄 수 ÷ 번호 폭 = 받은 비율, 가중치 = 1 ÷ 비율.
  - 한계: 아예 못 받은 덩어리는 알 수 없다. 그래서 2025 대수는 전체의 80% 이상 받았을 때만 쓴다(enough_2025).
  - 다운로드를 다 받으면 비율이 모두 1에 가까워진다.
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
COLS = ["in_time", "out_time", "gate", "src", "w"]


def load_2024():
    p = RAW / "parking_inout_202407.csv"
    if not p.exists():
        return pd.DataFrame(columns=COLS)
    o = pd.read_csv(p, encoding="cp949")
    o.columns = ["date", "in_time", "out_time"]
    o["in_time"] = pd.to_datetime(o.in_time, errors="coerce")
    o["out_time"] = pd.to_datetime(o.out_time, errors="coerce")
    o["gate"] = None
    o["src"] = "2024"
    o["w"] = 1.0
    return o.dropna(subset=["in_time", "out_time"])[COLS]


def block_coverage(nums, months, min_run=200):
    """기록 번호를 정렬해 '같은 달이 이어지는 번호 덩어리'로 나누고, 덩어리마다 받은 비율(받은 줄 ÷ 번호 폭)을 구한다.
    한 달이 여러 덩어리일 수 있다(다른 주차 시스템 기록이 따로 번호를 받은 것으로 보임).
    돌려주는 값: (줄마다 받은 비율 배열, 달별 요약 {'202503': {'got', 'span', 'ratio'}})"""
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
    for i, j in merged:
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
    return ratio, dict(sorted(summary.items()))


def load_2025(min_ratio=0.2):
    """2025 입출차. 받은 비율이 min_ratio보다 낮은 달은 대수를 믿기 어려워 w = NaN(대수 계산에서 빼고 비율 계산에만 씀)."""
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
                continue
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
    ratio, cov = block_coverage(df.num.values.astype(np.int64), df.month.values)
    df["in_time"] = pd.to_datetime(df.in_time, errors="coerce")
    df["out_time"] = pd.to_datetime(df.out_time, errors="coerce")
    df["gate"] = df.out_gate.str.extract(r"^(\S+?문)")[0]
    df["src"] = "2025"
    df["w"] = np.where(ratio >= min_ratio, 1.0 / ratio, np.nan)
    return df.dropna(subset=["in_time", "out_time"])[COLS], cov


def enough_2025(got):
    """2025 대수를 믿고 쓸 만큼 받았나 (전체 줄 수의 80% 이상)"""
    return got >= 0.8 * TOTAL_2025


def load_all():
    """(2024 + 2025 합친 표, 2025 달별 받은 비율, 2025 받은 줄 수)"""
    d25, cov = load_2025()
    d = pd.concat([d25, load_2024()], ignore_index=True)
    got = sum(v["got"] for v in cov.values())
    return d, cov, got


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
