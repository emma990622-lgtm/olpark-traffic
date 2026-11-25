"""
브이월드(국가공간정보) 대용량 SHP 압축파일(.zip) 또는 .shp 파일에서
올림픽공원·주변 역 반경만 가볍게 잘라 WGS84 GeoJSON으로 저장하는 스크립트.

특징:
  - 외부 라이브러리(QGIS, geopandas, pyproj, pyshp 등) 설치 불필요 — 파이썬 표준 라이브러리만 사용
  - 100MB 넘는 .zip 압축을 풀지 않고 스트리밍으로 바로 읽으며, 중첩 .zip(선택다운로드 묶음)도 자동 처리
  - 국내 주요 좌표계 자동 인식·변환: EPSG:5174(베셀 중부원점, 7변수 보정 포함), 5186, 5181, 5179(UTM-K), 5178, 4326
  - 인자를 안 주면 data/raw, 프로젝트 폴더, 윈도우 '다운로드(Downloads)' 폴더에서 최근 받은 브이월드 .zip을 자동 탐색

실행:
  - 더블클릭: run_clip_vworld.bat (또는 .zip 파일을 run_clip_vworld.bat 아이콘 위에 끌어다 놓기)
  - 명령줄:   python scripts/35_clip_vworld_shp.py "C:\\Users\\...\\GIS건물통합정보.zip" "C:\\Users\\...\\등고선.zip"

결과:
  - 건물 면(Polygon): data/processed/vworld_buildings_olpark.geojson
  - 등고선(PolyLine): data/processed/vworld_contours_olpark.geojson
  - 기타 레이어:      data/processed/vworld_<이름>_olpark.geojson
"""
import argparse
import io
import json
import math
import os
import re
import struct
import sys
import time
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "processed"

# 올림픽공원 + KSPO DOME + 주변 5개 역(올림픽공원·몽촌토성·한성백제·둔촌오륜·강동구청) 반경
DEFAULT_BBOX = (127.103, 37.504, 127.142, 37.530)  # (min_lon, min_lat, max_lon, max_lat)

ELLIPSOIDS = {
    "GRS80": (6378137.0, 1.0 / 298.257222101),
    "WGS84": (6378137.0, 1.0 / 298.257223563),
    "BESSEL": (6377397.155, 1.0 / 299.1528128),
}
# 국토지리정보원/EPSG:15945 Korean 1985(Bessel) -> WGS84 7변수 (Position Vector 기준)
BESSEL_TOWGS84 = (-115.80, 474.99, 674.11, 1.16, -2.31, -1.63, 6.43)


def decode_zip_name(zinfo):
    """윈도우 한글 .zip 내부 파일명 깨짐(CP437 -> CP949) 복원."""
    name = zinfo.filename
    if zinfo.flag_bits & 0x800:
        return name
    try:
        return name.encode("cp437").decode("cp949")
    except Exception:
        return name


# ---------- 좌표계(CRS) 해석 및 변환 ----------

def _meridian_arc(phi, a, e2):
    e4 = e2 * e2
    e6 = e4 * e2
    e8 = e6 * e2
    a0 = 1.0 - e2 / 4.0 - 3.0 * e4 / 64.0 - 5.0 * e6 / 256.0 - 175.0 * e8 / 16384.0
    a2 = 3.0 / 8.0 * (e2 + e4 / 4.0 + 15.0 * e6 / 128.0 - 455.0 * e8 / 4096.0)
    a4 = 15.0 / 256.0 * (e4 + 3.0 * e6 / 4.0 - 77.0 * e8 / 128.0)
    a6 = 35.0 / 3072.0 * (e6 - 41.0 * e8 / 32.0)
    return a * (a0 * phi - a2 * math.sin(2.0 * phi) + a4 * math.sin(4.0 * phi) - a6 * math.sin(6.0 * phi))


def tm_fwd(lon_deg, lat_deg, a, rf, lat0_deg, lon0_deg, k0, x0, y0):
    e2 = 2.0 * rf - rf * rf
    ep2 = e2 / (1.0 - e2)
    phi = math.radians(lat_deg)
    lam = math.radians(lon_deg)
    phi0 = math.radians(lat0_deg)
    lam0 = math.radians(lon0_deg)
    m = _meridian_arc(phi, a, e2)
    m0 = _meridian_arc(phi0, a, e2)
    sinp, cosp, tanp = math.sin(phi), math.cos(phi), math.tan(phi)
    n = a / math.sqrt(1.0 - e2 * sinp * sinp)
    t = tanp * tanp
    c = ep2 * cosp * cosp
    aa = (lam - lam0) * cosp
    a2, a3, a4, a5, a6 = aa * aa, aa ** 3, aa ** 4, aa ** 5, aa ** 6
    x = x0 + k0 * n * (
        aa + (1.0 - t + c) * a3 / 6.0
        + (5.0 - 18.0 * t + t * t + 72.0 * c - 58.0 * ep2) * a5 / 120.0
    )
    y = y0 + k0 * (
        m - m0 + n * tanp * (
            a2 / 2.0
            + (5.0 - t + 9.0 * c + 4.0 * c * c) * a4 / 24.0
            + (61.0 - 58.0 * t + t * t + 600.0 * c - 330.0 * ep2) * a6 / 720.0
        )
    )
    return x, y


