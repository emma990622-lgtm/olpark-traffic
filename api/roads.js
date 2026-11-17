// GET /api/roads
// 서울시 실시간 도시데이터(올림픽공원): 도로 58구간 속도, 근처 주차장, 지하철역 도착, 날씨
const { getJSON, send, nowKST } = require("./_util");

module.exports = async (req, res) => {
  const key = process.env.SEOUL_API_KEY;
  if (!key) return send(res, 500, { error: "SEOUL_API_KEY 환경변수가 없습니다" });
  try {
    const d = await getJSON(`http://openapi.seoul.go.kr:8088/${key}/json/citydata/1/5/${encodeURIComponent("올림픽공원")}`, { timeoutMs: 15000 });
    const c = d.CITYDATA || {};
    const road = c.ROAD_TRAFFIC_STTS || {};
    const avg = road.AVG_ROAD_DATA || {};
    const w = (c.WEATHER_STTS || [{}])[0];
    send(res, 200, {
      time: nowKST(),
      roadTime: avg.ROAD_TRAFFIC_TIME || null,
      avgSpeed: avg.ROAD_TRAFFIC_SPD != null ? Number(avg.ROAD_TRAFFIC_SPD) : null,
      avgLevel: avg.ROAD_TRAFFIC_IDX || null,
      links: (road.ROAD_TRAFFIC_STTS || []).map((r) => ({ id: String(r.LINK_ID), spd: Number(r.SPD), idx: r.IDX })),
      nearLots: (c.PRK_STTS || []).map((p) => ({
        name: p.PRK_NM, cap: Number(p.CPCTY) || null,
        now: p.CUR_PRK_CNT === "" ? null : Number(p.CUR_PRK_CNT), live: p.CUR_PRK_YN === "Y",
      })),
      subway: (c.SUB_STTS || []).map((s) => ({
        name: s.SUB_STN_NM, line: s.SUB_STN_LINE,
        arrivals: (s.SUB_DETAIL || []).slice(0, 4).map((a) => ({ to: a.SUB_ROUTE_NM, msg: a.SUB_ARMG1 })),
      })),
      weather: { temp: w.TEMP ?? null, rain: w.PRECPT_TYPE ?? null },
    }, 180);   // 도로 정보는 5분마다 바뀌므로 3분 공유
  } catch (e) {
    send(res, 502, { error: "서울시 도시데이터 실패: " + e.message });
  }
};
