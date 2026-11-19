"""
2025년 올림픽공원 주차장 데이터(문화공공데이터광장, KCISA) 내려받기.

  - linked : API_CPM_009  2025 차량입출차, 공연, 날씨정보 등 연계 데이터
  - inout  : API_CPM_008  2025 입출차정보

[사용법 - 윈도우]
  run_kcisa.bat 더블클릭 → 키 붙여넣기 → Enter
    (연계 데이터 확인 3번 요청 → 입출차 전체 받기. 오래 걸림, 끊기면 다시 더블클릭)
  (또는) python scripts\\03_fetch_kcisa_2025.py probe   : 응답 모양만 확인 (요청 4번)
         python scripts\\03_fetch_kcisa_2025.py linked inout

  * 응답 원본을 그대로 JSON Lines(.jsonl)로 저장합니다. 칸 이름이 무엇이든 잃지 않습니다.
    CSV로 정리하는 건 분석 단계에서 합니다.
  * 키는 파일에 저장하지 않습니다.
  * 끊겨도 다시 실행하면 이어받기 됩니다(.progress 파일).
  * 표준 라이브러리만 사용.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"

APIS = {
    "linked": ("[1] 2025 차량입출차, 공연, 날씨정보 등 연계 데이터",
               "https://api.kcisa.kr/openapi/API_CPM_009/request"),
    "inout": ("[2] 2025 입출차정보",
              "https://api.kcisa.kr/openapi/API_CPM_008/request"),
}
ROWS_PER_PAGE = 1000
PAUSE = 20.0           # 페이지 사이 쉬는 시간(초) - 429(요청 과다) 방지


def call(url, key, page, rows):
    q = urllib.parse.urlencode({"serviceKey": key, "numOfRows": rows, "pageNo": page})
    req = urllib.request.Request(f"{url}?{q}", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read().decode("utf-8", errors="replace")


def call_retry(url, key, page, rows):
    waits = [10, 30, 60, 120, 300, 600]
    for i, w in enumerate(waits + [None]):
        try:
            return call(url, key, page, rows)
        except Exception as e:
            if w is None:
                raise SystemExit(f"\n{page}페이지를 계속 실패했습니다({e}).\n"
                                 "잠시(30분 이상) 뒤 다시 실행하면 이어받습니다.")
            print(f"  {page}페이지 {e} → {w}초 쉬고 재시도")
            time.sleep(w)


def parse(body):
    """(전체건수, 행 목록) - JSON/XML 모두 처리, 행은 원본 칸 그대로."""
    body = body.strip()
    if body.startswith("{"):
        d = json.loads(body)
        resp = d.get("response", d)
        b = resp.get("body", {}) if isinstance(resp, dict) else {}
        items = b.get("items") or {}
        item = items.get("item", []) if isinstance(items, dict) else items
        if isinstance(item, dict):
            item = [item]
        return int(b.get("totalCount") or 0), item or []
    root = ET.fromstring(body)
    rows = [{c.tag: (c.text or "") for c in it} for it in root.iter("item")]
    return int(root.findtext(".//totalCount") or 0), rows


def ask_keys(names):
    keys, prev = {}, os.environ.get("KCISA_KEY", "")   # set_keys.bat에 저장하는 키 = 2025 입출차정보(API_CPM_008) 키
    for n in names:
        if os.environ.get("KCISA_KEY"):
            keys[n] = prev
            continue
        hint = " (앞과 같은 키면 그냥 Enter)" if prev else ""
        k = input(f"{APIS[n][0]} 의 서비스키를 붙여넣고 Enter{hint}: ").strip() or prev
        if not k:
            raise SystemExit("키가 비어 있습니다.")
        keys[n] = prev = k
    return keys


def probe(keys):
    """응답 모양 확인: API마다 2번만 호출하고 원본을 저장."""
    RAW.mkdir(parents=True, exist_ok=True)
    out = RAW / "kcisa_probe.txt"
    with open(out, "w", encoding="utf-8") as f:
        for n, (label, url) in APIS.items():
            for rows in (3, 5000):
                try:
                    body = call(url, keys[n], 1, rows)
                    total, items = parse(body)
                    f.write(f"### {n} numOfRows={rows}: total={total}, 받은행={len(items)}\n")
                    if rows == 3:
                        f.write(body.replace(keys[n], "***")[:6000] + "\n\n")
                except Exception as e:
                    f.write(f"### {n} numOfRows={rows}: 오류 {e}\n\n")
                time.sleep(3)
    print(f"확인 끝 → {out}\nClaude에게 '확인 끝났어'라고 알려주세요.")


SIZES = [5000, 2000, 1000, 200, 50, 10]   # 한 번에 받을 줄 수(큰 것부터 시도, 서버가 버거워하면 줄임)
SKIP_AFTER = 3        # 가장 작은 크기(10줄)로도 같은 자리에서 이만큼 연속 실패하면, 바로 다음 자리를 시험해 본다
SKIP_LIMIT = 2000     # 건너뛴 줄이 이보다 많아지면 멈추고 사람에게 알린다(데이터를 함부로 버리지 않게)


def fetch(name, key):
    """offset(지금까지 받은 줄 수) 기준으로 이어받기. 429면 쉬었다 같은 요청, 504면 크기 줄이기."""
    label, url = APIS[name]
    out = RAW / f"kcisa_{name}_2025.jsonl"
    off_file = out.with_name(out.name + ".offset")
    old_prog = out.with_name(out.name + ".progress")      # 예전 방식(1000줄 페이지 번호)
    if off_file.exists():
        offset = int(off_file.read_text())
    elif old_prog.exists():
        offset = int(old_prog.read_text()) * 1000
        off_file.write_text(str(offset))
        old_prog.unlink()
    else:
        offset = 0
        if out.exists():
            out.unlink()
    gap_file = out.with_name(out.name.replace(".jsonl", ".gaps.txt"))
    skipped = 0
    if gap_file.exists():
        for line in gap_file.read_text(encoding="utf-8").splitlines():
            if line and line[0].isdigit():
                a, b = line.split(",")[:2]
                skipped += int(b) - int(a)
    total = None
    size_i = 0
    fails_504 = 0
    stuck = 0          # 가장 작은 크기로 같은 자리에서 연속 실패한 횟수
    print(f"\n===== {label}: {offset:,}줄째부터 이어받기 =====")
    with open(out, "a", encoding="utf-8") as f:
        while total is None or offset < total:
            while offset % SIZES[size_i] != 0:     # 위치가 크기로 나눠떨어져야 페이지 계산 가능
                size_i += 1
            size = SIZES[size_i]
            page = offset // size + 1
            try:
                t, rows = parse(call(url, key, page, size))
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(30)
                    continue
                if e.code in (502, 503, 504) and size_i < len(SIZES) - 1:
                    size_i += 1
                    print(f"  서버가 느려서 한 번에 {SIZES[size_i]}줄로 줄입니다")
                    continue
                if e.code in (502, 503, 504):
                    stuck += 1
                    if stuck >= SKIP_AFTER:
                        # 이 10줄만 문제인지, 서버 전체가 멈췄는지 바로 다음 10줄로 시험
                        try:
                            parse(call(url, key, page + 1, size))
                            ok_next = True
                        except Exception:
                            ok_next = False
                        if ok_next:
                            if skipped + size > SKIP_LIMIT:
                                raise SystemExit(f"건너뛴 줄이 {SKIP_LIMIT:,}줄을 넘었어요. Claude에게 알려 주세요.")
                            if not gap_file.exists():
                                gap_file.write_text("# 서버 오류(502 등)로 받지 못하고 건너뛴 줄 (시작,끝,오류,시각)\n", encoding="utf-8")
                            with open(gap_file, "a", encoding="utf-8") as g:
                                g.write(f"{offset},{offset + size},{e.code},{time.strftime('%Y-%m-%d %H:%M')}\n")
                            skipped += size
                            print(f"  {offset + 1:,}~{offset + size:,}번째 줄만 서버가 계속 오류를 내요 → 이 {size}줄은 건너뛰고 기록해요 "
                                  f"(지금까지 건너뜀 {skipped:,}줄, {gap_file.name})")
                            offset += size
                            off_file.write_text(str(offset))
                            stuck = 0
                            fails_504 = 0
                            continue
                        print("  다음 자리도 오류예요 → 서버 전체 문제라서 기다려요")
                fails_504 += 1
                wait = min(600, 30 * fails_504)
                print(f"  {e} → {wait}초 쉬고 재시도")
                if fails_504 > 12:
                    raise SystemExit("서버가 계속 응답하지 않습니다. 30분 이상 뒤 다시 실행하면 이어받습니다.")
                time.sleep(wait)
                continue
            except Exception as e:
                fails_504 += 1
                print(f"  {e} → 30초 쉬고 재시도")
                if fails_504 > 12:
                    raise SystemExit("계속 실패합니다. 30분 이상 뒤 다시 실행하면 이어받습니다.")
                time.sleep(30)
                continue
            fails_504 = 0
            stuck = 0
            total = t or total
            if not rows:
                break
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            offset += len(rows)
            off_file.write_text(str(offset))
            pct = offset / total * 100 if total else 0
            print(f"  {offset:,} / {total:,}줄 ({pct:.1f}%)  [한 번에 {size}줄]  {time.strftime('%H:%M')}")
            if len(rows) < size:
                break
            # 잘 되면 다시 큰 크기로 올려 보기
            if size_i > 0 and offset % SIZES[size_i - 1] == 0:
                size_i -= 1
            time.sleep(PAUSE)
    off_file.unlink(missing_ok=True)
    print(f"완료 → {out}")
    if skipped:
        print(f"  서버 오류로 건너뛴 줄: {skipped:,}줄 (위치: {gap_file.name}). 분석할 때 이 숫자를 함께 밝혀요.")


def check_linked(key):
    """연계 데이터(API_CPM_009)에 실제 값이 들어있는 행이 있는지 앞·중간·끝 페이지로 확인."""
    url = APIS["linked"][1]
    out = RAW / "kcisa_probe2.txt"
    total, _ = parse(call_retry(url, key, 1, 3))
    pages = (total + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"linked total={total}\n")
        for pg in (1, pages // 2, pages):
            time.sleep(20)
            _, rows = parse(call_retry(url, key, pg, ROWS_PER_PAGE))
            filled = [r for r in rows if r.get("DESCRIPTION")]
            titles = sorted({str(r.get("TITLE")) for r in rows})
            f.write(f"\n### page {pg}: 행={len(rows)}, 내용있는행={len(filled)}\n")
            f.write("TITLE 예: " + " | ".join(titles[:5]) + "\n")
            f.write("칸 이름: " + ", ".join(sorted({k for r in rows for k in r})) + "\n")
            for r in filled[:3]:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"연계 데이터 확인 끝 → {out}")


def main():
    # 더블클릭 기본: 연계 데이터 확인(3번 요청) → 입출차 전체 받기
    args = sys.argv[1:] or ["inout"]          # 연계 데이터(CPM_009)는 값이 비어 있어 기본으로는 받지 않음
    valid = set(APIS) | {"probe", "check_linked"}
    if any(a not in valid for a in args):
        raise SystemExit("사용법: 03_fetch_kcisa_2025.py [probe | check_linked | linked | inout]")
    need = []
    for a in args:
        for n in (list(APIS) if a == "probe" else ["linked"] if a == "check_linked" else [a]):
            if n not in need:
                need.append(n)
    keys = ask_keys(need)
    for a in args:
        if a == "probe":
            probe(keys)
        elif a == "check_linked":
            if (RAW / "kcisa_probe2.txt").exists():
                print("연계 데이터 확인은 이미 했으므로 건너뜁니다.")
                continue
            try:
                check_linked(keys["linked"])
            except SystemExit as e:   # 연계 데이터 서버가 안 되면 건너뛰고 입출차로 진행
                print(f"연계 데이터 확인 실패 → 건너뜀 ({e})")
                (RAW / "kcisa_probe2.txt").write_text(f"실패: {e}\n", encoding="utf-8")
        else:
            fetch(a, keys[a])
    print("\n모두 끝났습니다. Claude에게 '다 받았어'라고 알려주세요.")


if __name__ == "__main__":
    main()
