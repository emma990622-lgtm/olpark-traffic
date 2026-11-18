// GET /api/drivetime
// 환승주차 역 주차장 4곳 → 올림픽공원 주차장, 지금 자동차로 몇 분 (TMAP 자동차 경로, 실시간 교통 반영)
// TMAP_APP_KEY 환경변수가 있을 때만 동작(선택 기능). 10분 동안 모든 사용자에게 같은 값을 줘서 호출 수를 아낀다.
const { send, nowKST } = require("./_util");

const PARK = [127.126027, 37.517033];   // 올림픽공원 주차장 [경도, 위도]
const LOTS = {                            // TMAP 주소 검색 좌표 (2026-11-18)
  "천호역 공영주차장": [127.125127, 37.538509],
  "잠실역 공영주차장": [127.103362, 37.514223],
  "복정역 공영주차장": [127.127776, 37.470021],
  "신천유수지 공영주차장": [127.103012, 37.522408],
};

async function route(key, a) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 8000);
  try {
    const r = await fetch("https://apis.openapi.sk.com/tmap/routes?version=1&format=json", {
      method: "POST", signal: ctrl.signal,
      headers: { appKey: key, "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ startX: String(a[0]), startY: String(a[1]), endX: String(PARK[0]), endY: String(PARK[1]),
        reqCoordType: "WGS84GEO", resCoordType: "WGS84GEO", searchOption: "0", trafficInfo: "N" }),
    });
    if (!r.ok) throw new Error("HTTP " + r.status);
    const p = (await r.json()).features[0].properties;
    return { min: Math.round(p.totalTime / 60), km: +(p.totalDistance / 1000).toFixed(1) };
  } finally { clearTimeout(t); }
}

module.exports = async (req, res) => {
  const key = (process.env.TMAP_APP_KEY || "").trim();
  if (!key) return send(res, 501, { error: "TMAP 키가 등록되지 않았습니다(선택 기능)" });
  const out = { time: nowKST(), lots: {} };
  await Promise.all(Object.entries(LOTS).map(async ([name, a]) => {
    try { out.lots[name] = await route(key, a); } catch (e) { out.lots[name] = { error: e.message }; }
  }));
  send(res, 200, out, 600);
};
