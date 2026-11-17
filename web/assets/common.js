// 관객·운영자 화면이 함께 쓰는 함수들
const CONFIG = {
  // 공연일 자동 수집 결과가 쌓이는 공개 저장소 (GitHub Actions)
  collectorRepo: "emma990622-lgtm/olpark-collector",
  dataDir: "data/",
};

async function loadJSON(name) {
  const r = await fetch(CONFIG.dataDir + name);
  if (!r.ok) throw new Error(name + " 불러오기 실패");
  return r.json();
}

// 장소 + TMAP 실제 도보 경로값(있으면 직선 추정값 대신 사용)
async function loadPlaces() {
  const p = await loadJSON("places.json");
  try {
    const w = await loadJSON("walk_tmap.json");
    [...p.lots, ...p.stations].forEach((x) => {
      const m = w.items[x.name];
      if (m) { x.walkMin = m.minutes; x.walkM = m.meters; x.walkSrc = "TMAP 보행자 경로"; }
    });
    p.walkSource = `TMAP 보행자 경로(${w.measured} 계산)`;
  } catch (_) {
    p.walkSource = "직선거리 × 1.3, 분당 75m 추정";
  }
  return p;
}

// ---------- 시간 ----------
const toMin = (hhmm) => { const [h, m] = hhmm.split(":").map(Number); return h * 60 + m; };
const toHHMM = (min) => {
  const m = ((Math.round(min) % 1440) + 1440) % 1440;
  return String(Math.floor(m / 60)).padStart(2, "0") + ":" + String(m % 60).padStart(2, "0");
};
const durText = (min) => {
  const h = Math.floor(min / 60), m = Math.round(min % 60);
  return (h ? h + "시간 " : "") + (m ? m + "분" : (h ? "" : "0분"));
};
const won = (n) => n == null ? "-" : n.toLocaleString("ko-KR") + "원";
const DOW = ["일", "월", "화", "수", "목", "금", "토"];

// 공연 길이는 공연마다 다르다. 기본값 150분, 화면에서 바꿀 수 있다.
const DEFAULT_SHOW_MIN = 150;

// ---------- 요금 ----------
function parkingFee(lot, minutes) {
  if (!lot.won || !lot.per) return null;
  let fee = Math.ceil(minutes / lot.per) * lot.won;
  if (lot.dayMax) fee = Math.min(fee, lot.dayMax);
  return fee;
}

// 운영시간 "05:00~01:00" → 이 시각(분, 0~1440+)에 열려 있나
function openAt(hours, minOfDay) {
  if (!hours || hours === "24시간") return true;
  const [a, b] = hours.split("~").map(toMin);
  const end = b <= a ? b + 1440 : b;
  const t = minOfDay < a ? minOfDay + 1440 : minOfDay;
  return t >= a && t <= end;
}

// ---------- 공연 규모 → 대응 수준 (예측 모델 연결 전 규칙) ----------
function levelOf(totalSeats) {
  if (totalSeats >= 10000) return { key: "focus", label: "집중", cls: "bad" };
  if (totalSeats >= 3000) return { key: "caution", label: "주의", cls: "warn" };
  return { key: "normal", label: "평소", cls: "" };
}

// ---------- 2024년 7월 참고값 ----------
// KSPO DOME 공연 7회: 공연 시작부터 15분 출차가 가장 많았던 때까지 걸린 분, 그때 대수
function kspoReference(exits) {
  const w = Object.values(exits.kspoWaves);
  const lags = w.map((x) => x.lagMin).sort((a, b) => a - b);
  const peaks = w.map((x) => x.peak15).sort((a, b) => a - b);
  const med = (a) => a.length % 2 ? a[(a.length - 1) / 2] : (a[a.length / 2 - 1] + a[a.length / 2]) / 2;
  return { n: w.length, lagMed: med(lags), lagMin: lags[0], lagMax: lags.at(-1),
           peakMin: peaks[0], peakMax: peaks.at(-1) };
}

// ---------- 최근 수집값 (GitHub 공개 저장소에서 읽기) ----------
// 공연일에만 수집하므로, 수집이 없는 날에는 가장 최근 수집 폴더의 마지막 값을 보여 준다.
async function loadLatestCollection() {
  const api = `https://api.github.com/repos/${CONFIG.collectorRepo}/contents/data`;
  const raw = `https://raw.githubusercontent.com/${CONFIG.collectorRepo}/main/data/`;
  const list = await fetch(api).then((r) => { if (!r.ok) throw new Error("GitHub " + r.status); return r.json(); });
  const folders = list.filter((x) => x.type === "dir").map((x) => x.name).sort();
  if (!folders.length) return null;
  const folder = folders.at(-1);
  const get = (f) => fetch(raw + folder + "/" + f).then((r) => (r.ok ? r.text() : ""));
  const [roadsTxt, sumTxt, lotsTxt] = await Promise.all([get("roads.csv"), get("summary.csv"), get("parking_lots.csv")]);
  const rows = (t) => t.replace(/^﻿/, "").trim().split("\n").map((l) => l.split(","));
  // 도로: 마지막 수집시각의 행만
  const roads = {};
  let roadTime = null;
  if (roadsTxt) {
    const r = rows(roadsTxt).slice(1);
    roadTime = r.at(-1)[0];
    r.filter((x) => x[0] === roadTime).forEach((x) => { roads[x[2]] = { spd: +x[7], idx: x[8] }; });
  }
  let summary = null;
  if (sumTxt) {
    const r = rows(sumTxt); const h = r[0]; const last = r.at(-1);
    summary = Object.fromEntries(h.map((k, i) => [k, last[i]]));
  }
  const lots = {};
  if (lotsTxt) {
    const r = rows(lotsTxt).slice(1);
    const t = r.at(-1)[0];
    r.filter((x) => x[0] === t).forEach((x) => { lots[x[2]] = { cap: +x[6], now: +x[7], time: x[8] }; });
  }
  return { folder, roadTime, roads, summary, lots };
}


