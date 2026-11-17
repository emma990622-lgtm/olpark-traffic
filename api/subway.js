// GET /api/subway
// 서울교통공사 1~8호선 역간 거리 및 소요시간 (서울시 StationDstncReqreTimeHm)
// 표준 운행시간이라 자주 바뀌지 않으므로 하루 동안 공유한다.
const { getJSON, send, nowKST } = require("./_util");

module.exports = async (req, res) => {
  const key = process.env.SEOUL_API_KEY;
  if (!key) return send(res, 500, { error: "SEOUL_API_KEY 환경변수가 없습니다" });
  try {
    const rows = [];
    for (let a = 1; a <= 3001; a += 1000) {
      const d = await getJSON(`http://openapi.seoul.go.kr:8088/${key}/json/StationDstncReqreTimeHm/${a}/${a + 999}/`, { timeoutMs: 15000 });
      const svc = d.StationDstncReqreTimeHm || {};
      const r = svc.row || [];
      if (!r.length) {
        if (a === 1) return send(res, 502, { error: "응답에 데이터가 없습니다", raw: d });
        break;
      }
      rows.push(...r);
      if (rows.length >= Number(svc.list_total_count || 0)) break;
    }
    send(res, 200, { time: nowKST(), count: rows.length, fields: Object.keys(rows[0] || {}), rows }, 86400);
  } catch (e) {
    send(res, 502, { error: "역간 소요시간 조회 실패: " + e.message });
  }
};
