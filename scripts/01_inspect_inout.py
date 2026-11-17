"""2024년 7월 올림픽공원 입출차 자료 점검: 필드·기간·품질, 일별/시간별 출차 집계"""
import pandas as pd, numpy as np, sys
src = sys.argv[1] if len(sys.argv) > 1 else "data/raw/parking_inout_202407.csv"
df = pd.read_csv(src, encoding="cp949")
print("행", len(df), "열", list(df.columns))
df["in"] = pd.to_datetime(df["입차일시"], errors="coerce")
df["out"] = pd.to_datetime(df["출차일시"], errors="coerce")
print("입차 파싱 실패", df["in"].isna().sum(), "출차 결측/실패", df["out"].isna().sum())
print("입차 범위", df["in"].min(), "~", df["in"].max())
print("출차 범위", df["out"].min(), "~", df["out"].max())
df["stay"] = (df["out"] - df["in"]).dt.total_seconds() / 60
print("체류(분) 분포\n", df["stay"].describe(percentiles=[.05,.25,.5,.75,.95]).round(1))
print("음수 체류", (df["stay"] < 0).sum(), "0분", (df["stay"] == 0).sum(),
      "10분 미만", (df["stay"] < 10).sum(), "24시간 이상", (df["stay"] >= 1440).sum())
print("완전 중복 행", df.duplicated(["입차일시", "출차일시"]).sum())
# 일별 집계
d = df.dropna(subset=["out"])
day_in = df.groupby(df["in"].dt.date).size()
day_out = d.groupby(d["out"].dt.date).size()
night = d[(d["out"].dt.hour >= 20) | (d["out"].dt.hour < 1)]
night_out = night.groupby((night["out"] - pd.Timedelta(hours=1)).dt.date).size()  # 0시대는 전날로
peak15 = d.set_index("out").resample("15min").size()
pk = peak15.groupby(peak15.index.date).agg(["max", "idxmax"])
tab = pd.DataFrame({"입차": day_in, "출차": day_out, "20~01시출차": night_out,
                    "15분최대출차": pk["max"], "최대시각": pk["idxmax"].astype(str).str[11:16]})
tab.index = pd.to_datetime(tab.index)
tab["요일"] = tab.index.day_name().str[:3]
tab = tab[(tab.index >= "2024-07-01") & (tab.index <= "2024-07-31")]
pd.set_option("display.width", 200)
print(tab.to_string())
tab.to_csv("data/processed/daily_summary_202407.csv", encoding="utf-8-sig")