def tm_inv(x, y, a, rf, lat0_deg, lon0_deg, k0, x0, y0):
    e2 = 2.0 * rf - rf * rf
    ep2 = e2 / (1.0 - e2)
    phi0 = math.radians(lat0_deg)
    lam0 = math.radians(lon0_deg)
    m0 = _meridian_arc(phi0, a, e2)
    m = m0 + (y - y0) / k0
    e1 = (1.0 - math.sqrt(1.0 - e2)) / (1.0 + math.sqrt(1.0 - e2))
    mu = m / (a * (1.0 - e2 / 4.0 - 3.0 * e2 * e2 / 64.0 - 5.0 * e2 ** 3 / 256.0))
    phi1 = (
        mu
        + (3.0 * e1 / 2.0 - 27.0 * e1 ** 3 / 32.0) * math.sin(2.0 * mu)
        + (21.0 * e1 * e1 / 16.0 - 55.0 * e1 ** 4 / 32.0) * math.sin(4.0 * mu)
        + (151.0 * e1 ** 3 / 96.0) * math.sin(6.0 * mu)
        + (1097.0 * e1 ** 4 / 512.0) * math.sin(8.0 * mu)
    )
    sin1, cos1, tan1 = math.sin(phi1), math.cos(phi1), math.tan(phi1)
    n1 = a / math.sqrt(1.0 - e2 * sin1 * sin1)
    r1 = a * (1.0 - e2) / ((1.0 - e2 * sin1 * sin1) ** 1.5)
    t1 = tan1 * tan1
    c1 = ep2 * cos1 * cos1
    d = (x - x0) / (n1 * k0)
    d2, d3, d4, d5, d6 = d * d, d ** 3, d ** 4, d ** 5, d ** 6
    phi = phi1 - (n1 * tan1 / r1) * (
        d2 / 2.0
        - (5.0 + 3.0 * t1 + 10.0 * c1 - 4.0 * c1 * c1 - 9.0 * ep2) * d4 / 24.0
        + (61.0 + 90.0 * t1 + 298.0 * c1 + 45.0 * t1 * t1 - 252.0 * ep2 - 3.0 * c1 * c1) * d6 / 720.0
    )
    lam = lam0 + (
        d
        - (1.0 + 2.0 * t1 + c1) * d3 / 6.0
        + (5.0 - 2.0 * c1 + 28.0 * t1 - 3.0 * c1 * c1 + 8.0 * ep2 + 24.0 * t1 * t1) * d5 / 120.0
    ) / cos1
    return math.degrees(lam), math.degrees(phi)


def helmert_datum(lon_deg, lat_deg, src_ellps, dst_ellps, towgs84, inverse=False):
    a1, f1 = ELLIPSOIDS[src_ellps]
    a2, f2 = ELLIPSOIDS[dst_ellps]
    e2_1 = 2.0 * f1 - f1 * f1
    e2_2 = 2.0 * f2 - f2 * f2
    phi = math.radians(lat_deg)
    lam = math.radians(lon_deg)
    n1 = a1 / math.sqrt(1.0 - e2_1 * math.sin(phi) ** 2)
    x = n1 * math.cos(phi) * math.cos(lam)
    y = n1 * math.cos(phi) * math.sin(lam)
    z = n1 * (1.0 - e2_1) * math.sin(phi)

    dx, dy, dz, rx_s, ry_s, rz_s, ds_ppm = towgs84
    if inverse:
        dx, dy, dz, rx_s, ry_s, rz_s, ds_ppm = -dx, -dy, -dz, -rx_s, -ry_s, -rz_s, -ds_ppm
    arcsec = math.pi / (180.0 * 3600.0)
    rx, ry, rz = rx_s * arcsec, ry_s * arcsec, rz_s * arcsec
    s = 1.0 + ds_ppm * 1e-6

    x2 = dx + s * (x - rz * y + ry * z)
    y2 = dy + s * (rz * x + y - rx * z)
    z2 = dz + s * (-ry * x + rx * y + z)

    p = math.hypot(x2, y2)
    lam2 = math.atan2(y2, x2)
    phi2 = math.atan2(z2, p * (1.0 - e2_2))
    for _ in range(5):
        n2 = a2 / math.sqrt(1.0 - e2_2 * math.sin(phi2) ** 2)
        phi2 = math.atan2(z2 + e2_2 * n2 * math.sin(phi2), p)
    return math.degrees(lam2), math.degrees(phi2)


