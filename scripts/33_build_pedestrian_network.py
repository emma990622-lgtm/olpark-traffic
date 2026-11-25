"""
올림픽공원 및 주변 역 다층 보행 네트워크 GeoJSON 생성 스크립트.

통합 데이터(4종):
  1) 서울시 자치구별 도보 네트워크 공간정보 (data/raw/seoul_walknet_olpark.geojson, OA-21208):
     - 송파구·강동구 공식 보도·횡단보도(crswk)·육교(ovrp)·교량(brg)·공원 보행링크 반영
  2) 공원 내부 세밀 보행로 + 만남의광장~KSPO DOME '차도 위 보행로' (data/processed/osm_park_paths_raw.json):
     - 주인 현장 확인 반영: 올림픽공원역 만남의광장 ~ 상가동 북동측 광장 ~ KSPO DOME·핸드볼 앞 광장은
       계단식 육교가 아니라 아래로 차도(1230085700)가 지나가는 평평한 '차도 위 보행로'(level=1, 표고 약 20m)임.
     - 하부 차도(level=0, 표고 약 15.2m)와 상부 보행로(level=1) 노드를 분리해 평면 충돌 없이 입체 교차.
  3) 차도 겸용 보행 구간 (web/data/links.json, link_shapes.geojson + 공원 내부 차도):
     - 공원 내부 차도 등은 지상(level=0) 보행 가능 구간으로 연결(화면 문구에는 노출하지 않고 경로 계산에만 사용).
  4) 국토지리정보원 연속수치지형도 5m 등고선 (data/processed/vworld_contours_olpark.geojson):
     - 모든 보행 정점의 해발고도(elev_m)를 거리역산가중(IDW) 보간하여 간선별 시종점 표고(elevFrom, elevTo)와
       경사도(slopePct, %)를 산출 → 추후 도보경로에서 최단 경로와 완만한 길(언덕·계단 회피) 모두 탐색 가능.

출력:
  - web/data/pedestrian_overpass.geojson (지도 즉시 표시용 경량 레이어)
  - web/data/pedestrian_network.geojson  (다층·경사 반영 도보 경로 탐색 그래프)
"""
import heapq
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 보행 그래프 포함 범위 (올림픽공원 전체 + 주변 5개 역 + 외부 주차장)
WALKNET_BBOX = (127.108, 37.508, 127.140, 37.529)
# 차도 위 보행로(한얼광장 진입부) 입체 교차 중심점 — 반경 32m 안에서는 지상 자동 스냅 금지
UNDERPASS_CENTER = (127.12817, 37.51761)


def pt_dist_m(p1, p2):
    k = math.cos(math.radians((p1[1] + p2[1]) * 0.5))
    return math.hypot((p2[0] - p1[0]) * 111320.0 * k, (p2[1] - p1[1]) * 110540.0)


def project_point_to_seg(pt, a, b):
    k = math.cos(math.radians((a[1] + b[1]) * 0.5))
    px, py = pt[0] * k, pt[1]
    ax, ay = a[0] * k, a[1]
    bx, by = b[0] * k, b[1]
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    if denom < 1e-16:
        return [round(a[0], 6), round(a[1], 6)], pt_dist_m(pt, a)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denom))
    proj = [round(a[0] + t * (b[0] - a[0]), 6), round(a[1] + t * (b[1] - a[1]), 6)]
    return proj, pt_dist_m(pt, proj)


def seg_intersection_2d(p1, p2, p3, p4):
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4
    if max(x1, x2) < min(x3, x4) or max(x3, x4) < min(x1, x2):
        return None
    if max(y1, y2) < min(y3, y4) or max(y3, y4) < min(y1, y2):
        return None
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < 1e-15:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
    u = ((x1 - x3) * (y1 - y2) - (y1 - y3) * (x1 - x2)) / den
    if 0.001 < t < 0.999 and 0.001 < u < 0.999:
        return [round(x1 + t * (x2 - x1), 6), round(y1 + t * (y2 - y1), 6)]
    return None


def node_id(pt, lvl):
    # 약 1.8m 격자로 동일 층(level) 정점을 묶음 (level 0과 level 1은 절대 섞이지 않음)
    gx = round(pt[0] * 50000)
    gy = round(pt[1] * 50000)
    return f"L{int(lvl)}_{gx}_{gy}"


