"""
공연 종료 후 '가는 방면 빠른 버튼'용 출구별 둘레 도로 주행 시간 계산 (상용 길찾기 API 호출 0회).

원리:
  어느 문(북2·동2·남2)으로 나가든 같은 방면으로 가는 차는 공원 둘레의 같은 합류 교차로에서 만난다.
  합류 교차로 이후 목적지까지 걸리는 시간은 세 출구가 똑같으므로 비교에서 상쇄되고,
  '공원 안 출구 통과 시간 차이(exit_gate.json) + 출구→방면 합류 교차로 둘레 도로 시간'만 비교하면 된다.

입력:
  - web/data/links.json (서울시 실시간 도시데이터 도로 구간 길이·좌표)
  - ../olpark-collector/data/*roykim*/roads.csv (KSPO DOME 공연 종료 출차 시간대 5분 간격 실측 속도)
    * 수집기 폴더가 없는 환경에서 실행하면 기존 gate_directions.json의 구간 속도 중앙값을 재사용한다.
출력:
  - web/data/gate_directions.json (정적 JSON, 웹앱은 외부 길찾기 API 호출 없이 이 파일만 읽음)
"""
import csv
import glob
import json
import math
import os
import statistics as stt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINKS_PATH = ROOT / "web" / "data" / "links.json"
OUT_PATH = ROOT / "web" / "data" / "gate_directions.json"

# KSPO DOME 공연 종료 출차 집중 시간대 (공연 시작 165~255분 뒤, kspo_waves 출차 피크 구간과 동일)
CONCERT_WINDOWS = [
    ("2026-11-21 18:00 KSPO DOME", "2026-11-21", "2026-11-21 20:45", "2026-11-21 22:15"),
    ("2026-11-22 17:00 KSPO DOME", "2026-11-22", "2026-11-22 19:45", "2026-11-22 21:15"),
]


def dist_m(a, b):
    k = math.cos(math.radians((a[1] + b[1]) / 2))
    return math.hypot((a[0] - b[0]) * 111320 * k, (a[1] - b[1]) * 110540)


def line_intersection(p1, p2, p3, p4):
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / den
    py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / den
    return [px, py]


def load_post_concert_speeds(links):
    col_dir = Path(os.environ.get("OLPARK_COLLECTOR") or (ROOT.parent / "olpark-collector"))
    data_dir = col_dir / "data"
    if data_dir.exists():
        seen_ts_link = {}
        timestamps = set()
        for _, day_prefix, t0, t1 in CONCERT_WINDOWS:
            for fn in sorted(glob.glob(str(data_dir / f"{day_prefix}_*" / "roads.csv"))):
                with open(fn, encoding="utf-8-sig") as fp:
                    for r in csv.DictReader(fp):
                        ts = (r.get("수집시각") or "")[:16]
                        lid = r.get("LINK_ID") or ""
                        spd = r.get("속도_kmh") or ""
                        if t0 <= ts <= t1 and spd:
                            seen_ts_link[(ts, lid)] = float(spd)
                            timestamps.add(ts)
        by_link = {l["id"]: [] for l in links}
        for (_, lid), v in seen_ts_link.items():
            if lid in by_link:
                by_link[lid].append(v)
        med = {k: round(stt.median(v), 1) for k, v in by_link.items() if v}
        if med:
            return med, len(timestamps)

    if OUT_PATH.exists():
        old = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        if old.get("linkSpeedMed"):
            return old["linkSpeedMed"], old.get("snapshots", 0)
    raise SystemExit("수집기 도로 속도 파일(../olpark-collector/data)이 없고 기존 gate_directions.json도 없습니다.")