def parse_crs(prj_text, shp_bbox):
    """WKT(.prj) 또는 헤더 범위로 좌표계 파라미터 결정."""
    wkt = (prj_text or "").strip()
    upper = wkt.upper()

    if wkt and "PROJCS" not in upper and ("GEOGCS" in upper or "WGS_1984" in upper):
        return {"kind": "lonlat", "label": "EPSG:4326 (WGS84)"}

    if wkt and "PROJCS" in upper:
        def param(names, default):
            for nm in names:
                m = re.search(rf'PARAMETER\[\s*"{nm}"\s*,\s*([+-]?\d+(?:\.\d+)?)', wkt, re.I)
                if m:
                    return float(m.group(1))
            return default

        is_bessel = "BESSEL" in upper
        ellps = "BESSEL" if is_bessel else "GRS80"
        lat0 = param(["latitude_of_origin", "latitude_of_center"], 38.0)
        lon0 = param(["central_meridian", "longitude_of_center"], 127.0028902777778 if is_bessel else 127.0)
        k0 = param(["scale_factor"], 1.0)
        x0 = param(["false_easting"], 200000.0)
        y0 = param(["false_northing"], 500000.0 if is_bessel else 600000.0)
        towgs = None
        m_tw = re.search(r"TOWGS84\[\s*([^\]]+)\]", wkt, re.I)
        if m_tw:
            vals = [float(v.strip()) for v in m_tw.group(1).split(",") if v.strip()]
            if len(vals) >= 7:
                towgs = tuple(vals[:7])
            elif len(vals) == 3:
                towgs = (vals[0], vals[1], vals[2], 0.0, 0.0, 0.0, 0.0)
        elif is_bessel:
            towgs = BESSEL_TOWGS84

        # 브이월드/국가공간정보 EPSG:5174 .prj에는 가산경도 10.405초(0.00289028도)가 빠진 채
        # Bessel + 127.0 + 200000/500000으로 적혀 있는 경우가 흔하므로 보정 적용
        if is_bessel and abs(lon0 - 127.0) < 1e-7 and abs(x0 - 200000.0) < 1.0 and abs(y0 - 500000.0) < 1.0:
            lon0 = 127.0028902777778

        return {
            "kind": "tm",
            "ellps": ellps,
            "lat0": lat0,
            "lon0": lon0,
            "k0": k0,
            "x0": x0,
            "y0": y0,
            "towgs84": towgs,
            "label": f"TM({ellps}, lon0={lon0:.6f}, x0={x0:.0f}, y0={y0:.0f}, k0={k0})",
        }

    # .prj가 없는 경우 헤더 범위로 추정
    xmin, ymin, xmax, ymax = shp_bbox
    if abs(xmax) <= 180.5 and abs(ymax) <= 90.5:
        return {"kind": "lonlat", "label": "EPSG:4326 (범위 추정)"}
    if xmax > 700000:
        return {
            "kind": "tm", "ellps": "GRS80", "lat0": 38.0, "lon0": 127.5,
            "k0": 0.9996, "x0": 1000000.0, "y0": 2000000.0, "towgs84": None,
            "label": "EPSG:5179 UTM-K (범위 추정)",
        }
    if ymax > 520000:
        return {
            "kind": "tm", "ellps": "GRS80", "lat0": 38.0, "lon0": 127.0,
            "k0": 1.0, "x0": 200000.0, "y0": 600000.0, "towgs84": None,
            "label": "EPSG:5186 중부원점 (범위 추정)",
        }
    return {
        "kind": "tm", "ellps": "BESSEL", "lat0": 38.0, "lon0": 127.0028902777778,
        "k0": 1.0, "x0": 200000.0, "y0": 500000.0, "towgs84": BESSEL_TOWGS84,
        "label": "EPSG:5174 보정중부원점 (범위 추정)",
    }


def make_converters(crs):
    """(to_wgs84(x, y), from_wgs84(lon, lat)) 함수 쌍 반환."""
    if crs["kind"] == "lonlat":
        return (lambda x, y: (x, y)), (lambda lon, lat: (lon, lat))

    a, rf = ELLIPSOIDS[crs["ellps"]]
    lat0, lon0, k0, x0, y0 = crs["lat0"], crs["lon0"], crs["k0"], crs["x0"], crs["y0"]
    towgs = crs.get("towgs84")

    def to_wgs84(x, y):
        lon, lat = tm_inv(x, y, a, rf, lat0, lon0, k0, x0, y0)
        if towgs:
            lon, lat = helmert_datum(lon, lat, crs["ellps"], "WGS84", towgs, inverse=False)
        return lon, lat

    def from_wgs84(lon, lat):
        if towgs:
            lon, lat = helmert_datum(lon, lat, "WGS84", crs["ellps"], towgs, inverse=True)
        return tm_fwd(lon, lat, a, rf, lat0, lon0, k0, x0, y0)

    return to_wgs84, from_wgs84


# ---------- DBF / SHP 스트리밍 파서 ----------