class ContourElevationModel:
    """5m 등고선 정점 격자 인덱스를 이용한 해발고도(m) 보간기."""
    def __init__(self, contour_geojson_path):
        self.cell = 0.0025  # 약 250m 격자
        self.grid = {}
        self.default_elev = 18.0
        if not contour_geojson_path.exists():
            return
        fc = json.loads(contour_geojson_path.read_text(encoding="utf-8"))
        for f in fc.get("features", []):
            p = f.get("properties", {})
            hg = p.get("ctrln_hg") if p.get("ctrln_hg") is not None else p.get("elev_m")
            if hg is None:
                continue
            elev = float(hg)
            geom = f["geometry"]
            parts = geom["coordinates"] if geom["type"] == "MultiLineString" else [geom["coordinates"]]
            for part in parts:
                last = None
                for pt in part:
                    if last is None or pt_dist_m(pt, last) >= 12.0:
                        gx = int(math.floor(pt[0] / self.cell))
                        gy = int(math.floor(pt[1] / self.cell))
                        self.grid.setdefault((gx, gy), []).append((pt[0], pt[1], elev))
                        last = pt

    def query(self, pt, level=0, is_upper_walkway=False, is_underpass_road=False):
        if is_upper_walkway:
            # 만남의광장~KSPO DOME 차도 위 보행로는 주변 상가동 등고선(20m)과 같은 평평한 지면 높이
            return 20.0
        if is_underpass_road and pt_dist_m(pt, UNDERPASS_CENTER) <= 40.0:
            # 상부 보행로 아래로 통과하는 공원 차도 굴다리 구간
            return 15.2
        if not self.grid:
            return self.default_elev

        gx = int(math.floor(pt[0] / self.cell))
        gy = int(math.floor(pt[1] / self.cell))
        cands = []
        for r in (1, 2, 4):
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    for cx, cy, ez in self.grid.get((gx + dx, gy + dy), ()):
                        cands.append((pt_dist_m(pt, (cx, cy)), ez))
            if len(cands) >= 8:
                break
        if not cands:
            return self.default_elev
        cands.sort(key=lambda x: x[0])
        top = cands[:8]
        if top[0][0] < 1.5:
            return round(top[0][1], 1)
        w_sum = 0.0
        z_sum = 0.0
        for d, ez in top:
            w = 1.0 / ((d + 4.0) ** 2)
            w_sum += w
            z_sum += w * ez
        return round(z_sum / w_sum, 1)


