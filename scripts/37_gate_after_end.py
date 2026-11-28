"""종료 시각 확인 공연의 진입문·출구별 출차 중앙 시점을 계산한다."""

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median


ROOT = Path(__file__).resolve().parents[1]
GATES = ("북2", "동2", "남2")


def csv_rows(name):
    with (ROOT / "data" / "processed" / name).open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def main():
    known = defaultdict(list)
    for row in csv_rows("exit_after_end_shows.csv"):
        known[row["date"]].append(float(row["actual_min"]))

    # 출차 집계표는 날짜 단위이므로 분석 대상 공연이 한 회차인 날만 사용.
    shows_per_date = Counter(row["date"] for row in csv_rows("exit_weather_shows.csv"))
    runtimes = {
        date: minutes[0]
        for date, minutes in known.items()
        if len(minutes) == 1 and shows_per_date[date] == 1
    }
    per_event = defaultdict(dict)
    for row in csv_rows("exit_gate_pairs.csv"):
        date, entry, exit_gate = row["date"], row["gin"], row["gout"]
        if date in runtimes and entry in GATES and exit_gate in GATES:
            per_event[date, entry][exit_gate] = float(row["median"]) - runtimes[date]

    by_entry = {}
    for entry in GATES:
        # 같은 출발 구역의 세 출구를 동일한 공연 표본으로 비교.
        matched = [exits for (_, zone), exits in per_event.items() if zone == entry and all(gate in exits for gate in GATES)]
        if not matched:
            continue
        by_entry[entry] = {
            "shows": len(matched),
            "minutes": {gate: round(median(exits[gate] for exits in matched)) for gate in GATES},
        }

    data = {
        "method": "같은 KSPO DOME 공연·진입문에서 기록된 출구별 출차 시각 중앙값에서 확인된 공연 종료 시각을 뺀 뒤, 해당 공연들의 중앙값",
        "byEntry": by_entry,
    }
    output = ROOT / "web" / "data" / "gate_after_end.json"
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