class DbfRandomReader:
    """매칭된 레코드 번호(0-indexed)만 골라 읽는 경량 DBF 리더."""
    def __init__(self, raw_bytes, encoding_hint=None):
        self.buf = raw_bytes
        if len(raw_bytes) < 32:
            self.num_records = 0
            self.header_len = 0
            self.rec_len = 0
            self.fields = []
            self.encoding = "cp949"
            return
        self.num_records, self.header_len, self.rec_len = struct.unpack("<IHH", raw_bytes[4:12])
        self.encoding = (encoding_hint or "").strip().lower() or "cp949"
        if self.encoding in ("utf8", "utf-8"):
            self.encoding = "utf-8"
        elif self.encoding in ("ms949", "euc-kr", "euckr", "ansi", "949"):
            self.encoding = "cp949"

        self.fields = []
        pos = 32
        while pos + 32 <= self.header_len and raw_bytes[pos] != 0x0D:
            fdesc = raw_bytes[pos:pos + 32]
            raw_name = fdesc[:11].split(b"\x00", 1)[0]
            fname = self._decode(raw_name).replace("\x00", "").strip()
            ftype = chr(fdesc[11])
            flen = fdesc[16]
            fdec = fdesc[17]
            self.fields.append((fname, ftype, flen, fdec))
            pos += 32

    def _decode(self, b):
        for enc in (self.encoding, "cp949", "utf-8", "latin1"):
            try:
                return b.decode(enc)
            except Exception:
                continue
        return b.decode("latin1", errors="ignore")

    def read_record(self, idx):
        if idx < 0 or idx >= self.num_records or self.rec_len <= 0:
            return {}
        off = self.header_len + idx * self.rec_len
        if off + self.rec_len > len(self.buf):
            return {}
        rec = self.buf[off:off + self.rec_len]
        if rec[:1] == b"*":  # 삭제 표시 레코드
            return {}
        pos = 1
        out = {}
        for fname, ftype, flen, fdec in self.fields:
            raw = rec[pos:pos + flen]
            pos += flen
            txt = self._decode(raw).replace("\x00", "").strip()
            if not txt:
                continue
            if ftype in ("N", "F"):
                if txt in ("*", "-", "."):
                    continue
                try:
                    val = float(txt) if (fdec > 0 or "." in txt) else int(txt)
                except ValueError:
                    val = txt
                out[fname] = val
            elif ftype == "L":
                out[fname] = txt.upper() in ("Y", "T", "1")
            else:
                out[fname] = txt
        return out


def signed_ring_area(pts):
    """평면 좌표 링 면적 부호: 음수면 시계방향(Shapefile 외곽), 양수면 반시계방향(구멍)."""
    if len(pts) < 3:
        return 0.0
    area = 0.0
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        area += (x1 * y2 - x2 * y1)
    return 0.5 * area


def convert_polygon_parts(parts_pts, to_wgs84):
    """Shapefile Polygon 파트를 GeoJSON Polygon 또는 MultiPolygon으로 변환."""
    polys = []
    for ring in parts_pts:
        if len(ring) < 4:
            continue
        is_hole = signed_ring_area(ring) > 0
        wgs_ring = []
        for x, y in ring:
            lon, lat = to_wgs84(x, y)
            pt = [round(lon, 6), round(lat, 6)]
            if not wgs_ring or pt != wgs_ring[-1]:
                wgs_ring.append(pt)
        if len(wgs_ring) < 3:
            continue
        if wgs_ring[0] != wgs_ring[-1]:
            wgs_ring.append(wgs_ring[0])
        if len(wgs_ring) < 4:
            continue

        # GeoJSON RFC 7946: 외곽 반시계, 구멍 시계
        if not is_hole:
            wgs_ring = list(reversed(wgs_ring))
            polys.append([wgs_ring])
        else:
            if polys:
                polys[-1].append(list(reversed(wgs_ring)))
            else:
                polys.append([list(reversed(wgs_ring))])

    if not polys:
        return None
    if len(polys) == 1:
        return {"type": "Polygon", "coordinates": polys[0]}
    return {"type": "MultiPolygon", "coordinates": polys}


def _clip_segment_box(p1, p2, box):
    """Liang-Barsky 2D 선분 클리핑: 선분이 box와 겹치면 잘린 (q1, q2) 반환, 안 겹치면 None."""
    xmin, ymin, xmax, ymax = box
    x1, y1 = p1
    dx = p2[0] - x1
    dy = p2[1] - y1
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x1 - xmin), (dx, xmax - x1), (-dy, y1 - ymin), (dy, ymax - y1)):
        if abs(p) < 1e-12:
            if q < 0.0:
                return None
        else:
            r = q / p
            if p < 0.0:
                if r > t1:
                    return None
                if r > t0:
                    t0 = r
            else:
                if r < t0:
                    return None
                if r < t1:
                    t1 = r
    return (x1 + t0 * dx, y1 + t0 * dy), (x1 + t1 * dx, y1 + t1 * dy)


