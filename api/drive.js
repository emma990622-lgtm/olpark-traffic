// GET /api/drive?lat=37.50&lng=127.03&to=park|chunho|jamsil|bokjeong
// 출발지 → 주차장 운전 시간 (네이버 Directions 5, 실시간 교통 반영)
// 무료 사용량을 아끼려고 출발지를 소수 둘째 자리(약 1km 격자)로 묶고, 결과를 15분 동안 공유한다.
const { getJSON, send } = require("./_util");

const DEST = {
  park: [127.126027, 37.517033],     // 올림픽공원 주차장
  chunho: [127.125127, 37.538509],   // 천호역 공영주차장 (TMAP 주소 검색, 2026-11-18)
  jamsil: [127.103362, 37.514223],   // 잠실역 공영주차장 (TMAP 주소 검색, 2026-11-18)
  bokjeong: [127.127776, 37.470021], // 복정역 공영주차장 (TMAP 주소 검색, 2026-11-18)
};

module.exports = async (req, res) => {
  const id = process.env.NAVER_KEY_ID, secret = process.env.NAVER_KEY;
  if (!id || !secret) return send(res, 501, { error: "네이버 키가 아직 등록되지 않았습니다(선택 기능)" });
  const lat = Number(req.query.lat), lng = Number(req.query.lng), to = String(req.query.to || "park");
  if (!(to in DEST)) return send(res, 400, { error: "모르는 목적지" });
  if (!DEST[to]) return send(res, 501, { error: "이 주차장 좌표가 아직 입력되지 않았습니다" });
  if (!(lat > 33 && lat < 39) || !(lng > 124 && lng < 132)) return send(res, 400, { error: "잘못된 요청" });
  const start = `${lng.toFixed(2)},${lat.toFixed(2)}`;
  const goal = DEST[to].join(",");
  try {
    const d = await getJSON(`https://maps.apigw.ntruss.com/map-direction/v1/driving?start=${start}&goal=${goal}&option=traoptimal`, {
      headers: { "x-ncp-apigw-api-key-id": id, "x-ncp-apigw-api-key": secret },
    });
    const s = (((d.route || {}).traoptimal || [])[0] || {}).summary;
    if (!s) return send(res, 502, { error: "경로 없음", code: d.code, message: d.message });
    send(res, 200, { to, start, minutes: Math.round(s.duration / 60000), km: +(s.distance / 1000).toFixed(1) }, 900);
  } catch (e) {
    send(res, 502, { error: "네이버 길찾기 실패: " + e.message });
  }
};
