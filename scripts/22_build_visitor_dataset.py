"""
공연·날씨·입출차·방문객을 한 시간 단위로 묶은 '연계 데이터'를 만든다(2024-06 ~ 최근).
한국체육산업개발 '2025 차량입출차·공연·날씨 연계 데이터'(문화공공데이터광장 API_CPM_009)가 값이 모두 비어 있어
(주인 PC에 받은 8,000줄 확인, 2026-11-21) 같은 구성을 공개 자료로 직접 만든다. 인증키 불필요.

입력
  data/processed/event_days.csv                  공원 공연 일정(공연장·시작 시각·좌석 규모 참고값)
  data/raw/visitor_weather/weather_hourly_openmeteo.csv   시간별 날씨(Open-Meteo, ERA5 기반)
  data/raw/seoul_living_pop_11710566.csv (+ visitor_weather/oryun_living_pop_2026.csv)  올림픽공원 동 시간별 생활인구
  data/raw/visitor_weather/subway_daily_files_olpark.csv (+ subway_daily_olpark.csv)  주변 역 일별 승하차(서울 열린데이터광장 OA-12914 월별 파일 + 일별 API)
  입출차 원본(inout_common): 2024년 7월 전체 + 2025년(못 받은 덩어리가 없을 때만, 받은 비율로 보정)
출력
  data/processed/visitor_hourly.csv   1줄 = 1시간. 칸 설명은 docs/visitor_dataset.md
  실행: python scripts/22_build_visitor_dataset.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inout_common as ic  # noqa: E402

ROOT = ic.ROOT
RAW = ROOT / "data" / "raw"
VW = RAW / "visitor_weather"
OUT = ROOT / "data" / "processed" / "visitor_hourly.csv"
START = pd.Timestamp("2024-06-01")
BIG = ("KSPO DOME", "핸드볼경기장", "올림픽홀")
SHOW_LEN = 180                                  # 공연 중으로 보는 시간(분, 참고 칸 show_on 용)

# 공휴일(대체공휴일 포함): data/processed/holidays_kr.csv (파이썬 holidays 꾸러미로 만든 2024~2027 표, 2026-11-21)
_hp = ROOT / "data" / "processed" / "holidays_kr.csv"
HOL = dict(pd.read_csv(_hp, encoding="utf-8-sig").values) if _hp.exists() else {d: "공휴일" for d in ic.HOLIDAYS}


def weather():
    p = VW / "weather_hourly_openmeteo.csv"
    if not p.exists():
        return None
    w = pd.read_csv(p)
    w["dt"] = pd.to_datetime(w["time"])
    return w.drop(columns=["time"]).rename(columns={
        "temperature_2m": "temp_c", "apparent_temperature": "feels_c", "precipitation": "precip_mm", "rain": "rain_mm",
        "snowfall": "snow_cm", "relative_humidity_2m": "humidity_pct", "wind_speed_10m": "wind_kmh",
        "weather_code": "weather_code", "cloud_cover": "cloud_pct"})


def living_pop():
    fs = [RAW / "seoul_living_pop_11710566.csv", VW / "oryun_living_pop_2026.csv"]
    parts = [pd.read_csv(f, index_col=False, dtype=str) for f in fs if f.exists()]
    if not parts:
        return None
    d = pd.concat(parts, ignore_index=True)
    d.columns = [c.strip().strip('"').lstrip("﻿") for c in d.columns]
    for c in d.columns[3:]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["dt"] = pd.to_datetime(d["기준일ID"].str.strip('"'), format="%Y%m%d") + pd.to_timedelta(pd.to_numeric(d["시간대구분"].str.strip('"')), unit="h")
    male = [c for c in d.columns if c.startswith("남자")]
    female = [c for c in d.columns if c.startswith("여자")]
    young = [c for c in male + female if any(s in c for s in ("15세부터19세", "20세부터24세", "25세부터29세", "30세부터34세"))]
    out = pd.DataFrame({"dt": d["dt"], "pop_total": d["총생활인구수"].round(0),
                        "pop_female_share": (d[female].sum(axis=1) / d[male + female].sum(axis=1)).round(3),
                        "pop_15_34_share": (d[young].sum(axis=1) / d[male + female].sum(axis=1)).round(3)})
    return out.drop_duplicates("dt", keep="last")


def subway():
    """주변 역 일별 승하차. 월별 파일(OA-12914, 2024-06~)을 먼저 쓰고, 파일에 없는 최근 날은 일별 API 값으로 채운다."""
    parts = []
    for f, src in (("subway_daily_files_olpark.csv", "file"), ("subway_daily_olpark.csv", "api")):
        p = VW / f
        if not p.exists() or p.stat().st_size < 100:
            continue
        s = pd.read_csv(p, dtype=str, index_col=False)                     # 월별 파일은 줄 끝에 빈 칸이 하나 더 있음
        s.columns = [c.strip().strip('"').lstrip("\ufeff") for c in s.columns]
        pick = lambda *names: next(c for c in s.columns if c in names)
        t = pd.DataFrame({"date": pd.to_datetime(s[pick("USE_YMD", "USE_DT", "사용일자")].str.strip('"'), format="%Y%m%d").dt.strftime("%Y-%m-%d"),
                          "st": s[pick("SBWY_STNS_NM", "SUB_STA_NM", "역명")].str.strip('"').str.replace(r"\(.*\)", "", regex=True).str.strip(),
                          "on": pd.to_numeric(s[pick("GTON_TNOPE", "RIDE_PASGR_NUM", "승차총승객수")].str.strip('"'), errors="coerce"),
                          "off": pd.to_numeric(s[pick("GTOFF_TNOPE", "ALIGHT_PASGR_NUM", "하차총승객수")].str.strip('"'), errors="coerce"),
                          "src": src})
        parts.append(t)
    if not parts:
        return None
    t = pd.concat(parts, ignore_index=True)
    file_days = set(t[t.src == "file"].date)
    t = t[(t.src == "file") | ~t.date.isin(file_days)]
    t = t.groupby(["date", "st"])[["on", "off"]].sum().reset_index()
    wide = t.pivot(index="date", columns="st", values="off")                    # 내린 사람(공원으로 오는 쪽)
    wide.columns = [f"subway_off_{c}" for c in wide.columns]
    wide["subway_off_total"] = wide.sum(axis=1, min_count=1)
    wide["subway_on_total"] = t.groupby("date")["on"].sum()
    return wide.reset_index()


def events():
    e = pd.read_csv(ROOT / "data" / "processed" / "event_days.csv")
    rows = []
    for day, g in e.groupby("날짜"):
        k = g[g["공연장"] == "KSPO DOME"]
        times = sorted({t for v in k["시작시각들"].dropna() for t in str(v).split(";") if t})
        oth = g[g["공연장"].isin(BIG) & (g["공연장"] != "KSPO DOME")]
        rows.append({"date": day, "kspo_show": int(len(k) > 0), "kspo_title": "; ".join(k["공연명"].astype(str).unique())[:80],
                     "kspo_start": times[0] if times else "", "kspo_shows_n": len(times),
                     "other_big_venues": "·".join(sorted(oth["공연장"].unique())),
                     "other_big_seats": int(pd.to_numeric(oth["좌석규모_참고"], errors="coerce").fillna(0).sum()),
                     "venues_n": g["공연장"].nunique(),
                     "seats_total": int(pd.to_numeric(g["좌석규모_참고"], errors="coerce").fillna(0).sum()),
                     "festival": int(g["공연명"].astype(str).str.contains("페스티벌|festival|FESTIVAL").any())})
    return pd.DataFrame(rows)


def parking(hours):
    """동2·남2·북2문 구역, 24시간 이상 주차 제외, 2025는 받은 비율로 보정. 믿을 수 없는 날은 비움."""
    d24 = ic.load_2024()
    d25, cov = ic.load_2025()
    use25 = ic.enough_2025(cov)
    d = pd.concat([d24, d25] if use25 else [d24], ignore_index=True)
    stay = (d.out_time - d.in_time).dt.total_seconds() / 60
    d = d[(stay > 0) & (stay < 24 * 60) & ((d.src == "2024") | d.igate.isin(ic.MAIN_GATES))].copy()
    d["iday"] = d.in_time.dt.strftime("%Y-%m-%d")
    out = []
    for day, x in d.groupby("iday"):
        if day < "2024-07-01":
            continue
        w, ok, _ = ic.show_weights(x, pd.Timestamp(f"{day} 06:00"), before=0, after=18 * 60)
        if not ok or np.isnan(w).any():
            continue
        out.append((day, x.assign(w=w)))
    if not out:
        return None, "없음"
    days = {k for k, _ in out}
    allx = pd.concat([x for _, x in out], ignore_index=True)
    # 앞날에 들어와 이날 머문 차도 있으므로 주차 대수는 이날 기준 모든 기록에서 센다(앞날 기록이 없으면 그날은 과소)
    res = []
    for day in sorted(days):
        prev = (pd.Timestamp(day) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        x = allx[allx.iday.isin([day, prev])]
        full_prev = prev in days
        for h in range(24):
            t0 = pd.Timestamp(f"{day}") + pd.Timedelta(hours=h)
            t1 = t0 + pd.Timedelta(hours=1)
            res.append({"dt": t0,
                        "park_in": round(float(x.w[(x.in_time >= t0) & (x.in_time < t1)].sum())),
                        "park_out": round(float(x.w[(x.out_time >= t0) & (x.out_time < t1)].sum())),
                        "park_parked_end": round(float(x.w[(x.in_time < t1) & (x.out_time >= t1)].sum())),
                        "park_src": day[:4], "park_prevday_ok": int(full_prev)})
    return pd.DataFrame(res), f"{len(days)}일" + (f" (2025: {ic.note_2025(cov)})" if use25 else " (2024년 7월만, 2025는 받은 자료가 모자라 제외)")


def main():
    w = weather()
    end = (w["dt"].max() if w is not None else pd.Timestamp.now().normalize()) + pd.Timedelta(hours=23 - (w["dt"].max().hour if w is not None else 0))
    hours = pd.DataFrame({"dt": pd.date_range(START, end, freq="h")})
    hours["date"] = hours.dt.dt.strftime("%Y-%m-%d")
    hours["hour"] = hours.dt.dt.hour
    hours["dow"] = hours.dt.dt.dayofweek                                        # 0=월
    hours["holiday"] = hours.date.map(HOL).fillna("")
    hours["day_type"] = np.where((hours.dow >= 5) | (hours.holiday != ""), np.where((hours.dow == 5) & (hours.holiday == ""), "토", "일·공휴일"), "평일")
    df = hours.merge(events(), on="date", how="left")
    df["kspo_show"] = df.kspo_show.fillna(0).astype(int)
    for c in ("venues_n", "seats_total", "other_big_seats", "festival", "kspo_shows_n"):
        df[c] = df[c].fillna(0).astype(int)
    st = pd.to_datetime(df.date + " " + df.kspo_start.fillna("").replace("", np.nan), errors="coerce")
    df["kspo_rel_min"] = ((df.dt - st).dt.total_seconds() / 60).round()               # 공연 시작 기준 분(이 시간의 시작)
    df["show_on"] = ((df.kspo_rel_min >= -60) & (df.kspo_rel_min < SHOW_LEN)).astype(int)
    if w is not None:
        df = df.merge(w, on="dt", how="left")
    lp = living_pop()
    if lp is not None:
        df = df.merge(lp, on="dt", how="left")
    sw = subway()
    if sw is not None:
        df = df.merge(sw, on="date", how="left")
    pk, pk_note = parking(hours)
    if pk is not None:
        df = df.merge(pk, on="dt", how="left")
    df["dt"] = df.dt.dt.strftime("%Y-%m-%d %H:%M")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False, encoding="utf-8-sig")
    fill = {c: f"{df[c].notna().mean():.0%}" for c in ("temp_c", "pop_total", "subway_off_total", "park_in") if c in df}
    print(f"저장 → {OUT.relative_to(ROOT)}: {len(df):,}시간 ({df.dt.iloc[0]} ~ {df.dt.iloc[-1]}), 칸 {len(df.columns)}개")
    print(f"채워진 비율: {fill}")
    print(f"주차(입출차): {pk_note}")
    print(f"KSPO DOME 공연일 {df[df.kspo_show == 1].date.nunique()}일, 다른 큰 공연장 공연일 {df[df.other_big_venues.fillna('') != ''].date.nunique()}일")


if __name__ == "__main__":
    main()