def clip_polyline_parts(parts_pts, clip_box, to_wgs84, min_step_m=0.8):
    """긴 등고선·도로 선형에서 올림픽공원 범위 안쪽 구간만 정확히 잘라 경량화."""
    lines = []
    min_step_sq = min_step_m * min_step_m

    for part in parts_pts:
        if len(part) < 2:
            continue
        cur = []
        for i in range(len(part) - 1):
            clipped = _clip_segment_box(part[i], part[i + 1], clip_box)
            if clipped is None:
                if len(cur) >= 2:
                    lines.append(cur)
                cur = []
            else:
                q1, q2 = clipped
                if not cur:
                    cur.append(q1)
                elif (q1[0] - cur[-1][0]) ** 2 + (q1[1] - cur[-1][1]) ** 2 > 1e-4:
                    if len(cur) >= 2:
                        lines.append(cur)
                    cur = [q1]
                cur.append(q2)
        if len(cur) >= 2:
            lines.append(cur)

    wgs_lines = []
    for seg in lines:
        thinned = [seg[0]]
        for pt in seg[1:-1]:
            dx = pt[0] - thinned[-1][0]
            dy = pt[1] - thinned[-1][1]
            if dx * dx + dy * dy >= min_step_sq:
                thinned.append(pt)
        thinned.append(seg[-1])

        wgs = []
        for x, y in thinned:
            lon, lat = to_wgs84(x, y)
            p = [round(lon, 6), round(lat, 6)]
            if not wgs or p != wgs[-1]:
                wgs.append(p)
        if len(wgs) >= 2:
            wgs_lines.append(wgs)

    if not wgs_lines:
        return None
    if len(wgs_lines) == 1:
        return {"type": "LineString", "coordinates": wgs_lines[0]}
    return {"type": "MultiLineString", "coordinates": wgs_lines}


def enrich_props(props, kind, z_val=None):
    """긴 식별번호 문자열은 덜어내고 유의미한 DBF 속성과 표준 높이(height_m/elev_m)를 보존."""
    skip_long_ids = {"a0", "a1", "a2", "a19", "a21", "pnu", "ufid", "gis_id", "bjd_cd"}
    out = {}
    for k, v in props.items():
        if k.lower() in skip_long_ids and isinstance(v, str) and len(v) >= 16:
            continue
        out[k] = v

    lower = {k.lower(): v for k, v in props.items()}

    def num_from(keys):
        for k in keys:
            v = lower.get(k.lower())
            if isinstance(v, (int, float)) and math.isfinite(v):
                return float(v)
            if isinstance(v, str):
                try:
                    f = float(v)
                    if math.isfinite(f):
                        return f
                except ValueError:
                    pass
        return None

    if kind == "buildings":
        # GIS건물통합정보(AL_D010): A16=높이(m), A26=지상층수, A24=건물명 / 도로명주소건물: GRO_FLO_CO/GRND_FLR
        h = num_from(["height", "hg", "bld_hg", "heit", "a16"])
        fl = num_from(["grnd_flr", "gro_flo_co", "flr_cnt", "a26"])
        if h is not None and h > 0:
            out["height_m"] = round(h, 2)
        if fl is not None and 0 < fl < 200:
            out["floors"] = int(round(fl))
        for nk in ("bld_nm", "buld_nm", "bd_nm", "a24"):
            v = lower.get(nk)
            if isinstance(v, str) and v:
                out.setdefault("name", v)
                break
    elif kind == "contours":
        # 연속수치지형도 등고선(N3L_F0010000 / AL_D155): ctrln_hg / CONT / ELEV / ALT / Z값
        elev = num_from(["ctrln_hg", "cont", "elev", "elevation", "alt", "height", "z", "a2", "a3"])
        if elev is None and z_val is not None and math.isfinite(z_val) and abs(z_val) < 9000:
            elev = z_val
        if elev is not None:
            out["elev_m"] = round(elev, 2)

    return out


def classify_layer(display_name, shape_type, field_names):
    """파일명 + 도형 타입 + 컬럼명으로 buildings / contours / other 분류."""
    nm = display_name.lower()
    fset = {f.lower() for f in field_names}
    base_type = shape_type % 10  # 1:Point, 3:PolyLine, 5:Polygon

    if base_type == 5:
        if any(k in nm for k in ("건물", "building", "spbd", "d010", "b001")) or (
            fset & {"a16", "hg", "bld_hg", "gro_flo_co", "grnd_flr"}
        ):
            return "buildings"
    if base_type == 3:
        if any(k in nm for k in ("등고", "cont", "d155", "f001")) or (
            fset & {"ctrln_hg", "cont", "elev", "elevation"}
        ):
            return "contours"
        if any(k in nm for k in ("보행", "도로", "인도", "육교", "road", "walk")):
            return "roads_walk"
    stem = re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", Path(display_name).stem).strip("_") or "layer"
    return stem[:30]