def main():
    osm_raw = json.loads((ROOT / "data/processed/osm_park_paths_raw.json").read_text(encoding="utf-8"))
    links = json.loads((ROOT / "web/data/links.json").read_text(encoding="utf-8"))
    shapes_fc = json.loads((ROOT / "web/data/link_shapes.geojson").read_text(encoding="utf-8"))
    shapes = {str(f["properties"]["id"]): f["geometry"]["coordinates"] for f in shapes_fc["features"]}
    places = json.loads((ROOT / "web/data/places.json").read_text(encoding="utf-8"))
    walk_t = json.loads((ROOT / "web/data/walk_tmap.json").read_text(encoding="utf-8"))
    elev_model = ContourElevationModel(ROOT / "data/processed/vworld_contours_olpark.geojson")

    walknet_path = ROOT / "data/raw/seoul_walknet_olpark.geojson"
    seoul_walknet = json.loads(walknet_path.read_text(encoding="utf-8")) if walknet_path.exists() else {"features": []}

    poly_features = []
    raw_polylines = []

    # ------------------------------------------------------------------
    # 1) 만남의광장(올림픽공원역) ~ 차도 위 보행로(level=1, 육교 아님) ~ KSPO DOME·핸드볼 광장
    # ------------------------------------------------------------------
    ne_se_plaza = [[127.130962, 37.516632], [127.128425, 37.517666]]
    ne_bridge = [[127.128425, 37.517666], [127.128049, 37.517819]]
    ne_nw_plaza = [
        [127.128049, 37.517819], [127.127969, 37.517913], [127.127813, 37.518011],
        [127.127765, 37.518066], [127.127668, 37.518202], [127.127556, 37.518376],
        [127.127416, 37.518415], [127.127116, 37.518419],
    ]
    sw_se_plaza = [[127.130747, 37.516309], [127.128301, 37.517406]]
    sw_bridge = [[127.128301, 37.517406], [127.127904, 37.517581]]
    sw_nw_plaza = [
        [127.127904, 37.517581], [127.127700, 37.517670], [127.127609, 37.517691],
        [127.127432, 37.517683], [127.127346, 37.517666], [127.127218, 37.517683],
        [127.127100, 37.517747], [127.126998, 37.517874], [127.126831, 37.517993],
    ]

    promenade_ring = (
        ne_se_plaza + [ne_bridge[1]] + ne_nw_plaza[1:]
        + list(reversed(sw_nw_plaza)) + [sw_se_plaza[0], ne_se_plaza[0]]
    )
    overpass_deck_ring = [
        [127.128425, 37.517666],
        [127.128049, 37.517819],
        [127.127904, 37.517581],
        [127.128301, 37.517406],
        [127.128425, 37.517666],
    ]

    poly_features.append({
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [promenade_ring]},
        "properties": {
            "id": "haneol_promenade_poly",
            "featureRole": "promenade",
            "kind": "overpass_walkway",
            "name": "만남의광장~KSPO DOME 보행로",
            "walkable": True,
            "vehicle": False,
            "gradeSeparated": True,
            "crossesOverRoadId": "1230085700",
            "note": "올림픽공원역 만남의광장에서 아래로 지나가는 차도 위를 평평하게 건너 KSPO DOME·핸드볼경기장 앞 광장으로 이어지는 보행자 전용 보행로",
        },
    })
    poly_features.append({
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [overpass_deck_ring]},
        "properties": {
            "id": "haneol_overpass_deck",
            "featureRole": "overpass_deck",
            "kind": "overpass_walkway",
            "name": "차도 위 보행로",
            "level": 1,
            "baseHeightM": 4.4,
            "topHeightM": 5.4,
            "walkable": True,
            "vehicle": False,
            "gradeSeparated": True,
            "crossesOverRoadId": "1230085700",
            "note": "아래로 공원 차도(1230085700)가 지나가고 위로는 평평한 보행로가 이어지는 입체 교차 구간(계단식 육교 아님)",
        },
    })

    center_se = [[127.130855, 37.516471], [127.129610, 37.517003], [127.128363, 37.517536]]
    center_bridge = [[127.128363, 37.517536], [127.127977, 37.517700]]
    center_nw = [[127.127977, 37.517700], [127.127476, 37.517955], [127.126976, 37.518210], [127.127116, 37.518419], [127.127450, 37.518680]]

    overpass_defs = [
        ("haneol_center_se", center_se, 0, 1, False, True, "만남의광장 보행로(동측)"),
        ("haneol_center_bridge", center_bridge, 1, 1, True, True, "차도 위 보행로(중앙)"),
        ("haneol_center_nw", center_nw, 1, 0, False, True, "한얼광장 보행로(KSPO DOME 앞)"),
        ("haneol_ne_se", ne_se_plaza, 0, 1, False, False, "만남의광장 북측 보행로"),
        ("haneol_ne_bridge", ne_bridge, 1, 1, True, False, "차도 위 보행로(북측)"),
        ("haneol_ne_nw", ne_nw_plaza, 1, 0, False, False, "KSPO DOME 남동 광장 보행로"),
        ("haneol_sw_se", sw_se_plaza, 0, 1, False, False, "만남의광장 남측 보행로"),
        ("haneol_sw_bridge", sw_bridge, 1, 1, True, False, "차도 위 보행로(남측)"),
        ("haneol_sw_nw", sw_nw_plaza, 1, 0, False, False, "핸드볼경기장 북측 광장 보행로"),
        ("haneol_tie_se", [[127.130962, 37.516632], [127.130855, 37.516471], [127.130747, 37.516309]], 0, 0, False, False, "만남의광장 진입 연결"),
        ("haneol_tie_nw", [[127.127116, 37.518419], [127.126976, 37.518210], [127.126831, 37.517993]], 0, 0, False, False, "한얼광장 분기 연결"),
        ("haneol_tie_br_e", [[127.128425, 37.517666], [127.128363, 37.517536], [127.128301, 37.517406]], 1, 1, True, False, "차도 위 보행로 동측 상판"),
        ("haneol_tie_br_w", [[127.128049, 37.517819], [127.127977, 37.517700], [127.127904, 37.517581]], 1, 1, True, False, "차도 위 보행로 서측 상판"),
    ]
    for eid, coords, l0, l1, is_br, is_main, label in overpass_defs:
        raw_polylines.append({
            "id": eid, "kind": "overpass_walkway", "name": label, "coords": coords,
            "l0": l0, "l1": l1, "bridge": is_br, "vehicle": False,
            "upperFlat": True,
            "extra": {
                "primaryCorridor": is_main,
                "crossesOverRoadId": "1230085700" if is_br else None,
                "footbridge": False,
                "crosswalk": False,
            },
        })

    skip_osm_ends = {
        ((127.128425, 37.517666), (127.130962, 37.516632)),
        ((127.128049, 37.517819), (127.128425, 37.517666)),
        ((127.127904, 37.517581), (127.128301, 37.517406)),
        ((127.128173, 37.517653), (127.126976, 37.518210)),
        ((127.126456, 37.518806), (127.128049, 37.517819)),
        ((127.127904, 37.517581), (127.125978, 37.518074)),
    }
    raw_polylines.append({
        "id": "haneol_ext_nw_ne", "kind": "footway", "name": "KSPO DOME 북서 광장 보행로",
        "coords": [[127.127116, 37.518419], [127.126939, 37.518470], [127.126767, 37.518547],
                   [127.126638, 37.518619], [127.126579, 37.518670], [127.126510, 37.518785], [127.126456, 37.518806]],
        "l0": 0, "l1": 0, "bridge": False, "vehicle": False, "upperFlat": True, "extra": {},
    })
    raw_polylines.append({
        "id": "haneol_ext_nw_sw", "kind": "footway", "name": "핸드볼경기장 북서 광장 보행로",
        "coords": [[127.126831, 37.517993], [127.126574, 37.518087], [127.126418, 37.518113],
                   [127.126209, 37.518113], [127.126113, 37.518104], [127.125978, 37.518074]],
        "l0": 0, "l1": 0, "bridge": False, "vehicle": False, "upperFlat": True, "extra": {},
    })

    # ------------------------------------------------------------------
    # 2) 서울시 도보 네트워크(OA-21208): 공식 보도·횡단보도·육교·교량 반영
    # ------------------------------------------------------------------
    w_minx, w_miny, w_maxx, w_maxy = WALKNET_BBOX
    seoul_added = 0
    for f in seoul_walknet.get("features", []):
        if f["geometry"]["type"] != "LineString":
            continue
        p = f.get("properties", {})
        if p.get("kind") != "link":
            continue
        cs = [[round(c[0], 6), round(c[1], 6)] for c in f["geometry"]["coordinates"]]
        if len(cs) < 2:
            continue
        if not any(w_minx <= x <= w_maxx and w_miny <= y <= w_maxy for x, y in cs):
            continue
        # 한얼광장 차도 위 보행로(127.12817, 37.51761) 바로 위를 평면(level=0)으로 가로지르는 선은
        # 이미 위 1번에서 입체(level=1)로 정확히 반영했으므로 하부 차도와 단락되지 않게 건너뜀
        if any(pt_dist_m(pt, UNDERPASS_CENTER) < 28.0 for pt in cs):
            continue

        is_ovrp = str(p.get("ovrp", "0")) == "1"
        is_crswk = str(p.get("crswk", "0")) == "1"
        is_brg = str(p.get("brg", "0")) == "1"
        lid = p.get("id")
        seoul_added += 1

        if is_ovrp:
            # 실제 도로 육교(계단 동반)는 하부 차도와 평면 교차하지 않도록 0->1->0 입체 분리
            mid = [round((cs[0][0] + cs[-1][0]) * 0.5, 6), round((cs[0][1] + cs[-1][1]) * 0.5, 6)]
            for sfx, seg, la, lb in (("a", [cs[0], mid], 0, 1), ("b", [mid, cs[-1]], 1, 0)):
                raw_polylines.append({
                    "id": f"sw_ovrp_{lid}_{sfx}", "kind": "footway", "name": "보행 육교(서울시 도보망)",
                    "coords": seg, "l0": la, "l1": lb, "bridge": True, "vehicle": False,
                    "upperFlat": False,
                    "extra": {"footbridge": True, "crosswalk": False, "source": "seoul_walknet"},
                })
        else:
            label = "횡단보도" if is_crswk else ("보행 교량" if is_brg else "보도(서울시 도보망)")
            raw_polylines.append({
                "id": f"sw_{lid}", "kind": "footway", "name": label,
                "coords": cs, "l0": 0, "l1": 0, "bridge": is_brg, "vehicle": False,
                "upperFlat": False,
                "extra": {
                    "footbridge": False,
                    "crosswalk": is_crswk,
                    "riverBridge": is_brg,
                    "source": "seoul_walknet",
                },
            })

    # ------------------------------------------------------------------
    # 3) 서울시 도로 58구간 (하부 차도 1230085700 등 지상 level=0 보행 가능 연결)
    # ------------------------------------------------------------------
    for lk in links:
        lid = str(lk["id"])
        raw_coords = shapes.get(lid) or [lk["a"], lk["b"]]
        coords = [[round(c[0], 6), round(c[1], 6)] for c in raw_coords]
        raw_polylines.append({
            "id": f"road_{lid}", "kind": "road_walkable",
            "name": f"{lk['road']} ({lk['from']}→{lk['to']})",
            "coords": coords, "l0": 0, "l1": 0, "bridge": False, "vehicle": True,
            "upperFlat": False,
            "isUnderpassRoad": lid == "1230085700",
            "extra": {"linkId": lid, "underpassBelow": "haneol_overpass_deck" if lid == "1230085700" else None},
        })

    # ------------------------------------------------------------------
    # 4) 공원 내부 세밀 산책로·광장길 및 공원 내부 차도 (OSM)
    # ------------------------------------------------------------------
    osm_idx = 0
    for item in osm_raw:
        p = item["props"]
        coords = item["coords"]
        if len(coords) < 2:
            continue
        cls = p.get("class", "")
        if cls in ("transit", "primary", "secondary", "trunk") or p.get("foot") == "no":
            continue
        ends = (tuple(coords[0]), tuple(coords[-1]))
        if ends in skip_osm_ends or (ends[1], ends[0]) in skip_osm_ends:
            continue
        if tuple(coords[0]) == (127.128301, 37.517406) and len(coords) >= 2 and tuple(coords[1]) == (127.130747, 37.516309):
            coords = coords[1:]
            if len(coords) < 2:
                continue
        is_bridge = p.get("brunnel") == "bridge"
        is_road = cls in ("service", "minor", "tertiary")
        if is_bridge and not is_road:
            mid = [round((coords[0][0] + coords[-1][0]) * 0.5, 6), round((coords[0][1] + coords[-1][1]) * 0.5, 6)]
            for sfx, seg, la, lb in (("a", [coords[0], mid], 0, 1), ("b", [mid, coords[-1]], 1, 0)):
                osm_idx += 1
                raw_polylines.append({
                    "id": f"osm_br_{osm_idx}_{sfx}", "kind": "overpass_walkway", "name": "공원 다리 보행로",
                    "coords": seg, "l0": la, "l1": lb, "bridge": True, "vehicle": False,
                    "upperFlat": False, "extra": {"primaryCorridor": False, "footbridge": False},
                })
            continue
        osm_idx += 1
        raw_polylines.append({
            "id": f"osm_{osm_idx}", "kind": "road_walkable" if is_road else "footway",
            "name": "공원 내부 길" if is_road else "공원 산책로",
            "coords": coords, "l0": 0, "l1": 0, "bridge": is_bridge, "vehicle": is_road,
            "upperFlat": False, "extra": {},
        })

    # ------------------------------------------------------------------
    # 5) 지상(level 0→0) 선분들의 평면 교차점 분할 (격자 인덱스로 고속 처리, level 1 상부 보행로는 분리 유지)
    # ------------------------------------------------------------------
    lvl0_segs = []
    seg_grid = {}
    gcell = 0.0015
    for pi, pl in enumerate(raw_polylines):
        if pl["l0"] == 0 and pl["l1"] == 0:
            cs = pl["coords"]
            for si in range(len(cs) - 1):
                a1, b1 = cs[si], cs[si + 1]
                idx = len(lvl0_segs)
                lvl0_segs.append((pi, si, a1, b1))
                gx0, gx1 = int(math.floor(min(a1[0], b1[0]) / gcell)), int(math.floor(max(a1[0], b1[0]) / gcell))
                gy0, gy1 = int(math.floor(min(a1[1], b1[1]) / gcell)), int(math.floor(max(a1[1], b1[1]) / gcell))
                for gx in range(gx0, gx1 + 1):
                    for gy in range(gy0, gy1 + 1):
                        seg_grid.setdefault((gx, gy), []).append(idx)

    splits = {}
    checked = set()
    for cell_idxs in seg_grid.values():
        n_c = len(cell_idxs)
        for i_a in range(n_c):
            idx1 = cell_idxs[i_a]
            pi1, si1, a1, b1 = lvl0_segs[idx1]
            for i_b in range(i_a + 1, n_c):
                idx2 = cell_idxs[i_b]
                pi2, si2, a2, b2 = lvl0_segs[idx2]
                if pi1 == pi2:
                    continue
                pair = (idx1, idx2) if idx1 < idx2 else (idx2, idx1)
                if pair in checked:
                    continue
                checked.add(pair)
                inter = seg_intersection_2d(a1, b1, a2, b2)
                if inter and pt_dist_m(inter, UNDERPASS_CENTER) > 28.0:
                    splits.setdefault((pi1, si1), []).append(inter)
                    splits.setdefault((pi2, si2), []).append(inter)

    for (pi, si), pts in sorted(splits.items(), key=lambda kv: (kv[0][0], -kv[0][1])):
        cs = raw_polylines[pi]["coords"]
        a = cs[si]
        pts_sorted = sorted(pts, key=lambda p: pt_dist_m(a, p))
        cs[si:si + 1] = [a] + pts_sorted

    # ------------------------------------------------------------------
    # 6) 단위 간선 전개 + 등고선 표고(elevFrom, elevTo)·경사도(slopePct) 산출
    # ------------------------------------------------------------------
    edge_features = []
    lvl0_nodes = {}
    node_elev_cache = {}
    snap_seg_grid = {}

    def get_elev(nid, pt, lvl, upper_flat=False, underpass_rd=False):
        key = (nid, upper_flat, underpass_rd)
        if key not in node_elev_cache:
            node_elev_cache[key] = elev_model.query(pt, level=lvl, is_upper_walkway=upper_flat, is_underpass_road=underpass_rd)
        return node_elev_cache[key]

    for pl in raw_polylines:
        cs = pl["coords"]
        l0, l1 = pl["l0"], pl["l1"]
        upper_flat = bool(pl.get("upperFlat"))
        under_rd = bool(pl.get("isUnderpassRoad"))
        nseg = len(cs) - 1
        for i in range(nseg):
            if l0 == l1:
                la = lb = l0
            elif l0 == 0 and l1 == 1:
                la = 0
                lb = 1 if i == nseg - 1 else 0
            else:
                la = 1 if i == 0 else 0
                lb = 0
            pa, pb = cs[i], cs[i + 1]
            m = pt_dist_m(pa, pb)
            if m < 0.05 and la == lb:
                continue
            u = node_id(pa, la)
            v = node_id(pb, lb)
            if la == 0:
                lvl0_nodes.setdefault(u, pa)
            if lb == 0:
                lvl0_nodes.setdefault(v, pb)
            if la == 0 and lb == 0:
                gx = int(math.floor((pa[0] + pb[0]) * 0.5 / gcell))
                gy = int(math.floor((pa[1] + pb[1]) * 0.5 / gcell))
                snap_seg_grid.setdefault((gx, gy), []).append((u, v, pa, pb))

            za = get_elev(u, pa, la, upper_flat=upper_flat, underpass_rd=under_rd)
            zb = get_elev(v, pb, lb, upper_flat=upper_flat, underpass_rd=under_rd)
            slope = round(abs(zb - za) / max(m, 5.0) * 100.0, 1)

            edge_features.append({
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [pa, pb]},
                "properties": {
                    "id": f"{pl['id']}_{i}",
                    "parentId": pl["id"],
                    "featureRole": "edge",
                    "kind": pl["kind"],
                    "name": pl["name"],
                    "u": u,
                    "v": v,
                    "fromLevel": la,
                    "toLevel": lb,
                    "bridge": pl["bridge"],
                    "walkable": True,
                    "vehicle": pl["vehicle"],
                    "meters": round(m, 1),
                    "elevFrom": za,
                    "elevTo": zb,
                    "slopePct": slope,
                    **pl["extra"],
                },
            })

    # 지상(level=0) 보도(서울시 도보망 ↔ 공원 보행로 ↔ 차도) 인접 끝점 연결(16m 이내, 입체교차 굴다리 주변 제외)
    seen_pairs = {(f["properties"]["u"], f["properties"]["v"]) for f in edge_features}
    snap_cnt = 0
    for nid, pt in list(lvl0_nodes.items()):
        if pt_dist_m(pt, UNDERPASS_CENTER) <= 32.0:
            continue
        gx = int(math.floor(pt[0] / gcell))
        gy = int(math.floor(pt[1] / gcell))
        best = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for u, v, pa, pb in snap_seg_grid.get((gx + dx, gy + dy), ()):
                    if nid == u or nid == v:
                        continue
                    proj, d = project_point_to_seg(pt, pa, pb)
                    if 0.3 < d <= 16.0 and (best is None or d < best[0]):
                        target_nid = u if pt_dist_m(proj, pa) <= pt_dist_m(proj, pb) else v
                        target_pt = pa if target_nid == u else pb
                        if pt_dist_m(target_pt, UNDERPASS_CENTER) <= 32.0:
                            continue
                        td = pt_dist_m(pt, target_pt)
                        if td <= 22.0:
                            best = (d, target_nid, target_pt, td)
        if best:
            _, t_nid, t_pt, td = best
            if (nid, t_nid) not in seen_pairs and (t_nid, nid) not in seen_pairs:
                seen_pairs.add((nid, t_nid))
                snap_cnt += 1
                za = get_elev(nid, pt, 0)
                zb = get_elev(t_nid, t_pt, 0)
                edge_features.append({
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": [pt, t_pt]},
                    "properties": {
                        "id": f"junction_{snap_cnt}",
                        "featureRole": "edge",
                        "kind": "connector",
                        "name": "보도 연결",
                        "u": nid,
                        "v": t_nid,
                        "fromLevel": 0,
                        "toLevel": 0,
                        "bridge": False,
                        "walkable": True,
                        "vehicle": False,
                        "meters": round(td, 1),
                        "elevFrom": za,
                        "elevTo": zb,
                        "slopePct": round(abs(zb - za) / max(td, 5.0) * 100.0, 1),
                    },
                })

    # ------------------------------------------------------------------
    # 7) 역·주차장·공연장 기준점 연결
    # ------------------------------------------------------------------
    anchors = []
    for s in places["stations"]:
        anchors.append(("station", s["name"], [round(s["lng"], 6), round(s["lat"], 6)]))
    for lot in places["lots"]:
        if lot.get("lat") and lot.get("kind") != "transfer":
            anchors.append(("lot", lot["name"], [round(lot["lng"], 6), round(lot["lat"], 6)]))
    for vname, v in walk_t.get("venues", {}).items():
        if vname == "뮤즈라이브":
            continue
        anchors.append(("venue", vname, [round(v["lng"], 6), round(v["lat"], 6)]))

    anchor_nodes = {}
    for idx, (akind, aname, pt) in enumerate(anchors, 1):
        anid = f"ANCHOR_{akind}_{aname}"
        anchor_nodes[aname] = (anid, pt)
        cands = sorted(
            ((pt_dist_m(pt, npt), nid, npt) for nid, npt in lvl0_nodes.items()
             if pt_dist_m(npt, UNDERPASS_CENTER) > 28.0),
            key=lambda x: x[0],
        )
        picked = []
        for d, nid, npt in cands:
            if d > 130.0 and picked:
                break
            if all(pt_dist_m(npt, p[2]) >= 22.0 for p in picked):
                picked.append((d, nid, npt))
            if len(picked) >= 6:
                break
        za = elev_model.query(pt)
        for k_i, (d, nid, npt) in enumerate(picked, 1):
            zb = get_elev(nid, npt, 0)
            edge_features.append({
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [pt, npt]},
                "properties": {
                    "id": f"anchor_{idx}_{k_i}",
                    "featureRole": "edge",
                    "kind": "connector",
                    "anchorKind": akind,
                    "anchorName": aname,
                    "name": f"{aname} 진입 연결",
                    "u": anid,
                    "v": nid,
                    "fromLevel": 0,
                    "toLevel": 0,
                    "bridge": False,
                    "walkable": True,
                    "vehicle": False,
                    "meters": round(d, 1),
                    "elevFrom": za,
                    "elevTo": zb,
                    "slopePct": 0.0,
                },
            })

    # ------------------------------------------------------------------
    # 8) 분기 없는 중간 정점(degree=2, 동일 속성·동일 층) 병합 → 파일 경량화
    # ------------------------------------------------------------------
    deg = {}
    for f in edge_features:
        p = f["properties"]
        deg[p["u"]] = deg.get(p["u"], 0) + 1
        deg[p["v"]] = deg.get(p["v"], 0) + 1

    by_parent = {}
    standalones = []
    for f in edge_features:
        pid = f["properties"].get("parentId")
        if pid:
            by_parent.setdefault(pid, []).append(f)
        else:
            standalones.append(f)

    compact_edges = []
    for pid, segs in by_parent.items():
        cur = None
        for s in segs:
            sp = s["properties"]
            sc = s["geometry"]["coordinates"]
            if cur is None:
                cur = {
                    "coords": [sc[0], sc[1]],
                    "props": {k: v for k, v in sp.items() if k != "parentId"},
                }
            else:
                cp = cur["props"]
                mid_node = cp["v"]
                can_join = (
                    mid_node == sp["u"]
                    and deg.get(mid_node, 0) == 2
                    and not mid_node.startswith("ANCHOR_")
                    and cp["fromLevel"] == cp["toLevel"] == sp["fromLevel"] == sp["toLevel"]
                    and cp["kind"] == sp["kind"]
                    and cp["bridge"] == sp["bridge"]
                    and bool(cp.get("crosswalk")) == bool(sp.get("crosswalk"))
                    and bool(cp.get("footbridge")) == bool(sp.get("footbridge"))
                )
                if can_join:
                    cur["coords"].append(sc[1])
                    cp["v"] = sp["v"]
                    cp["meters"] = round(cp["meters"] + sp["meters"], 1)
                    cp["elevTo"] = sp["elevTo"]
                    cp["slopePct"] = max(cp.get("slopePct", 0.0), sp.get("slopePct", 0.0))
                else:
                    compact_edges.append({
                        "type": "Feature",
                        "geometry": {"type": "LineString", "coordinates": cur["coords"]},
                        "properties": cur["props"],
                    })
                    cur = {
                        "coords": [sc[0], sc[1]],
                        "props": {k: v for k, v in sp.items() if k != "parentId"},
                    }
        if cur is not None:
            compact_edges.append({
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": cur["coords"]},
                "properties": cur["props"],
            })
    compact_edges.extend(standalones)

    # 기본값(False/None/일반 보도명) 제거로 네트워크 파일 경량화
    default_names = {"보도(서울시 도보망)", "공원 산책로", "보도 연결"}
    for f in compact_edges:
        p = f["properties"]
        is_haneol = str(p.get("id", "")).startswith("haneol_")
        cleaned = {}
        for k, v in p.items():
            if v is None or v is False:
                if is_haneol and k in ("bridge", "primaryCorridor"):
                    cleaned[k] = False
                continue
            if k == "source":
                continue
            if k == "name" and v in default_names and not is_haneol:
                continue
            cleaned[k] = v
        f["properties"] = cleaned

    edge_features = compact_edges

    kst = timezone(timedelta(hours=9))
    features = poly_features + edge_features
    out = {
        "type": "FeatureCollection",
        "metadata": {
            "built": datetime.now(kst).strftime("%Y-%m-%d"),
            "description": "올림픽공원·주변 역 통합 다층 보행 네트워크 — 서울시 도보 네트워크(OA-21208) + 공원 세밀 보행로 + 만남의광장~KSPO DOME 차도 위 보행로(level=1) + 연속수치지형도 5m 등고선 표고·경사 반영",
            "walkSpeedMPerMin": 75,
            "sources": [
                "서울시 자치구별 도보 네트워크 공간정보(OA-21208)",
                "국토교통부 연속수치지형도 등고선(5m 간격 표고)",
                "OpenStreetMap 공원 내부 보행로 및 현장 확인 차도 위 보행로",
                "서울시 실시간 도시데이터 도로 구간 형상",
            ],
            "rules": {
                "allRoadsWalkable": True,
                "gradeSeparatedLevels": [0, 1],
                "upperWalkwayCorridor": "올림픽공원역 만남의광장 ↔ 차도 위 보행로(level=1, 육교 아님) ↔ KSPO DOME·핸드볼경기장 광장",
            },
        },
        "features": features,
    }
    out_path = ROOT / "web/data/pedestrian_network.geojson"
    out_path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    overpass_vis = {
        "type": "FeatureCollection",
        "metadata": out["metadata"],
        "features": poly_features + [
            f for f in edge_features
            if f["properties"].get("kind") == "overpass_walkway"
            and str(f["properties"].get("id", "")).startswith("haneol_")
        ],
    }
    vis_path = ROOT / "web/data/pedestrian_overpass.geojson"
    vis_path.write_text(json.dumps(overpass_vis, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # 경로 및 입체 분리 검증 (전용 보도 우선 가중치 1.12 on 차도, 완만한 길 옵션 검증)
    adj = {}
    for f in edge_features:
        p = f["properties"]
        u, v, w = p["u"], p["v"], float(p["meters"])
        sl = float(p.get("slopePct") or 0.0)
        veh = bool(p.get("vehicle"))
        fb = bool(p.get("footbridge"))
        adj.setdefault(u, []).append((v, w, p["kind"], bool(p.get("bridge")), sl, bool(p.get("crosswalk")), veh, fb))
        adj.setdefault(v, []).append((u, w, p["kind"], bool(p.get("bridge")), sl, bool(p.get("crosswalk")), veh, fb))

    def dijkstra(su, tu, gentle=False):
        pq = [(0.0, 0.0, su, False, 0.0, 0)]
        best = {su: 0.0}
        while pq:
            cost, real_d, u, used_up, max_sl, cw_cnt = heapq.heappop(pq)
            if u == tu:
                return round(real_d), max(1, round(real_d / 75.0)), used_up, round(max_sl, 1), cw_cnt
            if cost > best.get(u, 1e18):
                continue
            for v, w, kind, is_br, sl, is_cw, veh, fb in adj.get(u, []):
                mult = 1.12 if veh else 1.0
                if gentle:
                    if fb:
                        mult += 1.5
                    if sl >= 8.0:
                        mult += (sl - 6.0) * 0.18
                    elif sl >= 4.0:
                        mult += (sl - 4.0) * 0.05
                ncost = cost + w * mult
                if ncost < best.get(v, 1e18):
                    best[v] = ncost
                    heapq.heappush(pq, (
                        ncost, real_d + w, v,
                        used_up or (kind == "overpass_walkway" and is_br),
                        max(max_sl, sl),
                        cw_cnt + (1 if is_cw else 0),
                    ))
        return None

    sz_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"저장 완료 → {out_path} (서울시 링크 {seoul_added:,}개 통합, 최종 간선 {len(edge_features):,}개, {sz_mb:.2f} MB)")
    for st in ("올림픽공원역", "몽촌토성역", "한성백제역", "올림픽공원 주차장(동2문·남2문·북2문)"):
        for vn in ("KSPO DOME", "핸드볼경기장", "우리금융아트홀", "올림픽홀"):
            r = dijkstra(anchor_nodes[st][0], anchor_nodes[vn][0], gentle=False)
            rg = dijkstra(anchor_nodes[st][0], anchor_nodes[vn][0], gentle=True)
            if r:
                extra = f" | 완만={rg[0]}m(최대경사 {rg[3]}%)" if rg and rg[3] < r[3] else ""
                print(f"  {st} -> {vn}: {r[0]}m · 약 {r[1]}분 (차도위보행로={r[2]}, 최대경사={r[3]}%, 횡단보도={r[4]}회){extra}")


if __name__ == "__main__":
    main()
