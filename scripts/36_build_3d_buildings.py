"""
브이월드 GIS건물통합정보(data/processed/vworld_buildings_olpark.geojson)에서
3D 지도(web/assets/map3d.js)가 API 호출 없이 즉시 그릴 수 있는 경량 정적 건물 파일 생성.

처리 원칙:
  1) 지도 표시 범위(127.105~127.140, 37.505~37.528 — 기존 api/buildings.js와 동일) 안의 건물 추출
  2) 실측 건물 높이(A16, m)가 있으면 우선 사용하고, 0·결측인 경우 지상층수(A26) × 3.3m(최소 3.3m)로 보완
  3) 데이터 함정 보정(방이동 88 단일 필지 매칭 오류):
     올림픽공원 전체가 '방이동 88' 단일 필지여서 국토교통부 GIS건물통합정보 자동 매칭 과정에서
     건축물대장 표제부 동명·높이(체조경기장 34.55m, 핸드볼 21.58m, 역도경기장 22.7m 등)가
     실제 경기장 도형끼리 뒤바뀌어 붙어 있음 → 실제 공연장 좌표 기준으로 높이·이름을 바로잡음.
  4) 모바일(360px) 로딩 속도를 위해 불필요한 필지·대장 속성은 빼고 {height, floors, name}만 남김.

출력: web/data/buildings_3d.geojson
"""
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IN_PATH = ROOT / "data" / "processed" / "vworld_buildings_olpark.geojson"
OUT_PATH = ROOT / "web" / "data" / "buildings_3d.geojson"

# 기존 api/buildings.js와 동일한 표시 범위
BOX = (127.105, 37.505, 127.140, 37.528)

# 방이동 88 단일 필지 내 주요 시설 실제 위치·건축물대장 높이 보정표
# (경도, 위도, 반경m, 실제 이름, 실제 높이m, 층수)
PARK_VENUE_FIXES = [
    (127.12741, 37.51921, 45.0, "KSPO DOME", 34.6, 3),         # 건축물대장 '체조경기장' A16=34.55m
    (127.12632, 37.51738, 40.0, "핸드볼경기장", 21.6, 3),        # 건축물대장 'SK 올림픽 핸드볼 경기장' A16=21.58m
    (127.12504, 37.51675, 35.0, "우리금융아트홀", 22.7, 3),      # 건축물대장 '역도경기장' A16=22.7m
    (127.12754, 37.51471, 35.0, "올림픽홀", 21.0, 3),            # 올림픽홀 본관 (A16=0 결측 보정)
    (127.12844, 37.51539, 40.0, "올림픽테니스장", 31.2, 2),      # 센터코트 A16=31.2m
    (127.12328, 37.51687, 45.0, "올림픽벨로드롬", 20.0, 2),      # 자전거경기장 (체조경기장 값 오매칭 보정)
    (127.12659, 37.52098, 45.0, "올림픽수영장", 36.8, 3),        # 수영경기장 A16=36.798m
    (127.12624, 37.51401, 45.0, "소마미술관", 15.0, 2),          # 역도경기장 값 오매칭 보정
]


def clean_str(v):
    if v is None:
        return ""
    return str(v).replace("\x00", "").strip()


def fnum(v):
    s = clean_str(v)
    if not s:
        return 0.0
    try:
        x = float(s)
        return x if math.isfinite(x) else 0.0
    except ValueError:
        return 0.0


def dist_m(lng1, lat1, lng2, lat2):
    k = math.cos(math.radians((lat1 + lat2) * 0.5))
    return math.hypot((lng2 - lng1) * 111320.0 * k, (lat2 - lat1) * 110540.0)


def simplify_ring(ring, prec=5):
    """소수점 5자리(약 1.1m) 반올림 및 연속 중복 정점 제거."""
    pts = []
    for c in ring:
        pt = [round(c[0], prec), round(c[1], prec)]
        if not pts or pt != pts[-1]:
            pts.append(pt)
    if len(pts) >= 3 and pts[0] != pts[-1]:
        pts.append(pts[0])
    return pts if len(pts) >= 4 else None


def simplify_geom(geom, prec=5):
    gtype = geom["type"]
    if gtype == "Polygon":
        rings = [simplify_ring(r, prec) for r in geom["coordinates"]]
        rings = [r for r in rings if r]
        return {"type": "Polygon", "coordinates": rings} if rings else None
    if gtype == "MultiPolygon":
        polys = []
        for poly in geom["coordinates"]:
            rings = [simplify_ring(r, prec) for r in poly]
            rings = [r for r in rings if r]
            if rings:
                polys.append(rings)
        if not polys:
            return None
        if len(polys) == 1:
            return {"type": "Polygon", "coordinates": polys[0]}
        return {"type": "MultiPolygon", "coordinates": polys}
    return None


def outer_centroid_and_span(geom):
    ring = geom["coordinates"][0]
    if geom["type"] == "MultiPolygon":
        ring = ring[0]
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    cx = sum(xs) / len(xs)
    cy = sum(ys) / len(ys)
    w_m = (max(xs) - min(xs)) * 88800.0
    h_m = (max(ys) - min(ys)) * 110540.0
    return cx, cy, max(w_m, h_m)


