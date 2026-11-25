"""
올림픽공원 보행 네트워크(인도·고가 보행육교 + 보행 가능 차도) GeoJSON 생성 스크립트.

핵심 구조:
  1) 차도 겸 보행로 (kind='road_walkable', level 0→0, walkable=True, vehicle=True):
     - 올림픽공원 내부 차도 및 둘레 도로(58개 링크 포함)는 기본적으로 모두 보행자가 걸을 수 있다.
     - 특히 1230085700(남2문·동2문 분기 ~ 북2문 방향 공원 내부 차도)은 보행육교 아래(level=0)로 지나간다.
  2) 차도 위 입체 보행 인도·육교 (kind='overpass_walkway', walkable=True, vehicle=False):
     - 올림픽공원역(3·4번 출구 만남의광장) ↔ 상가동 북동측 보행광장 ↔ 차도 위 보행육교(level=1) ↔ KSPO DOME·핸드볼경기장 앞 광장.
     - 육교 본체 구간은 fromLevel=1, toLevel=1 이고 양쪽 광장 진입부는 0→1 / 1→0 으로 연결되어,
       도보 경로 탐색 시 (경도, 위도, 층 level) 그래프에서 하부 차도(level=0)와 평면 충돌하지 않고 입체 교차한다.
  3) 공원 일반 보행로 (kind='footway', level 0→0, walkable=True, vehicle=False):
     - 공원 안 보행자 전용 산책로·광장 동선 및 공연장·역·주차장 진입 연결선.

입력: data/processed/osm_park_paths_raw.json, web/data/links.json, web/data/link_shapes.geojson,
      web/data/places.json, web/data/walk_tmap.json
출력: web/data/pedestrian_network.geojson
"""
import heapq
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def pt_dist_m(p1, p2):
    k = math.cos(math.radians((p1[1] + p2[1]) * 0.5))
    return math.hypot((p2[0] - p1[0]) * 111320.0 * k, (p2[1] - p1[1]) * 110540.0)


def seg_meters(coords):
    return round(sum(pt_dist_m(a, b) for a, b in zip(coords, coords[1:])), 1)


def project_point_to_seg(pt, a, b):
    """점 pt에서 선분 a-b에 내린 수선의 발 (투영점, 거리 m)."""
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
    """두 선분 (p1-p2), (p3-p4)가 내부에서 교차하면 교차점 [lng, lat] 반환."""
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
    # 약 1.5m 격자로 동일 층(level) 정점을 묶음 (level 0과 level 1은 절대 섞이지 않음)
    gx = round(pt[0] * 60000)
    gy = round(pt[1] * 60000)
    return f"L{int(lvl)}_{gx}_{gy}"


