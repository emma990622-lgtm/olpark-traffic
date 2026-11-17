// GET /api/parking
// 올림픽공원 주차 합계(한국체육산업개발) + 송파·강동 공영주차장 실시간 빈자리(서울시 GetParkingInfo)
const { getJSON, send, nowKST } = require("./_util");

const KSPO = "https://www.ksponco.or.kr/online/main/parkingorsApi.do?apiKey=PARKING21803504";
const GUS = ["송파구", "강동구"];

module.exports = async (req, res) => {
  const key = process.env.SEOUL_API_KEY;
  if (!key) return send(res, 500, { error: "SEOUL_API_KEY 환경변수가 없습니다" });

  const out = { time: nowKST(), kspo: null, lots: [], errors: [] };

  const kspo = getJSON(KSPO).then((p) => {
    const x = Array.isArray(p) ? p[0] : p;
    out.kspo = { parking_sum: x && x.parking_sum != null ? Number(x.parking_sum) : null };
  }).catch((e) => out.errors.push("kspo: " + e.message));

  const seoul = Promise.all(GUS.map((gu) =>
    getJSON(`http://openapi.seoul.go.kr:8088/${key}/json/GetParkingInfo/1/1000/${encodeURIComponent(gu)}`)
      .then((d) => ((d.GetParkingInfo || {}).row || []).filter((r) => String(r.ADDR || "").includes(gu)))
      .catch((e) => { out.errors.push(`${gu}: ${e.message}`); return []; })
  )).then((lists) => {
    out.lots = lists.flat().map((r) => {
      const cap = Number(r.TPKCT) || null, now = r.NOW_PRK_VHCL_CNT === "" ? null : Number(r.NOW_PRK_VHCL_CNT);
      return {
        name: String(r.PKLT_NM || "").replace("(시)", "").trim(),
        addr: r.ADDR, cap, now,
        free: cap != null && now != null ? Math.max(0, cap - now) : null,
        updated: r.NOW_PRK_VHCL_UPDT_TM || null,
        live: r.PRK_STTS_YN === "1" || r.PRK_STTS_YN === 1,
        weekdayHours: `${r.WD_OPER_BGNG_TM || ""}~${r.WD_OPER_END_TM || ""}`,
        weekendHours: `${r.WE_OPER_BGNG_TM || ""}~${r.WE_OPER_END_TM || ""}`,
        feeWon: Number(r.BSC_PRK_CRG) || null, feeMin: Number(r.BSC_PRK_HR) || null,
      };
    });
  });

  await Promise.all([kspo, seoul]);
  send(res, 200, out, 120);   // 2분 동안 같은 값 공유
};