def clip_shapefile_stream(shp_stream, dbf_bytes, prj_text, cpg_text, display_name, wgs_bbox):
    """단일 .shp 스트림에서 wgs_bbox와 겹치는 객체만 추출해 반환."""
    hdr = shp_stream.read(100)
    if len(hdr) < 100:
        return None
    file_code = struct.unpack(">i", hdr[:4])[0]
    if file_code != 9994:
        return None
    shape_type = struct.unpack("<i", hdr[32:36])[0]
    shp_bbox = struct.unpack("<4d", hdr[36:68])

    crs = parse_crs(prj_text, shp_bbox)
    to_wgs84, from_wgs84 = make_converters(crs)

    # WGS84 사각형 네 꼭짓점을 원본 투영좌표로 바꿔 검색 범위 산출
    min_lon, min_lat, max_lon, max_lat = wgs_bbox
    corners = [
        from_wgs84(min_lon, min_lat),
        from_wgs84(min_lon, max_lat),
        from_wgs84(max_lon, min_lat),
        from_wgs84(max_lon, max_lat),
    ]
    b_xmin = min(c[0] for c in corners)
    b_xmax = max(c[0] for c in corners)
    b_ymin = min(c[1] for c in corners)
    b_ymax = max(c[1] for c in corners)

    # 선형 자르기용 약간의 여유(약 80m)
    pad = 0.0008 if crs["kind"] == "lonlat" else 80.0
    line_clip_box = (b_xmin - pad, b_ymin - pad, b_xmax + pad, b_ymax + pad)

    # 파일 전체 범위가 올림픽공원과 아예 안 겹치면 즉시 건너뜀(수치지형도 타 도엽 고속 스킵)
    if shp_bbox[2] < b_xmin or shp_bbox[0] > b_xmax or shp_bbox[3] < b_ymin or shp_bbox[1] > b_ymax:
        dbf_meta = DbfRandomReader(dbf_bytes[:2048] if dbf_bytes else b"", cpg_text)
        kind = classify_layer(display_name, shape_type, [f[0] for f in dbf_meta.fields])
        return {
            "kind": kind, "crs_label": crs["label"], "prj": (prj_text or "").strip(),
            "fields": dbf_meta.fields, "total_records": 0, "features": [],
        }

    dbf = DbfRandomReader(dbf_bytes or b"", cpg_text)
    kind = classify_layer(display_name, shape_type, [f[0] for f in dbf.fields])

    features = []
    rec_idx = -1
    while True:
        rh = shp_stream.read(8)
        if len(rh) < 8:
            break
        rec_num, content_words = struct.unpack(">ii", rh)
        rec_idx += 1
        byte_len = content_words * 2
        if byte_len <= 0:
            continue

        if byte_len < 4:
            shp_stream.read(byte_len)
            continue

        # 먼저 도형 타입과 경계 상자(36바이트)만 읽어 범위 밖이면 나머지 정점 바이트는 통째로 건너뜀
        if shape_type % 10 in (3, 5) and byte_len >= 44:
            head36 = shp_stream.read(36)
            rem = byte_len - 36
            rtype = struct.unpack("<i", head36[:4])[0]
            if rtype == 0:
                if rem > 0:
                    shp_stream.read(rem)
                continue
            rxmin, rymin, rxmax, rymax = struct.unpack("<4d", head36[4:36])
            if rxmax < b_xmin or rxmin > b_xmax or rymax < b_ymin or rymin > b_ymax:
                # 범위 밖 레코드 고속 스킵
                if rem > 0:
                    shp_stream.read(rem)
                continue
            rest = shp_stream.read(rem) if rem > 0 else b""
            num_parts, num_points = struct.unpack("<ii", rest[:8])
            parts_end = 8 + 4 * num_parts
            parts = struct.unpack(f"<{num_parts}i", rest[8:parts_end])
            pts_end = parts_end + 16 * num_points
            coords_flat = struct.unpack(f"<{num_points * 2}d", rest[parts_end:pts_end])
            pts = [(coords_flat[2 * i], coords_flat[2 * i + 1]) for i in range(num_points)]

            z_val = None
            if rtype in (13, 15) and len(rest) >= pts_end + 24:
                zmin, zmax = struct.unpack("<2d", rest[pts_end:pts_end + 16])
                z_val = 0.5 * (zmin + zmax)

            parts_pts = []
            for p_i in range(num_parts):
                s = parts[p_i]
                e = parts[p_i + 1] if p_i + 1 < num_parts else num_points
                parts_pts.append(pts[s:e])

            if rtype % 10 == 5:
                geom = convert_polygon_parts(parts_pts, to_wgs84)
            else:
                geom = clip_polyline_parts(parts_pts, line_clip_box, to_wgs84)

            if not geom:
                continue
            props = enrich_props(dbf.read_record(rec_idx), kind, z_val=z_val)
            features.append({"type": "Feature", "geometry": geom, "properties": props})

        else:
            body = shp_stream.read(byte_len)
            rtype = struct.unpack("<i", body[:4])[0]
            if rtype % 10 == 1 and len(body) >= 20:
                x, y = struct.unpack("<2d", body[4:20])
                if not (b_xmin <= x <= b_xmax and b_ymin <= y <= b_ymax):
                    continue
                z_val = struct.unpack("<d", body[20:28])[0] if rtype == 11 and len(body) >= 28 else None
                lon, lat = to_wgs84(x, y)
                props = enrich_props(dbf.read_record(rec_idx), kind, z_val=z_val)
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
                    "properties": props,
                })

    return {
        "kind": kind,
        "crs_label": crs["label"],
        "prj": (prj_text or "").strip(),
        "fields": dbf.fields,
        "total_records": rec_idx + 1,
        "features": features,
    }


# ---------- .zip(중첩 포함) 및 폴더 탐색 ----------

