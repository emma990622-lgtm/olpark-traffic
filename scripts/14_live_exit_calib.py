"""
공연 당일 '실시간 출차 감지' 규칙을 과거 입출차 기록으로 맞추고(보정), 얼마나 정확한지 되짚어 본다.

생각
  공연이 언제 끝나는지 미리 맞히는 건 어렵다(과거 70회 기준 '몰리기 시작' 오차 ±29분).
  대신 공연 당일 실시간 주차 대수(parking_sum, 5분마다)가 갑자기 줄기 시작하는 순간을 잡으면
  그때부터 "절반·90%가 빠지는 시각"을 훨씬 정확히 안내할 수 있다.

실시간 값 흉내
  parking_sum = (그날 들어와서 아직 안 나간 차) + (안 닫힌 오래된 기록, 거의 일정)
  → 5분마다의 '변화량'은 입출차 기록으로 그대로 재현된다(일정한 부분은 빼면 사라짐).
  모든 규칙은 비율(관객 차 증가량 대비)로 정해서, 2025 자료가 일부만 있어도(88% 등) 그대로 쓸 수 있다.

규칙 (11/19 실측 곡선을 보고 정함)
  여름엔 공연 3시간 전에 이미 낮 방문객 차가 많고 공연 즈음 빠져서, '공연 전 증가량'은 관객 수를 못 나타낸다.
  그래서 공연 시작 뒤의 최고 대수 M(t) = max P(시작~t)를 기준으로 삼는다(실시간 값에선 새벽 기준값 G를 빼고 씀).
  감지: 시작+60분 이후, 최근 W분 동안 P가 r×M 이상 줄고, 다음 5분에도 계속 줄면 "출차 시작"
  감지 후: 관객 차 절반·90%가 빠지는 시각 = 감지 시각 + 과거 공연의 '감지→도달' 시간(중앙값, 보통 범위 p25~p75)

입력  data/raw/kcisa_inout_2025.jsonl(있는 만큼), data/raw/parking_inout_202407.csv, data/processed/event_days.csv
출력  web/data/live_exit.json
실행  python scripts\\14_live_exit_calib.py      (원본이 있는 주인 컴퓨터: run_live_exit.bat → 끝나면 올릴지 물어봄)
"""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "data" / "live_exit.json"
spec = importlib.util.spec_from_file_location("ep", ROOT / "scripts" / "09_exit_profile.py")
ep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ep)

STEP = 5                                   # 실시간 값이 5분마다라고 보고 흉내
RATIOS = [0.06, 0.08, 0.10, 0.12, 0.15, 0.18, 0.22]
WINDOWS = [10, 15]
EARLIEST = 60                              # 시작 후 이 분 전에는 감지하지 않음(늦게 온 관객·다른 행사 차)
SER_FROM, SER_TO = -30, 330                # 화면 미리 보기용 곡선 범위


def series(x, s):
    """시작 s 기준 -180~+420분, 5분 간격 '그날 들어와 아직 안 나간 차' 대수."""
    t = np.arange(-180, 421, STEP)
    rin = ((x.in_time - s).dt.total_seconds() / 60).values
    rout = ((x.out_time - s).dt.total_seconds() / 60).values
    keep = rin >= -600                     # 그날 들어온 차만(오래된 차는 실시간 값에서도 일정한 몫)
    rin, rout = rin[keep], rout[keep]
    P = np.array([((rin <= m) & (rout > m)).sum() for m in t])
    return t, P


def peak_since_start(t, P, i):
    m = (t >= 0) & (np.arange(len(t)) <= i)
    return P[m].max() if m.any() else P[i]


def detect(t, P, r, w):
    k = w // STEP
    for i in range(len(t) - 1):
        if t[i] < EARLIEST or i < k:
            continue
        M = peak_since_start(t, P, i)
        if M >= 100 and P[i - k] - P[i] >= r * M and P[i + 1] < P[i]:   # 계속 줄어야(한 번 출렁임은 무시)
            return i
    return None


def progress_times(t, P, i_det):
    """감지 시점부터 진행률 50%·90%(감지 전 최고 대수 대비 빠져나간 비율)에 닿기까지 걸린 분."""
    M = peak_since_start(t, P, i_det)
    res = {}
    for f in (0.5, 0.9):
        hit = next((j for j in range(i_det, len(t)) if M - P[j] >= f * M), None)
        res[f] = None if hit is None else int(t[hit] - t[i_det])
    return res, int(M)