def main():
    src = json.loads(IN_PATH.read_text(encoding="utf-8"))
    min_lon, min_lat, max_lon, max_lat = BOX

    out_features = []
    measured_cnt = 0
    floor_est_cnt = 0
    fixed_venues = []

    for f in src.get("features", []):
        geom = simplify_geom(f["geometry"], prec=5)
        if not geom:
            continue
        cx, cy, span_m = outer_centroid_and_span(geom)
        if not (min_lon <= cx <= max_lon and min_lat <= cy <= max_lat):
            continue

        p = f.get("properties", {})
        h_m = fnum(p.get("height_m") or p.get("A16"))
        fl = int(round(fnum(p.get("floors") or p.get("A26"))))
        nm = clean_str(p.get("A24"))
        dong = clean_str(p.get("A25"))
        label = nm or dong

        # 방이동 88 대형 경기장 오매칭 보정 (폭 50m 이상 주 건물에만 적용)
        venue_fixed = False
        if span_m >= 50.0:
            for vx, vy, rad, vname, vh, vfl in PARK_VENUE_FIXES:
                if dist_m(cx, cy, vx, vy) <= rad:
                    h_m = vh
                    fl = vfl
                    label = vname
                    venue_fixed = True
                    fixed_venues.append(f"{vname}({vh}m)")
                    break

        if h_m > 0:
            height = round(h_m, 1)
            if not venue_fixed:
                measured_cnt += 1
        elif fl > 0:
            height = round(max(3.3, fl * 3.3), 1)
            floor_est_cnt += 1
        else:
            height = 5.0
            floor_est_cnt += 1

        props = {"height": height}
        if fl > 0:
            props["floors"] = fl
        if label:
            props["name"] = label

        out_features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": props,
        })

    kst = timezone(timedelta(hours=9))
    payload = {
        "type": "FeatureCollection",
        "meta": {
            "built": datetime.now(kst).strftime("%Y-%m-%d"),
            "source": "국토교통부 브이월드 GIS건물통합정보(AL_D010_11_20261109, EPSG:5186→WGS84)",
            "box": list(BOX),
            "count": len(out_features),
            "measuredHeightCount": measured_cnt + len(fixed_venues),
            "floorEstimatedCount": floor_est_cnt,
            "parkSingleLotFixed": fixed_venues,
        },
        "features": out_features,
    }
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    sz_mb = OUT_PATH.stat().st_size / (1024 * 1024)
    print(f"저장 완료 → {OUT_PATH} ({len(out_features):,}동, {sz_mb:.2f} MB)")
    print(f"  실측 높이(A16): {measured_cnt + len(fixed_venues):,}동 / 층수 환산 보완: {floor_est_cnt:,}동")
    print(f"  방이동 88 경기장 보정: {', '.join(fixed_venues)}")

    # 원본 가공본(vworld_buildings_olpark.geojson)에 섞인 DBF 널 패딩(\x00)도 함께 정리
    raw_txt = IN_PATH.read_text(encoding="utf-8")
    if "\\u0000" in raw_txt or "\x00" in raw_txt:
        for f in src.get("features", []):
            p = f.get("properties", {})
            cleaned_p = {}
            for k, v in p.items():
                if isinstance(v, str):
                    sv = v.replace("\x00", "").strip()
                    if not sv:
                        continue
                    cleaned_p[k] = sv
                else:
                    cleaned_p[k] = v
            f["properties"] = cleaned_p
        IN_PATH.write_text(json.dumps(src, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"  가공본 널 문자 정리 완료 → {IN_PATH} ({IN_PATH.stat().st_size / (1024 * 1024):.2f} MB)")

    # 3D 지도 등고선 표시용 경량 5m 등고선(web/data/contours_5m.geojson) 생성
    cont_in = ROOT / "data" / "processed" / "vworld_contours_olpark.geojson"
    cont_out = ROOT / "web" / "data" / "contours_5m.geojson"
    if cont_in.exists():
        cfc = json.loads(cont_in.read_text(encoding="utf-8"))
        c_feats = []
        for f in cfc.get("features", []):
            p = f.get("properties", {})
            elev = fnum(p.get("ctrln_hg") if p.get("ctrln_hg") is not None else p.get("elev_m"))
            if elev <= 0:
                continue
            g = f["geometry"]
            parts = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
            out_parts = []
            for part in parts:
                pts = []
                for c in part:
                    if not (min_lon <= c[0] <= max_lon and min_lat <= c[1] <= max_lat):
                        if len(pts) >= 2:
                            out_parts.append(pts)
                        pts = []
                        continue
                    pt = [round(c[0], 5), round(c[1], 5)]
                    if not pts or pt != pts[-1]:
                        pts.append(pt)
                if len(pts) >= 2:
                    out_parts.append(pts)
            if not out_parts:
                continue
            geom_out = (
                {"type": "LineString", "coordinates": out_parts[0]}
                if len(out_parts) == 1
                else {"type": "MultiLineString", "coordinates": out_parts}
            )
            c_feats.append({
                "type": "Feature",
                "geometry": geom_out,
                "properties": {"elev": int(round(elev)), "major": int(round(elev)) % 25 == 0},
            })
        cont_payload = {
            "type": "FeatureCollection",
            "meta": {
                "built": datetime.now(kst).strftime("%Y-%m-%d"),
                "source": "국토교통부 연속수치지형도 등고선(5m 간격, EPSG:5179→WGS84)",
                "box": list(BOX),
                "count": len(c_feats),
            },
            "features": c_feats,
        }
        cont_out.write_text(json.dumps(cont_payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"저장 완료 → {cont_out} ({len(c_feats):,}개, {cont_out.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