def process_zip_bytes(zf, source_label, wgs_bbox, grouped):
    """ZipFile 내부의 모든 .shp 세트 및 중첩 .zip 재귀 처리."""
    infos = zf.infolist()
    by_raw_key = {}
    nested_zips = []

    for info in infos:
        if info.is_dir():
            continue
        p = PurePosixPath(info.filename)
        ext = p.suffix.lower()
        if ext == ".zip":
            nested_zips.append(info)
            continue
        if ext in (".shp", ".dbf", ".prj", ".cpg"):
            key = str(p.with_suffix("")).lower()
            by_raw_key.setdefault(key, {})[ext] = info

    for key, files in sorted(by_raw_key.items()):
        if ".shp" not in files:
            continue
        shp_info = files[".shp"]
        disp = f"{source_label}:{decode_zip_name(shp_info)}"
        dbf_bytes = zf.read(files[".dbf"]) if ".dbf" in files else b""
        prj_text = ""
        if ".prj" in files:
            raw_prj = zf.read(files[".prj"])
            for enc in ("cp949", "utf-8", "latin1"):
                try:
                    prj_text = raw_prj.decode(enc)
                    break
                except Exception:
                    pass
        cpg_text = zf.read(files[".cpg"]).decode("latin1", errors="ignore") if ".cpg" in files else ""

        with zf.open(shp_info, "r") as shp_stream:
            res = clip_shapefile_stream(shp_stream, dbf_bytes, prj_text, cpg_text, disp, wgs_bbox)
        if res is not None:
            _merge_result(grouped, res, disp)

    for nz in nested_zips:
        nested_label = f"{source_label}/{decode_zip_name(nz)}"
        try:
            data = zf.read(nz)
            with zipfile.ZipFile(io.BytesIO(data), "r") as sub_zf:
                process_zip_bytes(sub_zf, nested_label, wgs_bbox, grouped)
        except Exception as e:
            print(f"  [경고] 중첩 압축 열기 실패 ({nested_label}): {e}")


def process_input_path(path, wgs_bbox, grouped):
    path = Path(path)
    if path.is_dir():
        for sub in sorted(path.rglob("*")):
            if sub.suffix.lower() in (".zip", ".shp"):
                process_input_path(sub, wgs_bbox, grouped)
        return

    ext = path.suffix.lower()
    if ext == ".zip":
        print(f"읽는 중: {path} ({path.stat().st_size / (1024 * 1024):.1f} MB)")
        with zipfile.ZipFile(path, "r") as zf:
            process_zip_bytes(zf, path.name, wgs_bbox, grouped)
    elif ext == ".shp":
        print(f"읽는 중: {path} ({path.stat().st_size / (1024 * 1024):.1f} MB)")
        dbf_p = _sibling(path, ".dbf")
        prj_p = _sibling(path, ".prj")
        cpg_p = _sibling(path, ".cpg")
        dbf_bytes = dbf_p.read_bytes() if dbf_p else b""
        prj_text = ""
        if prj_p:
            raw_prj = prj_p.read_bytes()
            for enc in ("cp949", "utf-8", "latin1"):
                try:
                    prj_text = raw_prj.decode(enc)
                    break
                except Exception:
                    pass
        cpg_text = cpg_p.read_text(encoding="latin1", errors="ignore") if cpg_p else ""
        with open(path, "rb") as shp_stream:
            res = clip_shapefile_stream(shp_stream, dbf_bytes, prj_text, cpg_text, path.name, wgs_bbox)
        if res is not None:
            _merge_result(grouped, res, path.name)


def _sibling(shp_path, ext):
    for cand in (shp_path.with_suffix(ext), shp_path.with_suffix(ext.upper())):
        if cand.exists():
            return cand
    return None


def _merge_result(grouped, res, source_name):
    kind = res["kind"]
    bucket = grouped.setdefault(kind, {
        "sources": [],
        "crs": set(),
        "prj": "",
        "fields": [],
        "scanned": 0,
        "features": [],
    })
    bucket["sources"].append(source_name)
    bucket["crs"].add(res["crs_label"])
    if res["prj"] and not bucket["prj"]:
        bucket["prj"] = res["prj"]
    if res["fields"] and not bucket["fields"]:
        bucket["fields"] = res["fields"]
    bucket["scanned"] += res["total_records"]
    bucket["features"].extend(res["features"])
    print(f"  -> [{kind}] {source_name}: 전체 {res['total_records']:,}건 중 올림픽공원 주변 {len(res['features']):,}건 추출 ({res['crs_label']})")


def zip_has_shp(zip_path):
    """압축파일 안에 .shp 또는 중첩 .zip이 들어있는지 빠르게 확인."""
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                ext = PurePosixPath(info.filename).suffix.lower()
                if ext == ".shp":
                    return True
                if ext == ".zip" and info.file_size < 300 * 1024 * 1024:
                    return True
    except Exception:
        return False
    return False