def main():
    ev = pd.read_csv(ep.EVENTS, encoding="utf-8-sig")
    d = pd.concat([ep.load_2025(), ep.load_2024()], ignore_index=True)
    d["day"] = d.in_time.dt.strftime("%Y-%m-%d")
    d["oday"] = d.out_time.dt.strftime("%Y-%m-%d")
    shows = []
    for _, row in ev[ev["공연장"] == "KSPO DOME"].iterrows():
        day, ts = row["날짜"], str(row["시작시각들"]).split(";")
        if len(ts) != 1 or "페스티벌" in str(row["공연명"]):
            continue
        x = d[(d.day == day) | (d.oday == day)]
        if len(x) < 800:
            continue
        s = pd.Timestamp(f"{day} {ts[0]}")
        if not ep.ic.ordered_ok(x, s, 180, 20)[0]:   # 10~12월: 관객 차 입차 시간대 기록에 빈 곳이 있는 공연은 뺀다(09와 같게)
            continue
        prof = ep.analyze(d[d.oday == day], day, ts[0])   # 기존 방식의 '몰리기 시작'(정답 역할)
        if not prof:
            continue
        t, P = series(x, s)
        A = int(P[t >= 0].max())                # 시작 뒤 최고 대수(참고용)
        if A < 100:
            continue
        shows.append({"date": day, "start": ts[0], "src": prof["src"], "title": row["공연명"], "A": A,
                      "surge": prof["surgeMin"], "t50": prof["t50"], "t90": prof["t90"], "t": t, "P": P})
    if not shows:
        raise SystemExit("계산할 공연일이 없습니다.")

    # 정답: 기존 방식(09)으로 구한 '관객 차 절반·90%가 빠져나간 시각'(공연 시작 기준 분)
    for sh in shows:
        sh["abs50"], sh["abs90"] = sh["surge"] + sh["t50"], sh["surge"] + sh["t90"]

    def evaluate(r, w):
        """한 공연씩 빼고 나머지로 맞혀 본다. 미리 = 시작 시각 + (나머지 공연 중앙값), 감지 후 = 감지 시각 + (나머지 공연의 '감지→도달' 중앙값)"""
        D = []
        for sh in shows:
            i = detect(sh["t"], sh["P"], r, w)
            if i is not None:
                D.append({"sh": sh, "det": int(sh["t"][i])})
        res = {"found": len(D), "n": len(shows), "early30": sum(d["det"] - d["sh"]["surge"] < -30 for d in D)}
        if len(D) < 5:
            return res | {"err": None, "score": 999}
        err = {}
        for k in ("abs50", "abs90"):
            pre, live = [], []
            for j, d in enumerate(D):
                o = [x for jj, x in enumerate(D) if jj != j]
                truth = d["sh"][k]
                pre.append(abs(np.median([x["sh"][k] for x in o]) - truth))
                live.append(abs(d["det"] + np.median([x["sh"][k] - x["det"] for x in o]) - truth))
            err[k] = {"before": round(float(np.mean(pre)), 1), "live": round(float(np.mean(live)), 1),
                      "liveMedian": round(float(np.median(live)), 1),
                      "within15": round(float(np.mean(np.array(live) <= 15)), 2)}
        miss = len(shows) - len(D)
        score = (err["abs50"]["live"] + err["abs90"]["live"]) / 2 + 60 * miss / len(shows)
        return res | {"err": err, "score": round(float(score), 1), "D": D}

    # 1) 규칙 고르기: 감지 후 예측 오차가 가장 작고, 놓친 공연이 적은 것
    grid, best = [], None
    for r in RATIOS:
        for w in WINDOWS:
            e = evaluate(r, w)
            grid.append({"r": r, "w": w, "found": e["found"], "n": e["n"], "early30": e["early30"],
                         "err50": e["err"] and e["err"]["abs50"]["live"], "err90": e["err"] and e["err"]["abs90"]["live"],
                         "score": e["score"]})
            if best is None or e["score"] < best["score"]:
                best = e | {"r": r, "w": w}
    r, w, D = best["r"], best["w"], best["D"]

    rows = [{"date": d["sh"]["date"], "start": d["sh"]["start"], "src": d["sh"]["src"], "peak": d["sh"]["A"],
             "det": d["det"], "surge": d["sh"]["surge"], "abs50": d["sh"]["abs50"], "abs90": d["sh"]["abs90"],
             # 화면 '지난 공연으로 미리 보기'용: 시작 −30분 ~ +330분, 5분 간격 대수
             "series": [int(v) for v in d["sh"]["P"][(d["sh"]["t"] >= SER_FROM) & (d["sh"]["t"] <= SER_TO)]]} for d in D]
    R = pd.DataFrame(rows)
    d50, d90 = (R.abs50 - R.det).values, (R.abs90 - R.det).values

    q = lambda v, p: int(round(float(np.percentile(v, p))))
    out = {
        "built": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "method": ("실시간 주차 대수(약 5분마다)로 '출차 시작'을 감지. M = 공연 시작 뒤 지금까지의 최고 대수(출차 기록 없는 차를 뺀 값). "
                   f"시작 {EARLIEST}분 뒤부터, 최근 {w}분 동안 M의 {int(r * 100)}% 이상 줄고 다음 값도 계속 줄면 감지. "
                   "감지되면 '관객 차 절반·90%가 빠지는 시각' = 감지 시각 + 과거 공연에서 감지 뒤 걸린 시간(중앙값)."),
        "series": {"fromMin": SER_FROM, "stepMin": STEP},
        "rule": {"ratio": r, "windowMin": w, "earliestMin": EARLIEST, "stepMin": STEP, "minPeak": 100, "confirmNext": True},
        "after": {  # 감지 시점부터 관객 차 절반·90%가 빠지기까지 걸린 분(과거 공연)
            "half": {"p25": q(d50, 25), "med": q(d50, 50), "p75": q(d50, 75), "n": int(len(d50))},
            "most": {"p25": q(d90, 25), "med": q(d90, 50), "p75": q(d90, 75), "n": int(len(d90))},
        },
        "backtest": {
            "shows": best["n"], "found": best["found"], "early30": best["early30"],
            "half": best["err"]["abs50"], "most": best["err"]["abs90"],
            "bySource": {k: int((R.src == k).sum()) for k in sorted(R.src.unique())},
            "period": f"{R.date.min()} ~ {R.date.max()}",
            "note": ("한 공연씩 빼고 나머지 공연으로 맞혀 본 평균 오차(분). before = 공연 시작 시각만 보고 미리 예측, "
                     "live = 출차 시작 감지 뒤 예측. 정답은 입출차 기록에서 관객 차 절반·90%가 빠져나간 시각."),
        },
        "grid": grid,
        "list": rows,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=int), encoding="utf-8")
    bt = out["backtest"]
    print(f"공연 {bt['shows']}회({bt['period']}, {bt['bySource']}), 규칙 r={r} w={w}분 → 감지 {bt['found']}회, 30분 넘게 이른 감지 {bt['early30']}회")
    print(f"절반 빠지는 시각 오차: 미리 {bt['half']['before']}분 → 감지 후 {bt['half']['live']}분 (15분 이내 {bt['half']['within15']:.0%})")
    print(f"90% 빠지는 시각 오차: 미리 {bt['most']['before']}분 → 감지 후 {bt['most']['live']}분 (15분 이내 {bt['most']['within15']:.0%})")
    print(f"감지 후 절반까지 {out['after']['half']}분, 90%까지 {out['after']['most']}분")
    print(f"저장 → {OUT}")


def ask_push():
    """주인 컴퓨터(run_live_exit.bat)에서: 새로 맞춘 결과만 GitHub main에 올릴지 묻는다(1~2분 뒤 사이트 반영)."""
    import subprocess
    try:
        a = input("\n결과(web/data/live_exit.json)를 GitHub에 올릴까요? 올리면 1~2분 뒤 사이트에 반영돼요. (y/n): ").strip().lower()
    except EOFError:
        return
    if a not in ("y", "yes", "ㅛ"):
        print("올리지 않았어요.")
        return
    rel = "web/data/live_exit.json"
    for c in (["git", "add", rel], ["git", "commit", "-m", "[주인 PC] 실시간 출차 감지 규칙 다시 맞춤 (전체 입출차 기록)"],
              ["git", "pull", "--rebase", "--autostash"], ["git", "push"]):
        r = subprocess.run(c, cwd=ROOT)
        if r.returncode != 0 and c[1] != "commit":
            print("※ 올리기 중 문제가 생겼어요. 이 창 내용을 AI에게 보여 주세요.")
            return
    print("올렸어요.")


if __name__ == "__main__":
    import sys
    main()
    if "--ask-push" in sys.argv:
        ask_push()
