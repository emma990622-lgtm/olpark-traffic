// GET /api/weather
// 서울시 실시간 도시데이터(올림픽공원)의 날씨: 지금 날씨 + 앞으로 24시간 시간별 예보
// 방문객 예측 카드(web/assets/visitor.js)가 쓴다. 예보는 한 시간마다 바뀌므로 10분 공유.
const { getJSON, send, nowKST } = require("./_util");

// "-" → 0, "1.5mm" → 1.5, 숫자를 못 읽는데 비·눈 예보면 0.5(비 기준선)
function rainMm(v, type) {
  const wet = type && type !== "없음";
  const n = parseFloat(String(v == null ? "" : v).replace(/[^0-9.]/g, ""));
  if (Number.isFinite(n)) return wet ? Math.max(n, 0.5) : n;
  return wet ? 0.5 : 0;
}

module.exports = async (req, res) => {
  const key = process.env.SEOUL_API_KEY;
  if (!key) return send(res, 500, { error: "SEOUL_API_KEY 환경변수가 없습니다" });
  try {
    const d = await getJSON(`http://openapi.seoul.go.kr:8088/${key}/json/citydata/1/5/${encodeURIComponent("올림픽공원")}`, { timeoutMs: 15000 });
    const w = ((d.CITYDATA || {}).WEATHER_STTS || [{}])[0] || {};
    const hours = (w.FCST24HOURS || []).map((f) => {
      const s = String(f.FCST_DT || "");
      if (!/^\d{10}/.test(s)) return null;
      const temp = Number(f.TEMP);
      return {
        date: `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`, hour: Number(s.slice(8, 10)),
        temp: Number.isFinite(temp) ? temp : null,
        precip: rainMm(f.PRECIPITATION, f.PRECPT_TYPE), type: f.PRECPT_TYPE || null,
        chance: f.RAIN_CHANCE != null && f.RAIN_CHANCE !== "" ? Number(f.RAIN_CHANCE) : null, sky: f.SKY_STTS || null,
      };
    }).filter(Boolean);
    send(res, 200, {
      time: nowKST(), weatherTime: w.WEATHER_TIME || null,
      now: { temp: w.TEMP != null && w.TEMP !== "" ? Number(w.TEMP) : null, type: w.PRECPT_TYPE || null, msg: w.PCP_MSG || null },
      hours, source: "서울시 실시간 도시데이터(올림픽공원) 날씨 예보",
    }, 600);
  } catch (e) {
    send(res, 502, { error: "서울시 도시데이터 실패: " + e.message });
  }
};