def main():
    osm_raw = json.loads((ROOT / "data/processed/osm_park_paths_raw.json").read_text(encoding="utf-8"))
    links = json.loads((ROOT / "web/data/links.json").read_text(encoding="utf-8"))
    shapes_fc = json.loads((ROOT / "web/data/link_shapes.geojson").read_text(encoding="utf-8"))
    shapes = {str(f["properties"]["id"]): f["geometry"]["coordinates"] for f in shapes_fc["features"]}
    places = json.loads((ROOT / "web/data/places.json").read_text(encoding="utf-8"))
    walk_t = json.loads((ROOT / "web/data/walk_tmap.json").read_text(encoding="utf-8"))

    poly_features = []
    raw_polylines = []  # list of dicts: id, kind, name, coords, l0, l1, bridge, vehicle, extra

    # ------------------------------------------------------------------
    # 1) 만남의광장(올림픽공원역) ~ 차도 위 육교(level=1) ~ KSPO DOME·핸드볼 광장 인도
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
            "name": "만남의광장~KSPO DOME 보행 인도",
            "walkable": True,
            "vehicle": False,
            "gradeSeparated": True,
            "crossesOverRoadId": "1230085700",
            "note": "올림픽공원역 만남의광장에서 하부 차도 위로 지나 KSPO DOME·핸드볼경기장 앞 광장으로 이어지는 보행자 전용 인도",
        },
    })
    poly_features.append({
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [overpass_deck_ring]},
        "properties": {
            "id": "haneol_overpass_deck",
            "featureRole": "overpass_deck",
            "kind": "overpass_walkway",
            "name": "차도 위 보행 육교(인도)",
            "level": 1,
            "baseHeightM": 4.4,
            "topHeightM": 5.4,
            "walkable": True,
            "vehicle": False,
            "gradeSeparated": True,
            "crossesOverRoadId": "1230085700",
            "note": "하부 공원 차도(1230085700, 보행 가능) 위로 보행자 인도가 입체 교차하는 구간",
        },
    })

    center_se = [[127.130855, 37.516471], [127.129610, 37.517003], [127.128363, 37.517536]]
    center_bridge = [[127.128363, 37.517536], [127.127977, 37.517700]]
    center_nw = [[127.127977, 37.517700], [127.127476, 37.517955], [127.126976, 37.518210], [127.127116, 37.518419], [127.127450, 37.518680]]

    overpass_defs = [
        ("haneol_center_se", center_se, 0, 1, False, True, "만남의광장 보행 인도(동측 진입)"),
        ("haneol_center_bridge", center_bridge, 1, 1, True, True, "차도 위 보행 육교(중앙)"),
        ("haneol_center_nw", center_nw, 1, 0, False, True, "한얼광장 보행 인도(KSPO DOME 앞)"),
        ("haneol_ne_se", ne_se_plaza, 0, 1, False, False, "만남의광장 북측 인도"),
        ("haneol_ne_bridge", ne_bridge, 1, 1, True, False, "차도 위 보행 육교(북측)"),
        ("haneol_ne_nw", ne_nw_plaza, 1, 0, False, False, "KSPO DOME 남동 광장 인도"),
        ("haneol_sw_se", sw_se_plaza, 0, 1, False, False, "만남의광장 남측 인도"),
        ("haneol_sw_bridge", sw_bridge, 1, 1, True, False, "차도 위 보행 육교(남측)"),
        ("haneol_sw_nw", sw_nw_plaza, 1, 0, False, False, "핸드볼경기장 북측 광장 인도"),
        ("haneol_tie_se", [[127.130962, 37.516632], [127.130855, 37.516471], [127.130747, 37.516309]], 0, 0, False, False, "만남의광장 진입 연결"),
        ("haneol_tie_nw", [[127.127116, 37.518419], [127.126976, 37.518210], [127.126831, 37.517993]], 0, 0, False, False, "한얼광장 분기 연결"),
        # 육교 위(level=1) 좌우 횡단 연결(넓은 일체형 데크 광장 표현)
        ("haneol_tie_br_e", [[127.128425, 37.517666], [127.128363, 37.517536], [127.128301, 37.517406]], 1, 1, True, False, "보행 육교 동측 데크"),
        ("haneol_tie_br_w", [[127.128049, 37.517819], [127.127977, 37.517700], [127.127904, 37.517581]], 1, 1, True, False, "보행 육교 서측 데크"),
    ]
    for eid, coords, l0, l1, is_br, is_main, label in overpass_defs:
        raw_polylines.append({
            "id": eid, "kind": "overpass_walkway", "name": label, "coords": coords,
            "l0": l0, "l1": l1, "bridge": is_br, "vehicle": False,
            "extra": {"primaryCorridor": is_main, "crossesOverRoadId": "1230085700" if is_br else None},
        })

    skip_osm_ends = {
        ((127.128425, 37.517666), (127.130962, 37.516632)),
        ((127.128049, 37.517819), (127.128425, 37.517666)),
        ((127.127904, 37.517581), (127.128301, 37.517406)),
        ((127.128173, 37.517653), (127.126976, 37.518210)),
        ((127.126456, 37.518806), (127.128049, 37.517819)),
        ((127.127904, 37.517581), (127.125978, 37.518074)),
    }
    # [21]·[11]의 한얼광장 서쪽 연장부(level 0→0)도 그대로 보존
    raw_polylines.append({
        "id": "haneol_ext_nw_ne", "kind": "footway", "name": "KSPO DOME 북서 광장 인도",
        "coords": [[127.127116, 37.518419], [127.126939, 37.518470], [127.126767, 37.518547],
                   [127.126638, 37.518619], [127.126579, 37.518670], [127.126510, 37.518785], [127.126456, 37.518806]],
        "l0": 0, "l1": 0, "bridge": False, "vehicle": False, "extra": {},
    })
    raw_polylines.append({
        "id": "haneol_ext_nw_sw", "kind": "footway", "name": "핸드볼경기장 북서 광장 인도",
        "coords": [[127.126831, 37.517993], [127.126574, 37.518087], [127.126418, 37.518113],
                   [127.126209, 37.518113], [127.126113, 37.518104], [127.125978, 37.518074]],
        "l0": 0, "l1": 0, "bridge": False, "vehicle": False, "extra": {},
    })

    # ------------------------------------------------------------------
    # 2) 서울시 도로 58구간 (모두 차도 겸 보행 가능 level 0→0)
    # ------------------------------------------------------------------
    for lk in links:
        lid = str(lk["id"])
        raw_coords = shapes.get(lid) or [lk["a"], lk["b"]]
        coords = [[round(c[0], 6), round(c[1], 6)] for c in raw_coords]
        raw_polylines.append({
            "id": f"road_{lid}", "kind": "road_walkable",
            "name": f"{lk['road']} ({lk['from']}→{lk['to']})",
            "coords": coords, "l0": 0, "l1": 0, "bridge": False, "vehicle": True,
            "extra": {"linkId": lid, "underpassBelow": "haneol_overpass_deck" if lid == "1230085700" else None},
        })

    # ------------------------------------------------------------------
    # 3) 공원 내부 차도(보행 가능) 및 일반 보행로 (OSM)
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
                    "id": f"osm_br_{osm_idx}_{sfx}", "kind": "overpass_walkway", "name": "공원 보행 육교",
                    "coords": seg, "l0": la, "l1": lb, "bridge": True, "vehicle": False, "extra": {"primaryCorridor": False},
                })
            continue
        osm_idx += 1
        raw_polylines.append({
            "id": f"osm_{osm_idx}", "kind": "road_walkable" if is_road else "footway",
            "name": "공원 내부 차도(보행 가능)" if is_road else "공원 보행로",
            "coords": coords, "l0": 0, "l1": 0, "bridge": is_bridge, "vehicle": is_road, "extra": {},
        })

    # ------------------------------------------------------------------
    # 4) 지상(level 0→0) 선분들의 평면 교차점 분할 (level 1 육교 선분은 건드리지 않음!)
    # ------------------------------------------------------------------
    lvl0_segs = []  # (poly_idx, seg_idx, p1, p2)
    for pi, pl in enumerate(raw_polylines):
        if pl["l0"] == 0 and pl["l1"] == 0:
            for si in range(len(pl["coords"]) - 1):
                lvl0_segs.append((pi, si, pl["coords"][si], pl["coords"][si + 1]))

    splits = {}  # (pi, si) -> list of [lng, lat]
    for i in range(len(lvl0_segs)):
        pi1, si1, a1, b1 = lvl0_segs[i]
        for j in range(i + 1, len(lvl0_segs)):
            pi2, si2, a2, b2 = lvl0_segs[j]
            if pi1 == pi2:
                continue
            inter = seg_intersection_2d(a1, b1, a2, b2)
            if inter:
                splits.setdefault((pi1, si1), []).append(inter)
                splits.setdefault((pi2, si2), []).append(inter)

    for (pi, si), pts in sorted(splits.items(), key=lambda kv: (kv[0][0], -kv[0][1])):
        cs = raw_polylines[pi]["coords"]
        a = cs[si]
        pts_sorted = sorted(pts, key=lambda p: pt_dist_m(a, p))
        cs[si:si + 1] = [a] + pts_sorted

    # ------------------------------------------------------------------
    # 5) 단위 구간(2점 간선) 전개 + 지상(level=0) 인접 끝점·T자 분기 자동 연결(18m 이내)
    #    ※ level=1 노드는 절대 지상(level=0) 노드와 자동 연결하지 않음(입체 분리 보장!)
    # ------------------------------------------------------------------
    edge_features = []
    lvl0_nodes = {}  # nid -> [lng, lat]
    lvl0_segments_for_snap = []  # (nid_u, nid_v, pt_u, pt_v)

    for pl in raw_polylines:
        cs = pl["coords"]
        l0, l1 = pl["l0"], pl["l1"]
        nseg = len(cs) - 1
        for i in range(nseg):
            if l0 == l1:
                la = lb = l0
            elif l0 == 0 and l1 == 1:
                la = 0
                lb = 1 if i == nseg - 1 else 0
            else:  # 1 -> 0
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
                lvl0_segments_for_snap.append((u, v, pa, pb))
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
                    **pl["extra"],
                },
            })

    # 지상(level=0) 노드들 중 다른 지상 선분에 16m 이내로 맞닿는 T자 교차점·횡단보도 연결
    n_items = list(lvl0_nodes.items())
    seen_pairs = {(f["properties"]["u"], f["properties"]["v"]) for f in edge_features}
    snap_cnt = 0
    for nid, pt in n_items:
        best = None
        for u, v, pa, pb in lvl0_segments_for_snap:
            if nid == u or nid == v:
                continue
            if abs(pt[0] - pa[0]) > 0.0003 and abs(pt[0] - pb[0]) > 0.0003:
                continue
            if abs(pt[1] - pa[1]) > 0.0003 and abs(pt[1] - pb[1]) > 0.0003:
                continue
            proj, d = project_point_to_seg(pt, pa, pb)
            if 0.3 < d <= 16.0 and (best is None or d < best[0]):
                # 가장 가까운 정점(pa 또는 pb, 또는 투영 노드)으로 연결
                target_nid = u if pt_dist_m(proj, pa) <= pt_dist_m(proj, pb) else v
                target_pt = pa if target_nid == u else pb
                td = pt_dist_m(pt, target_pt)
                if td <= 22.0:
                    best = (d, target_nid, target_pt, td)
        if best:
            _, t_nid, t_pt, td = best
            if (nid, t_nid) not in seen_pairs and (t_nid, nid) not in seen_pairs:
                seen_pairs.add((nid, t_nid))
                snap_cnt += 1
                edge_features.append({
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": [pt, t_pt]},
                    "properties": {
                        "id": f"junction_{snap_cnt}",
                        "featureRole": "edge",
                        "kind": "connector",
                        "name": "지상 교차·보도 연결",
                        "u": nid,
                        "v": t_nid,
                        "fromLevel": 0,
                        "toLevel": 0,
                        "bridge": False,
                        "walkable": True,
                        "vehicle": False,
                        "meters": round(td, 1),
                    },
                })

    # ------------------------------------------------------------------
    # 6) 역·주차장·공연장 기준점 → 주변 지상(level=0) 보행 노드 다중 연결(최대 4개, 120m 이내)
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
            ((pt_dist_m(pt, npt), nid, npt) for nid, npt in lvl0_nodes.items()),
            key=lambda x: x[0],
        )
        picked = []
        for d, nid, npt in cands:
            if d > 130.0 and picked:
                break
            # 서로 다른 방향의 진입점까지 최대 6개 연결(건물 중심 좌표에서도 정문·후문 광장 모두 닿게 함)
            if all(pt_dist_m(npt, p[2]) >= 22.0 for p in picked):
                picked.append((d, nid, npt))
            if len(picked) >= 6:
                break
        for k_i, (d, nid, npt) in enumerate(picked, 1):
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
                },
            })

    # ------------------------------------------------------------------
    # 7) 분기 없는 중간 정점(degree=2, 동일 속성·동일 층) 병합 → 파일 용량 경량화(경로·거리 동일)
    # ------------------------------------------------------------------
    deg = {}
    for f in edge_features:
        p = f["properties"]
        deg[p["u"]] = deg.get(p["u"], 0) + 1
        deg[p["v"]] = deg.get(p["v"], 0) + 1

    # parentId 별로 원래 순서대로 이어 붙이되, 분기점(deg != 2)에서 끊는다
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
                )
                if can_join:
                    cur["coords"].append(sc[1])
                    cp["v"] = sp["v"]
                    cp["meters"] = round(cp["meters"] + sp["meters"], 1)
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
    edge_features = compact_edges

    kst = timezone(timedelta(hours=9))
    features = poly_features + edge_features
    out = {
        "type": "FeatureCollection",
        "metadata": {
            "built": datetime.now(kst).strftime("%Y-%m-%d"),
            "description": "올림픽공원 보행 네트워크 — 모든 차도는 지상(level=0) 보행 가능 구간으로 포함하고, 만남의광장(올림픽공원역)~KSPO DOME 보행 인도는 하부 차도(1230085700) 위를 지나는 입체 인도(level=1)로 분리함",
            "walkSpeedMPerMin": 75,
            "rules": {
                "allRoadsWalkable": True,
                "gradeSeparatedLevels": [0, 1],
                "overpassCorridor": "올림픽공원역 만남의광장 ↔ 차도 위 보행 육교(level=1) ↔ KSPO DOME·핸드볼경기장 광장",
            },
        },
        "features": features,
    }
    out_path = ROOT / "web/data/pedestrian_network.geojson"
    out_path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # 지도(3D·평면) 즉시 표시용 경량 레이어 파일 (만남의광장~육교~한얼광장 인도 다각형 + 주 보행축·난간)
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

    # 즉시 최단 경로 검증 출력
    adj = {}
    for f in edge_features:
        p = f["properties"]
        u, v, w = p["u"], p["v"], float(p["meters"])
        adj.setdefault(u, []).append((v, w, p["kind"], p.get("bridge", False)))
        adj.setdefault(v, []).append((u, w, p["kind"], p.get("bridge", False)))

    def dijkstra(su, tu):
        pq = [(0.0, su, False)]
        best = {su: 0.0}
        while pq:
            d, u, used_br = heapq.heappop(pq)
            if u == tu:
                return round(d), max(1, round(d / 75.0)), used_br
            if d > best.get(u, 1e18):
                continue
            for v, w, kind, is_br in adj.get(u, []):
                nd = d + w
                if nd < best.get(v, 1e18):
                    best[v] = nd
                    heapq.heappush(pq, (nd, v, used_br or (kind == "overpass_walkway" and is_br)))
        return None

    print(f"저장 완료 → {out_path} (피처 {len(features)}개, 간선 {len(edge_features)}개)")
    for st in ("올림픽공원역", "몽촌토성역", "한성백제역", "올림픽공원 주차장(동2문·남2문·북2문)"):
        for vn in ("KSPO DOME", "핸드볼경기장", "우리금융아트홀", "올림픽홀"):
            r = dijkstra(anchor_nodes[st][0], anchor_nodes[vn][0])
            print(f"  {st} -> {vn}: {r[0]}m · 약 {r[1]}분 (육교 통과={r[2]})" if r else f"  {st} -> {vn}: 경로 없음")


if __name__ == "__main__":
    main()
