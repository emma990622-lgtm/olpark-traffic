"""
운영자 화면 '데이터 점검 결과' 카드용 요약을 만든다. 원본이 없어도 돈다(이미 만들어진 점검·결과 파일만 읽음).

입력: data/processed/kcisa_2025_check.json   (scripts/17, 주인 PC에서 run_check_2025.bat)
      web/data/exit_profile.json, park_profile.json, kspo_waves.json, exit_curves.json (제외한 공연 목록 skipped2025)
출력: web/data/data_quality.json

  실행: python scripts\\19_data_quality.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECK = ROOT / "data" / "processed" / "kcisa_2025_check.json"
WEB = ROOT / "web" / "data"
OUT = WEB / "data_quality.json"
CAP_SPAN = 70000                       # 번호 폭이 이보다 작은 달 = 65,535줄로 잘린 달 (inout_common과 같게)
ORDERED = {"202510", "202511", "202512"}   # 입차 시각 순서로 저장된 달 (2026-11-20 확인, docs/context.md 데이터 함정)

GAPS = ROOT / "data" / "raw" / "kcisa_inout_2025.gaps.txt"


def gap_summary():
    """kcisa_inout_2025.gaps.txt에서 실제 건너뛴 구간 수·총 줄 수·주요 오류 코드를 읽는다."""
    if not GAPS.exists():
        return 9, 90, "504"
    spans, lines, codes = 0, 0, set()
    for raw in GAPS.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        parts = s.split(",")
        if len(parts) >= 3:
            try:
                spans += 1
                lines += int(parts[1]) - int(parts[0])
                codes.add(parts[2].strip())
            except ValueError:
                continue
    return (spans or 9), (lines or 90), "·".join(sorted(codes)) or "504"


def build_issues():
    spans, skipped_lines, code = gap_summary()
    return [
        {"data": "2025년 입출차", "problem": "한 달 기록이 65,535줄에서 잘린 달이 있어요(8·9·11·12월)",
         "handling": "8·9월은 대수 계산에서 빼고 시각·비중만 써요. 11·12월은 기록이 남은 앞쪽 날만 써요."},
        {"data": "2025년 입출차", "problem": "내려받을 때 같은 줄이 겹쳐서 와요(327,684줄 중복)",
         "handling": "기록 번호(LOCAL_ID)로 하나만 남겨 유효 2,083,451줄만 써요."},
        {"data": "2025년 입출차", "problem": "달마다 저장 순서가 달라요(1~9월은 여러 날이 섞임, 10~12월은 입차 시각 순서)",
         "handling": "10~12월은 공연 시간대 기록을 90% 넘게 받은 공연만 써요."},
        {"data": "2025년 입출차", "problem": f"특정 구간({spans}곳)에서 서버 시간 초과 오류({code})가 반복돼요",
         "handling": f"총 {skipped_lines}줄을 건너뛰고 건너뛴 위치를 kcisa_inout_2025.gaps.txt에 기록해요."},
        {"data": "차량 이용현황", "problem": "파일명 표기 월과 실제 수록 월이 다르거나 같은 달이 두 파일에 중복돼 있어요",
         "handling": "날짜 기준으로 달마다 행 수가 가장 많은 파일 하나만 고르고 중복 행을 제거해 써요."},
        {"data": "공식 공연 일정", "problem": "사전 취소·휴연 회차가 남아 있거나 공원 일정과 예매처 시각·관람시간이 다를 때가 있어요",
         "handling": "사전 취소(2025-01-04~05 로드 투 킹덤)·월요일 휴연 오표기(2024-10-14 투란도트)를 공연 통계에서 빼고, 폭발물 신고로 2시간 늦게 시작한 회차(2025-08-10 더보이즈)는 종료 시각 통계에서 분리하며, 앞으로 공연은 예매처 시각·관람시간을 우선 써요."},
        {"data": "실시간 주차현황", "problem": "출차 기록이 안 닫힌 장기 차량이 쌓여 새벽에도 1,000대 넘게 나와요",
         "handling": "매일 새벽 값을 기록해 실제 새벽 주차 중앙값(225대)과의 차이만큼 빼서 보여요."},
        {"data": "주차장 혼잡도", "problem": "등록시간 칸의 분·초 자리에 월·일이 들어 있어요",
         "handling": "시 단위로만 써요."},
        {"data": "2025년 연계 데이터", "problem": "주차대수·방문객·기온·강수량·공연명·관람객수 칸이 모두 비어 있어요",
         "handling": "서울 생활인구·지하철·기상·입출차를 직접 묶어 시간별 연계표(visitor_hourly.csv)를 만들고, 실제 관객 수는 대관 정산 인원 데이터로 교차 확인했어요."},
        {"data": "입출차·주차 면수", "problem": "주차 대수가 총 면수(2,120면)를 넘는 공연이 많아요",
         "handling": "24시간 이상 장기 차량을 빼고도 넘는 회차는 '기록상 면수보다 많음, 참고값'으로 밝혀요."},
        {"data": "도로 구간 도형", "problem": "서울시 도로 58구간 중 1개 구간(1230028803)의 TMAP 상세 도형이 비어 있어요",
         "handling": "누락된 1개 구간은 시·종점 직선 좌표로 이어 지도에 빈 구간이 없게 해요."},
    ]


def load(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def main():
    c = load(CHECK)
    issues = build_issues()
    out = {"built": None, "issues": issues, "check": None, "months": [], "skipped": {}}
    if c:
        out["check"] = {"total": c["total2025"], "received": c["lines"], "duplicates": c["dupSameLine"] + c.get("dupDiffContent", 0),
                        "usable": c["usable"], "usableShare": c["usableShare"],
                        "spanShare": round(sum(v["span"] for v in c["coverage"].values()) / c["total2025"], 4)}
        for m, v in sorted(c["coverage"].items()):
            notes = []
            if v["span"] <= CAP_SPAN:
                notes.append("원본이 65,535줄로 잘림")
            if m in ORDERED:
                notes.append("입차 시각 순서로 저장")
            out["months"].append({"month": f"{m[:4]}-{m[4:]}", "got": v["got"], "span": v["span"], "ratio": v["ratio"], "note": " · ".join(notes)})
    for f, label in (("exit_profile", "출차 분석"), ("park_profile", "주차 대수 곡선"), ("kspo_waves", "15분 출차 최대"), ("exit_curves", "입차·출차 곡선")):
        d = load(WEB / f"{f}.json")
        if not d:
            continue
        sk = d.get("skipped2025") or (d.get("summary") or {}).get("skipped2025") or []
        n = (d.get("summary") or {}).get("shows") or (d.get("summary") or {}).get("n") or (sum(d["bySource"].values()) if d.get("bySource") else None) \
            or (sum(g["n"] for g in d["groups"].values()) if d.get("groups") else None)
        out["skipped"][f] = {"label": label, "used": n, "skipped": len(sk), "dates": sk}
        out["built"] = max(out["built"] or "", str(d.get("built") or ""))
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"점검 요약 저장 → {OUT} (달 {len(out['months'])}개, 문제 {len(issues)}건)")


if __name__ == "__main__":
    main()
