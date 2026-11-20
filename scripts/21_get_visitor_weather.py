"""
수집기 저장소(olpark-collector)의 data/visitor-weather 갈래에 GitHub Actions가 받아 둔
날씨·지하철 승하차·생활인구(2026) 파일을 이 저장소 data/raw/visitor_weather/ 로 가져온다. 인증키 불필요(git만 씀).

  실행: python scripts/21_get_visitor_weather.py [--collector ../olpark-collector]
원본(받은 그대로)은 data/raw/visitor_weather/ 에 둔다. 다시 받으려면 수집기 저장소 갈래에서 워크플로를 다시 돌린다.
"""
import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "data" / "raw" / "visitor_weather"
BRANCH = "origin/data/visitor-weather"
FILES = ["weather_hourly_openmeteo.csv", "subway_daily_olpark.csv", "subway_daily_files_olpark.csv", "subway_hourly_month_olpark.csv",
         "oryun_living_pop_2026.csv", "README_fetch_log.txt"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collector", default=str(ROOT.parent / "olpark-collector"))
    a = ap.parse_args()
    c = Path(a.collector)
    if not (c / ".git").exists():
        raise SystemExit(f"수집기 저장소가 없어요: {c} (git clone https://github.com/emma990622-lgtm/olpark-collector)")
    subprocess.run(["git", "-C", str(c), "fetch", "-q", "origin",
                    "+refs/heads/data/visitor-weather:refs/remotes/origin/data/visitor-weather"], check=True)
    DEST.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        r = subprocess.run(["git", "-C", str(c), "show", f"{BRANCH}:data/visitor_weather/{f}"], capture_output=True)
        if r.returncode != 0:
            print(f"없음: {f}")
            continue
        (DEST / f).write_bytes(r.stdout)
        print(f"가져옴: {f} ({len(r.stdout):,} bytes)")


if __name__ == "__main__":
    main()