def main():
    links = json.loads(LINKS_PATH.read_text(encoding="utf-8"))
    by_id = {l["id"]: l for l in links}
    med_spd, n_snap = load_post_concert_speeds(links)

    # 북동쪽 모서리 둔촌사거리(강동대로 × 양재대로 직선 교점) 및 서쪽 올림픽회관앞교차로 통과 거리 계산
    dunchon = line_intersection(
        by_id["1230032504"]["a"], by_id["1230032504"]["b"],
        by_id["1230028704"]["a"], by_id["1230028704"]["b"],
    )
    m_chego_dunchon = round(dist_m(by_id["1230032504"]["b"], dunchon))
    m_oryun_dunchon = round(dist_m(by_id["1230028704"]["b"], dunchon))
    m_hoegwan_gap = round(dist_m(by_id["1230030701"]["b"], by_id["1230032100"]["a"]))

    # 공원 둘레 4변(반변 8개) 구간 정의: (LINK_ID 목록, [(추가거리_m, 속도참조_LINK_ID)])
    N_buk2_NW = (["1230033801", "1230033802", "1230033803", "1230034300"], [])
    N_buk2_NE = (["1230032504"], [(m_chego_dunchon, "1230032504")])
    N_NE_buk2 = (["1230032404"], [(m_chego_dunchon, "1230032404")])

    E_dong2_NE = (["1230028704"], [(m_oryun_dunchon, "1230028704")])
    E_NE_dong2 = (["1230028804"], [(m_oryun_dunchon, "1230028804")])
    E_dong2_SE = (["1230028803", "1230028802"], [])
    E_SE_dong2 = (["1230028702", "1230028703"], [])

    S_nam2_SE = (["1230026202"], [])
    S_SE_nam2 = (["1230026102", "1230026103"], [])
    S_nam2_SW = (["1230027100", "1230028100", "1230029300"], [])

    W_SW_NW = (["1230030701", "1230032100", "1230033202"], [(m_hoegwan_gap, "1230032100")])
    W_NW_SW = (["1230033301", "1230032200", "1230030802"], [])

    def eval_chain(*parts):
        ids, extras = [], []
        for a, b in parts:
            ids.extend(a)
            extras.extend(b)
        tot_m = 0.0
        tot_min = 0.0
        for lid in ids:
            ln = by_id[lid]["len"]
            tot_m += ln
            tot_min += (ln / 1000.0) / med_spd[lid] * 60.0
        for m, ref_lid in extras:
            tot_m += m
            tot_min += (m / 1000.0) / med_spd[ref_lid] * 60.0
        return {"meters": round(tot_m), "roadMin": round(tot_min, 1), "links": ids}

    def pick_best(candidates):
        best_via, best_res = min(
            ((via, eval_chain(*parts)) for via, parts in candidates),
            key=lambda x: x[1]["roadMin"],
        )
        return {**best_res, "via": best_via}

    spec = [
        {
            "key": "nw",
            "label": "올림픽대교 · 강북 · 김포방향",
            "sub": "강변북로 · 광진 · 성동 · 올림픽대로 서쪽",
            "hub": "올림픽대교남단교차로",
            "routes": {
                "북2": [("강동대로 서행 직진", [N_buk2_NW])],
                "남2": [("위례성대로 → 올림픽로 북행", [S_nam2_SW, W_SW_NW])],
                "동2": [
                    ("양재대로 북행 → 둔촌사거리 → 강동대로", [E_dong2_NE, N_NE_buk2, N_buk2_NW]),
                    ("양재대로 남행 → 위례성대로 → 올림픽로", [E_dong2_SE, S_SE_nam2, S_nam2_SW, W_SW_NW]),
                ],
            },
        },
        {
            "key": "sw",
            "label": "잠실 · 강남 · 서초",
            "sub": "삼성 · 종합운동장 · 테헤란로 방향",
            "hub": "평화의문(몽촌토성역) 교차로",
            "routes": {
                "남2": [("위례성대로 서행 직진", [S_nam2_SW])],
                "북2": [("강동대로 → 올림픽로 남행", [N_buk2_NW, W_NW_SW])],
                "동2": [("양재대로 남행 → 위례성대로 서행", [E_dong2_SE, S_SE_nam2, S_nam2_SW])],
            },
        },
        {
            "key": "se",
            "label": "송파 · 가락 · 분당 · 판교",
            "sub": "오금 · 위례 · 수서 · 성남 · 수원 방향",
            "hub": "올림픽공원사거리(남동측)",
            "routes": {
                "남2": [("위례성대로 동남행 직진", [S_nam2_SE])],
                "동2": [("양재대로 남행 직진", [E_dong2_SE])],
                "북2": [("강동대로 동행 → 둔촌사거리 → 양재대로 남행", [N_buk2_NE, E_NE_dong2, E_dong2_SE])],
            },
        },
        {
            "key": "ne",
            "label": "천호 · 강동 · 하남 · 구리",
            "sub": "길동 · 둔촌 · 상일IC · 중부고속도로 방향",
            "hub": "둔촌사거리",
            "routes": {
                "북2": [("강동대로 동행 직진", [N_buk2_NE])],
                "동2": [("양재대로 북행 직진", [E_dong2_NE])],
                "남2": [("위례성대로 → 양재대로 북행", [S_nam2_SE, E_SE_dong2, E_dong2_NE])],
            },
        },
    ]

    used_links = set()
    directions = []
    for d in spec:
        by_gate = {}
        for g, cands in d["routes"].items():
            res = pick_best(cands)
            used_links.update(res["links"])
            by_gate[g] = res
        directions.append({
            "key": d["key"],
            "label": d["label"],
            "sub": d["sub"],
            "hub": d["hub"],
            "byGate": by_gate,
        })

    out = {
        "built": "2026-11-23",
        "source": "서울시 실시간 도시데이터(OA-21285) 올림픽공원 주변 도로 소통 — 수집기(olpark-collector) 공연 직후 실측",
        "method": (
            f"KSPO DOME 공연 종료 출차 집중 시간대(시작 165~255분 뒤, 5분 간격 {n_snap}회 시점)의 구간별 속도 중앙값으로 "
            f"출구(북2·동2·남2문)에서 방면별 합류 교차로까지 공원 둘레 도로 주행 시간(거리÷속도)을 계산해 저장. "
            f"합류 교차로 이후 목적지까지 걸리는 시간은 어느 출구로 나가든 같은 길이라 비교에서 상쇄됨(교차로 신호 대기 1~2분은 별도). "
            f"북동쪽 둔촌사거리 연결 구간(서울체고앞 {m_chego_dunchon}m, 오륜교 {m_oryun_dunchon}m)은 강동대로·양재대로 직선 교점 거리와 인접 구간 속도를 적용. "
            "외부 상용 길찾기 API 호출 없음."
        ),
        "shows": [w[0] for w in CONCERT_WINDOWS],
        "snapshots": n_snap,
        "directions": directions,
        "linkSpeedMed": {k: med_spd[k] for k in sorted(used_links)},
    }
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"저장 완료: {OUT_PATH.relative_to(ROOT)} (수집 시점 {n_snap}회, 사용 구간 {len(used_links)}개)")
    for d in directions:
        s = ", ".join(f"{g}문 {v['roadMin']}분({v['meters']}m)" for g, v in d["byGate"].items())
        print(f"  - {d['label']} ({d['hub']}): {s}")


if __name__ == "__main__":
    main()