// ---------- 실시간 (중계 서버 /api) → 안 되면 GitHub 저장값 ----------
// Vercel에 올리면 /api/parking, /api/roads 가 서울시·한국체육산업개발 API를 실시간으로 중계한다.
// 내 PC(run_web.bat)에서는 /api 가 없으므로 GitHub에 저장된 최근 수집값을 쓴다.
async function loadLive() {
  try {
    const [p, r] = await Promise.all([
      fetch("/api/parking").then((x) => { if (!x.ok) throw new Error("parking " + x.status); return x.json(); }),
      fetch("/api/roads").then((x) => { if (!x.ok) throw new Error("roads " + x.status); return x.json(); }),
    ]);
    const roads = {};
    (r.links || []).forEach((l) => { roads[l.id] = { spd: l.spd, idx: l.idx }; });
    const lots = {};
    (p.lots || []).forEach((l) => { lots[l.name] = { cap: l.cap, now: l.now, time: l.updated || p.time }; });
    return {
      source: "live", folder: "실시간",
      roadTime: r.roadTime || r.time, roads,
      summary: { "주차합계_parking_sum": p.kspo ? p.kspo.parking_sum : "-", "수집시각": p.time },
      lots, subway: r.subway || [], weather: r.weather || null,
    };
  } catch (e) {
    const g = await loadLatestCollection();
    if (g) g.source = "saved";
    return g;
  }
}

function liveNote(live) {
  if (!live) return "수집값이 없어요.";
  return live.source === "live"
    ? `실시간: 도로 ${live.roadTime} 기준, 주차 ${live.summary["수집시각"].slice(11, 16)} 기준 (2~3분마다 갱신)`
    : `저장된 최근 수집값: ${live.roadTime} (${live.folder}). 인터넷에 올린 버전에서는 실시간으로 바뀌어요.`;
}

// ---------- 도로 지도 (SVG, 지도 타일 없이) ----------
const IDX_COLOR = { "원활": "var(--good)", "서행": "var(--warn)", "정체": "var(--bad)" };

function drawRoadMap(svg, links, places, roads) {
  const pts = [];
  links.forEach((l) => { pts.push(l.a, l.b); });
  places.lots.filter((x) => x.lat && x.kind !== "transfer").forEach((x) => pts.push([x.lng, x.lat]));
  places.stations.forEach((x) => pts.push([x.lng, x.lat]));
  const lngs = pts.map((p) => p[0]), lats = pts.map((p) => p[1]);
  const pad = 0.002;
  const minX = Math.min(...lngs) - pad, maxX = Math.max(...lngs) + pad;
  const minY = Math.min(...lats) - pad, maxY = Math.max(...lats) + pad;
  const k = Math.cos((minY + maxY) / 2 * Math.PI / 180);
  const W = 760, H = Math.round(W * (maxY - minY) / ((maxX - minX) * k));
  const X = (lng) => ((lng - minX) / (maxX - minX)) * W;
  const Y = (lat) => H - ((lat - minY) / (maxY - minY)) * H;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  const ns = "http://www.w3.org/2000/svg";
  const el = (tag, attrs, text) => {
    const e = document.createElementNS(ns, tag);
    Object.entries(attrs).forEach(([a, v]) => e.setAttribute(a, v));
    if (text != null) e.textContent = text;
    svg.appendChild(e); return e;
  };
  svg.innerHTML = "";
  links.forEach((l) => {
    const r = roads && roads[l.id];
    const line = el("line", {
      x1: X(l.a[0]), y1: Y(l.a[1]), x2: X(l.b[0]), y2: Y(l.b[1]),
      stroke: r ? (IDX_COLOR[r.idx] || "var(--none)") : "var(--none)",
      "stroke-width": 5, "stroke-linecap": "round", opacity: 0.9,
    });
    const t = document.createElementNS(ns, "title");
    t.textContent = `${l.road} ${l.from}→${l.to}` + (r ? ` · ${r.spd}km/h ${r.idx}` : " · 수집값 없음");
    line.appendChild(t);
  });
  const dot = (lng, lat, color, r, label, dy = -9) => {
    el("circle", { cx: X(lng), cy: Y(lat), r, fill: color, stroke: "#fff", "stroke-width": 2 });
    if (label) el("text", { x: X(lng), y: Y(lat) + dy, "text-anchor": "middle", "font-size": 12, fill: "var(--ink)", "font-weight": 600 }, label);
  };
  places.lots.filter((x) => x.lat && x.kind !== "transfer").forEach((x) => dot(x.lng, x.lat, "var(--ink-2)", 5, x.kind === "park" ? "공원 주차장" : x.name.replace(" 주차장", "").replace("올림픽공원 ", ""), 16));
  places.stations.forEach((s) => dot(s.lng, s.lat, "#7b4fd6", 6, s.name));
  dot(places.dome.lng, places.dome.lat, "var(--accent)", 9, "KSPO DOME");
}

function legendHTML() {
  return `<div class="legend">
    <span><i style="background:var(--good)"></i>원활</span>
    <span><i style="background:var(--warn)"></i>서행</span>
    <span><i style="background:var(--bad)"></i>정체</span>
    <span><i style="background:var(--none)"></i>수집값 없음</span>
    <span>● 보라: 지하철역 · 회색: 주차장</span></div>`;
}

// 공연을 날짜별로 묶기
function groupByDate(events) {
  const m = new Map();
  events.forEach((e) => { if (!m.has(e.date)) m.set(e.date, []); m.get(e.date).push(e); });
  return m;
}
