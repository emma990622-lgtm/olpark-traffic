// 중계 서버 공통 함수 (Vercel Functions, Node 18+)
// 인증키는 Vercel 환경변수에만 둔다. 코드와 웹 화면에는 절대 넣지 않는다.

async function getJSON(url, { headers = {}, timeoutMs = 9000 } = {}) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(url, { headers, signal: ctrl.signal });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return await r.json();
  } finally {
    clearTimeout(t);
  }
}

// s-maxage: Vercel이 응답을 이 초만큼 저장해 두고 모든 사용자에게 같은 값을 준다
// → 관객이 많아도 원본 API 호출 수는 늘지 않는다.
function send(res, status, body, cacheSec) {
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Access-Control-Allow-Origin", "*");
  if (cacheSec) res.setHeader("Cache-Control", `public, s-maxage=${cacheSec}, stale-while-revalidate=${cacheSec}`);
  res.status(status).send(JSON.stringify(body));
}

const nowKST = () => new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 19).replace("T", " ");

module.exports = { getJSON, send, nowKST };
