// GET /api/buildings
// 브이월드 2D 데이터 API로 KSPO DOME 주변 건물(모양 + 층수)을 받아 3D 지도용 GeoJSON으로 돌려준다.
// 건물은 자주 바뀌지 않으므로 7일 동안 공유한다.
const { getJSON, send } = require("./_util");

// 올림픽공원과 주변 도로를 덮는 범위 (경도/위도)
const BOX = [127.105, 37.505, 127.140, 37.528];
const LAYER = "LT_C_SPBD";   // 도로명주소 건물

const num = (v) => { const n = Number(v); return Number.isFinite(n) ? n : null; };

module.exports = async (req, res) => {
  const key = (process.env.VWORLD_KEY || "").trim().replace(/^["']|["']$/g, "");
  if (!key) return send(res, 501, { error: "VWORLD_KEY 환경변수가 없습니다" });
  // 브이월드는 키를 발급받을 때 적은 서비스 URL과 domain 값이 같아야 한다. 적은 모양이 달라도 되도록 몇 가지로 시도.
  const host = "olpark-traffic.vercel.app";
  const tries = [...new Set([process.env.VWORLD_DOMAIN, `https://${host}`, host, `https://${host}/`, `http://${host}`].filter(Boolean))];
  const features = [];
  const errors = [];
  let domain = tries[0];
  try {
    for (const dmn of tries) {               // 첫 페이지로 맞는 domain 찾기
      const q = new URLSearchParams({ service: "data", request: "GetFeature", data: LAYER, key, domain: dmn,
        geomFilter: `BOX(${BOX.join(",")})`, crs: "EPSG:4326", format: "json", size: "1", page: "1" });
      const d = await getJSON(`https://api.vworld.kr/req/data?${q}`, { timeoutMs: 15000 });
      const r = d.response || {};
      if (r.status === "OK") { domain = dmn; break; }
      errors.push(`${dmn}: ${(r.error && r.error.code) || r.status}`);
      if (!(r.error && r.error.code === "INCORRECT_KEY")) break;   // 키 문제가 아니면 더 시도할 필요 없음
    }
  } catch (e) { errors.push(e.message); }
  try {
    for (let page = 1; page <= 10; page++) {
      const q = new URLSearchParams({
        service: "data", request: "GetFeature", data: LAYER, key, domain,
        geomFilter: `BOX(${BOX.join(",")})`, crs: "EPSG:4326", format: "json",
        size: "1000", page: String(page), geometry: "true", attribute: "true",
      });
      const d = await getJSON(`https://api.vworld.kr/req/data?${q}`, { timeoutMs: 15000 });
      const r = d.response || {};
      if (r.status !== "OK") {
        if (page === 1) return send(res, 502, { error: "브이월드 응답 오류", status: r.status, detail: r.error || r,
          tried: errors, keyLength: key.length });
        break;
      }
      const fc = (r.result || {}).featureCollection || {};
      for (const f of fc.features || []) {
        const p = f.properties || {};
        const lower = Object.fromEntries(Object.entries(p).map(([k, v]) => [k.toLowerCase(), v]));
        const floors = num(lower.gro_flo_co) ?? num(lower.grnd_flr) ?? null;
        features.push({
          type: "Feature", geometry: f.geometry,
          properties: { name: lower.buld_nm || lower.bd_nm || "", floors,
                        height: Math.max(3, (floors || 2) * 3.3) },
        });
      }
      const total = Number((r.page || {}).total || 1);
      if (page >= total) break;
    }
  } catch (e) {
    errors.push(e.message);
  }
  if (!features.length) return send(res, 502, { error: "건물을 받지 못했습니다", errors });
  send(res, 200, { type: "FeatureCollection", features, meta: { layer: LAYER, box: BOX, errors } }, 604800);
};