def auto_discover_inputs():
    """인자가 없을 때 data/raw, 프로젝트 루트, 다운로드 폴더에서 브이월드 SHP/ZIP 자동 탐색."""
    found = []
    seen = set()

    def add(p):
        rp = str(p.resolve())
        if rp not in seen:
            seen.add(rp)
            found.append(p)

    # 1) 프로젝트 안(data/raw, 루트)에 놓인 .zip / .shp
    for folder in (ROOT / "data" / "raw", ROOT):
        if not folder.exists():
            continue
        for p in sorted(folder.glob("*.zip")):
            if zip_has_shp(p):
                add(p)
        for p in sorted(folder.glob("*.shp")):
            add(p)

    if found:
        return found

    # 2) 윈도우 기본 다운로드(Downloads)·바탕화면에서 최근 14일 내 받은 브이월드 SHP 압축파일 탐색
    keywords = ("gis", "건물", "등고", "보행", "도로", "수치", "al_", "n3", "f_fac", "lt_c", "vworld", "다운로드")
    cutoff = time.time() - 14 * 86400
    for folder in (Path.home() / "Downloads", Path.home() / "Desktop"):
        if not folder.exists():
            continue
        cands = sorted(folder.glob("*.zip"), key=lambda x: x.stat().st_mtime, reverse=True)
        for p in cands:
            try:
                st = p.stat()
            except OSError:
                continue
            if st.st_mtime < cutoff or st.st_size < 1024:
                continue
            nm = p.name.lower()
            if any(k in nm for k in keywords) and zip_has_shp(p):
                add(p)

    if found:
        return found

    # 3) 그래도 못 찾으면 윈도우 파일 선택창 띄우기(GUI 환경일 때만)
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        selected = filedialog.askopenfilenames(
            title="브이월드에서 받은 ZIP 또는 SHP 파일을 모두 선택하세요 (Ctrl 클릭으로 다중 선택)",
            filetypes=[("공간정보 압축/SHP", "*.zip *.shp"), ("모든 파일", "*.*")],
        )
        root.destroy()
        for s in selected:
            add(Path(s))
    except Exception:
        pass

    return found


def main():
    ap = argparse.ArgumentParser(description="브이월드 대용량 SHP/ZIP에서 올림픽공원 주변만 경량 GeoJSON으로 자르기")
    ap.add_argument("inputs", nargs="*", help=".zip 파일, .shp 파일 또는 폴더 경로(생략 시 자동 탐색)")
    ap.add_argument("--bbox", nargs=4, type=float, default=list(DEFAULT_BBOX),
                    metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"),
                    help="자를 경위도 범위 (기본: 올림픽공원·주변 역 반경)")
    ap.add_argument("--out-dir", default=str(OUT_DIR), help="결과 저장 폴더 (기본: data/processed)")
    args = ap.parse_args()

    inputs = [Path(p) for p in args.inputs] if args.inputs else auto_discover_inputs()
    if not inputs:
        print("\n[안내] 처리할 브이월드 .zip 또는 .shp 파일을 찾지 못했어요.")
        print("  방법 1) 다운받은 .zip 파일을 data\\raw 폴더에 넣고 다시 실행해 주세요.")
        print("  방법 2) 탐색기에서 .zip 파일을 run_clip_vworld.bat 아이콘 위에 끌어다 놓아 주세요.")
        raise SystemExit(1)

    wgs_bbox = tuple(args.bbox)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    grouped = {}
    for inp in inputs:
        if not inp.exists():
            print(f"[경고] 파일이 없어요: {inp}")
            continue
        process_input_path(inp, wgs_bbox, grouped)

    if not grouped:
        print("\n[안내] 선택한 파일 안에서 .shp 공간정보를 찾지 못했어요.")
        raise SystemExit(1)

    print("\n=== 저장 결과 ===")
    saved = []
    for kind, data in grouped.items():
        if not data["features"]:
            print(f"  - [{kind}] 올림픽공원 범위({wgs_bbox})와 겹치는 도형이 0건이라 건너뛰었어요.")
            continue
        out_path = out_dir / f"vworld_{kind}_olpark.geojson"
        payload = {
            "type": "FeatureCollection",
            "meta": {
                "kind": kind,
                "bbox": list(wgs_bbox),
                "crs_detected": sorted(data["crs"]),
                "prj": data["prj"],
                "fields": [[n, t, l, d] for (n, t, l, d) in data["fields"]],
                "scanned_records": data["scanned"],
                "feature_count": len(data["features"]),
                "sources": data["sources"],
            },
            "features": data["features"],
        }
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        out_path.write_text(text, encoding="utf-8")
        sz_mb = out_path.stat().st_size / (1024 * 1024)
        saved.append((out_path, len(data["features"]), sz_mb))
        print(f"  ✅ {out_path} ({len(data['features']):,}건, {sz_mb:.2f} MB)")
        sample_props = data["features"][0].get("properties", {})
        if sample_props:
            preview = ", ".join(f"{k}={v}" for k, v in list(sample_props.items())[:6])
            print(f"     속성 예시: {preview}")

    elapsed = time.time() - t0
    print(f"\n완료 ({elapsed:.1f}초 소요).")
    if saved:
        print("위 결과 파일(.geojson)은 용량이 작아 채팅창에 바로 업로드하시거나 git push 하실 수 있어요!")


if __name__ == "__main__":
    main()
