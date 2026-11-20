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

# 원본에서 찾은 문제와 처리 (기획서 6장과 같은 내용. 숫자는 아래 check 값으로 화면에서 채운다)
ISSUES = [
    {"data": "2025년 입출차", "problem": "한 달 기록이 65,535줄에서 잘린 달이 있어요(8·9·11·12월)",
     "handling": "8·9월은 대수 계산에서 빼고 시각·비중만 써요. 11·12월은 기록이 남은 앞쪽 날만 써요."},
    {"data": "2025년 입출차", "problem": "내려받을 때 같은 줄이 겹쳐서 와요",
     "handling": "기록 번호로 하나만 남겨요."},
    {"data": "2025년 입출차", "problem": "달마다 저장 순서가 달라요(1~9월은 여러 날이 섞임, 10~12월은 입차 시각 순서)",
     "handling": "10~12월은 공연 시간대 기록을 90% 넘게 받은 공연만 써요."},
    {"data": "2025년 입출차", "problem": "특정 위치에서 서버 오류(502)가 반복돼요",
     "handling": "그 10줄은 건너뛰고 건너뛴 위치를 기록해요."},
    {"data": "실시간 주차현황", "problem": "출차 기록이 안 닫힌 장기 차량이 쌓여 새벽에도 1,000대 넘게 나와요",
     "handling": "매일 새벽 값을 기록해 그만큼 뺀 값을 보여요."},
    {"data": "주차장 혼잡도", "problem": "등록시간 칸의 분·초 자리에 월·일이 들어 있어요",
     "handling": "시 단위로만 써요."},
    {"data": "2025년 연계 데이터", "problem": "공연 관람객 수 칸이 비어 있어요",
     "handling": "생활인구로 관객 구성을 대신 추정해요. '관객 1명이 차로 올 확률'은 구하지 못했어요."},
    {"data": "입출차·주차 면수", "problem": "주차 대수가 총 면수(2,120면)를 넘는 공연이 많아요",
     "handling": "원인을 확인하지 못해 '기록상 면수보다 많음, 참고값'으로 보여요."},
]


def load(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def main():
    c = load(CHECK)
    out = {"built": None, "issues": ISSUES, "check": None, "months": [], "skipped": {}}
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
    print(f"점검 요약 저장 → {OUT} (달 {len(out['months'])}개, 문제 {len(ISSUES)}건)")


if __name__ == "__main__":
    main()
