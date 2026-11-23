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
  p.venues = { "KSPO DOME": { name: "KSPO DOME", lat: p.dome.lat, lng: p.dome.lng, items: null } };
  try {
    const w = await loadJSON("walk_tmap.json");
    if (w.venues) Object.entries(w.venues).forEach(([n, v]) => { p.venues[n] = { name: n, lat: v.lat, lng: v.lng, items: v.items }; });
    else p.venues["KSPO DOME"].items = w.items;            // 예전 형식(KSPO DOME만)
    applyWalk(p, p.venues["KSPO DOME"].items);
    p.walkSource = `TMAP 보행자 경로(${w.measured} 계산)`;
  } catch (_) {
    p.walkSource = "직선거리 × 1.3, 분당 75m 추정";
  }
  return p;
}

function applyWalk(p, items) {
  if (!items) return;
  [...p.lots, ...p.stations].forEach((x) => {
    const m = items[x.name];
    if (m) { x.walkMin = m.minutes; x.walkM = m.meters; x.walkSrc = "TMAP 보행자 경로"; }
  });
}

// 고른 공연장 기준으로 장소 정보를 다시 만든다 (공연장 위치 + 주차장·역에서 걷는 시간)
// 측정값이 없는 공연장은 직선거리 × 1.3, 분당 75m로 추정. 위치조차 모르면 KSPO DOME 기준.
function placesFor(p, venueName) {
  const v = p.venues[venueName] || (venueName === "뮤즈라이브" ? p.venues["올림픽홀"] : null);
  const base = p.venues["KSPO DOME"];
  const q = JSON.parse(JSON.stringify({ lots: p.lots, stations: p.stations }));
  const out = { ...p, ...q, venueName, venueKnown: !!v };
  const tgt = v || base;
  out.dome = { name: v ? venueName : "KSPO DOME", lat: tgt.lat, lng: tgt.lng };
  if (tgt.items) {
    applyWalk(out, tgt.items);
    out.walkSource = p.walkSource;
  } else if (v) {
    [...out.lots, ...out.stations].forEach((x) => {
      if (!x.lat) return;
      const k = Math.cos(x.lat * Math.PI / 180);
      const m = Math.hypot((x.lng - tgt.lng) * 111320 * k, (x.lat - tgt.lat) * 110540) * 1.3;
      x.walkM = Math.round(m); x.walkMin = Math.max(1, Math.round(m / 75)); x.walkSrc = "추정";
    });
    out.walkSource = `${venueName}까지는 직선거리 × 1.3, 분당 75m 추정 (TMAP 계산 전)`;
  }
  return out;
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

// ---------- 지하철 시간 ----------
// 운행: 서울교통공사 역간 표준 운행시간(/api/subway) + 중간역 정차 30초씩. 못 받으면 정거장당 2분 가정.
// 개찰·대기 5분, 환승 5분은 가정값.
const SUBWAY = { perStopMin: 2, dwellMin: 0.5, waitMin: 5, transferMin: 5, official: null };

async function loadSubwayTimes() {
  try {
    const j = await fetch("/api/subway").then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); });
    const byLine = {};
    (j.rows || []).forEach((r, i) => {
      const [m, sec] = String(r.HM).split(":").map(Number);
      (byLine[r.SBWY_ROUT_LN] = byLine[r.SBWY_ROUT_LN] || []).push({ name: r.SBWY_STNS_NM, min: m + (sec || 0) / 60, i });
    });
    SUBWAY.official = byLine;
  } catch (_) { SUBWAY.official = null; }
}

// 한 호선에서 역 순서대로 탄 운행시간(분). 표의 HM은 '앞 행 역에서 이 역까지' 시간이므로,
// 이웃한 두 역 중 표에서 뒤에 나오는 역의 HM이 그 구간 시간이다.
function segmentMinutes(line, stations) {
  const rows = SUBWAY.official && SUBWAY.official[line];
  if (!rows) return null;
  let sum = 0;
  for (let k = 0; k + 1 < stations.length; k++) {
    const a = rows.find((r) => r.name === stations[k]), b = rows.find((r) => r.name === stations[k + 1]);
    if (!a || !b) return null;
    sum += (b.i > a.i ? b : a).min;
  }
  return sum + Math.max(0, stations.length - 2) * SUBWAY.dwellMin;
}

function subwayNote() {
  return SUBWAY.official
    ? "지하철 운행시간은 서울교통공사 역간 표준 운행시간(정차 30초씩 포함)이고, 개찰·대기 5분·환승 5분은 가정값이에요"
    : "지하철 운행은 정거장당 2분, 개찰·대기 5분, 환승 5분으로 가정한 값이에요";
}

// 환승주차 총 이동시간: 주차장→역 도보 + 대기 + 운행 + 환승 + 내린 역→공연장 도보
function transferTotal(lot, station) {
  if (lot.toStationMin == null || !station || lot.stops == null) return null;
  let ride = null;
  if (SUBWAY.official && lot.segments && lot.segments.length) {
    const parts = lot.segments.map((sg) => segmentMinutes(sg.line, sg.stations));
    if (parts.every((x) => x != null)) ride = parts.reduce((a, b) => a + b, 0);
  }
  const official = ride != null;
  if (!official) ride = lot.stops * SUBWAY.perStopMin;
  const parts = {
    walk1: lot.toStationMin, wait: SUBWAY.waitMin, ride: Math.round(ride),
    transfer: (lot.transfers || 0) * SUBWAY.transferMin, walk2: station.walkMin,
  };
  return { total: Object.values(parts).reduce((a, b) => a + b, 0), official, ...parts };
}

// ---------- 공연 끝나고 나올 때 (사람이 한꺼번에 몰리는 경우) ----------
// 근거: 서울시 역별 일별 승하차(CardSubwayStatsNew, 2026-03~11)에서 KSPO DOME 공연일 31일의 승차 인원을
// 같은 요일 종류(금요일/주말)의 공연 없는 날(±6주) 중앙값과 비교한 '늘어난 승차 인원'.
//   1만 5천 석 공연 1회 → 올림픽공원역에서 약 8,400명 더 탐(보통 4,000~10,300명). 9호선 71%, 5호선 29%.
//   몽촌토성역·한성백제역은 거의 늘지 않음.
// 나머지(개찰구 처리량, 열차 간격·여유 정원, 사람 많을 때 걷는 속도)는 가정값이고, 공연일 실측으로 고친다.
const CROWD = {
  riders: { med: 8400, high: 10300, seats: 15000 },          // KSPO DOME 1회 기준, 좌석 수에 비례
  share: { olympic5: { "5": 0.29, "9": 0.71 }, mongchon: { "8": 0.005 }, hanseong: { "9": 0.005 } },
  dirShare: 0.8,          // 그 호선 승객 중 내가 탈 방향 비율(가정)
  spreadMin: 20,          // 관객이 역에 도착하는 시간 폭(가정)
  gatePerMin: 250,        // 역 개찰구·계단 처리량, 명/분(가정)
  linePerMin: { "5": 150, "8": 125, "9": 200, "2": 250 },   // 열차가 실어 나르는 양, 명/분(가정)
  headway: { "5": 10, "8": 8, "9": 6, "2": 6 },             // 밤 시간 열차 간격, 분(가정)
  walkFactor: 1.3,        // 인파가 몰리는 역으로 걸을 때 평소보다 30% 느리게(그 밖의 역은 10%, 가정)
  lotExit: 3,             // 역 공영주차장 정산·출차(한산)
  source: "서울시 역별 일별 승하차 인원(2026년 3~11월, KSPO DOME 공연일 31일)",
};

// 나올 때: (인파 속) 공연장에서 역까지 도보 + 개찰·승강장 대기 + 운행 + 환승 + 역→주차장 도보 + 출차
function transferOut(lot, station, ev, level = "med") {
  if (lot.toStationMin == null || !station || !lot.segments || !lot.segments.length) return null;
  const go = transferTotal(lot, station);
  if (!go) return null;
  const line = lot.segments.at(-1).line;                       // 공연장 쪽에서 타는 호선
  const scale = (ev.seats || CROWD.riders.seats) / CROWD.riders.seats;
  const R = CROWD.riders[level] * scale;                       // 공원 근처 역으로 몰리는 사람
  const sh = CROWD.share[lot.station] || {};
  const T = CROWD.spreadMin;
  const atStation = R * Object.values(sh).reduce((a, b) => a + b, 0);
  const onLine = R * (sh[line] || 0) * CROWD.dirShare;
  const q = (lam, mu) => Math.max(0, lam - mu) * (T / 2) / mu;   // 가운데쯤 도착한 사람이 줄 서는 분
  const gateWait = q(atStation / T, CROWD.gatePerMin);
  const lineWait = q(Math.min(onLine / T, CROWD.gatePerMin), CROWD.linePerMin[line] || 150);
  const parts = {
    walk2: Math.round(station.walkMin * (atStation > 1000 ? CROWD.walkFactor : 1.1)),   // 인파가 가는 역이면 더 느리게
    crowd: Math.round(gateWait + lineWait),
    wait: Math.round((CROWD.headway[line] || 8) / 2),
    ride: go.ride, transfer: go.transfer, walk1: go.walk1, lotExit: CROWD.lotExit,
  };
  return { total: Object.values(parts).reduce((a, b) => a + b, 0), riders: Math.round(atStation), ...parts };
}

// ---------- 공원 주차 합계 보정 ----------
// 한국체육산업개발 실시간 주차현황(parking_sum)은 출차 기록이 없는 장기 주차까지 세어 실제보다 많게 나온다
// (공공데이터포털 설명: 장기 주차는 종료일이 표기되지 않아 실제 주차대수가 정확하지 않을 수 있음).
// 차량 이용현황(문화 빅데이터 플랫폼, 2025-10~12월 82일)으로 새벽 4시 30분에 동2·남2·북2문 구역에 실제로 서 있던 차를 세면
// 중앙값 225대(134~267대, 그중 24시간 넘게 머문 차 약 100대). 같은 때 실시간 값은 1,000~1,130대.
// → 새벽 값에서 225대를 뺀 만큼(약 800~900대)을 '출차 기록이 안 닫혀 실제로는 없는 차'로 보고 실시간 값에서 뺀다.
//   (2026-11-21까지는 2024년 7월 입출차 기록으로 본 60대를 썼음)
//   새벽 값이 매일 쌓이면(수집기 data/parking_night.csv) 가장 최근 값을 쓴다.
const PARK_NIGHT_DEFAULT = { date: "2026-11-18", time: "00:33", sum: 1085 };
const PARK_NIGHT_TRUE = 225;
let _parkNight = null;
async function loadParkNight() {
  if (_parkNight) return _parkNight;
  try {
    const t = await fetch(`https://raw.githubusercontent.com/${CONFIG.collectorRepo}/main/data/parking_night.csv`).then((r) => { if (!r.ok) throw 0; return r.text(); });
    const rows = parseCSV(t).filter((r) => +r.parking_sum > 0);
    const last = rows.at(-1);
    _parkNight = last ? { date: last.date, time: last.time, sum: +last.parking_sum } : PARK_NIGHT_DEFAULT;
  } catch (_) { _parkNight = PARK_NIGHT_DEFAULT; }
  return _parkNight;
}
// 실시간 값 → 실제에 가까운 대수
function parkActual(sum, night = _parkNight || PARK_NIGHT_DEFAULT) {
  const ghost = Math.max(0, night.sum - PARK_NIGHT_TRUE);
  return { est: Math.max(0, Math.round(sum - ghost)), ghost, night };
}

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

// ---------- 공연 규모 → 대응 수준 ----------
function levelOf(totalSeats) {
  if (totalSeats >= 10000) return { key: "focus", label: "집중", cls: "bad", sym: "■" };
  if (totalSeats >= 3000) return { key: "caution", label: "주의", cls: "warn", sym: "▲" };
  return { key: "normal", label: "평소", cls: "good", sym: "●" };
}

// 호선 문자열("5·9호선", "8호선" 등) → 노선 색 배지 HTML
function lineBadgesHTML(lineStr) {
  if (!lineStr) return "";
  const nums = String(lineStr).match(/\d+/g);
  if (!nums || !nums.length) return `<span class="line-badge">${lineStr}</span>`;
  return nums.map((n) => `<span class="line-badge l${n}">${n}호선</span>`).join(" ");
}

// ---------- KSPO DOME 출차 최대 참고값 ----------
// 공연 시작부터 15분 출차가 가장 많았던 때까지 걸린 분, 그때 대수.
// kspo_waves.json(2024년 7월 + 2025년, scripts/16)이 있으면 그것을, 없으면 exits_2024_07.json(2024년 7월만)을 쓴다.
function kspoReference(exits, waves) {
  if (waves && waves.summary && waves.summary.n) {
    const s = waves.summary;
    return { n: s.n, lagMed: s.lagMed, lagMin: s.lagLo, lagMax: s.lagHi, peakMin: s.peakLo, peakMax: s.peakHi,
             label: waves.label || `${s.n}회`, rangeNote: s.rangeNote || "" };
  }
  const w = Object.values((exits && exits.kspoWaves) || {});
  if (!w.length) return { n: 0, lagMed: 0, lagMin: 0, lagMax: 0, peakMin: 0, peakMax: 0, label: "기록 없음", rangeNote: "" };
  const lags = w.map((x) => x.lagMin).sort((a, b) => a - b);
  const peaks = w.map((x) => x.peak15).sort((a, b) => a - b);
  const med = (a) => a.length % 2 ? a[(a.length - 1) / 2] : (a[a.length / 2 - 1] + a[a.length / 2]) / 2;
  return { n: w.length, lagMed: med(lags), lagMin: lags[0], lagMax: lags.at(-1),
           peakMin: peaks[0], peakMax: peaks.at(-1), label: `2024년 7월 ${w.length}회`, rangeNote: "공연별 최소~최대" };
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
      roadTime: r.roadTime || r.time, roads, links: r.links || [],
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

// ---------- 공연일 자동 수집 결과 (GitHub 공개 저장소) ----------
let _folderCache = null;
async function listCollectedFolders() {
  if (_folderCache) return _folderCache;
  const api = `https://api.github.com/repos/${CONFIG.collectorRepo}/contents/data`;
  const list = await fetch(api).then((r) => { if (!r.ok) throw new Error("GitHub " + r.status); return r.json(); });
  _folderCache = list.filter((x) => x.type === "dir").map((x) => x.name).sort();
  return _folderCache;
}

function parseCSV(t) {
  const rows = t.replace(/^\uFEFF/, "").trim().split("\n").map((l) => l.replace(/\r$/, "").split(","));
  const h = rows[0];
  return rows.slice(1).map((r) => Object.fromEntries(h.map((k, i) => [k, r[i]])));
}

// 한 수집 폴더의 summary.csv + roads.csv
async function loadCollectedFolder(folder) {
  const raw = `https://raw.githubusercontent.com/${CONFIG.collectorRepo}/main/data/${folder}/`;
  const [s, r] = await Promise.all(["summary.csv", "roads.csv"].map((f) => fetch(raw + f).then((x) => (x.ok ? x.text() : ""))));
  return { folder, summary: s ? parseCSV(s) : [], roads: r ? parseCSV(r) : [] };
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
  dot(places.dome.lng, places.dome.lat, "var(--accent)", 9, places.dome.name || "KSPO DOME");
}

function legendHTML() {
  return `<div class="legend">
    <span><i style="background:var(--good)"></i>● 원활</span>
    <span><i style="background:var(--warn)"></i>▲ 서행</span>
    <span><i style="background:var(--bad)"></i>■ 정체</span>
    <span><i style="background:var(--none)"></i>— 수집값 없음</span>
    <span>● 보라: 지하철역 · 회색: 주차장</span></div>`;
}

// 공연을 날짜별로 묶기
function groupByDate(events) {
  const m = new Map();
  events.forEach((e) => { if (!m.has(e.date)) m.set(e.date, []); m.get(e.date).push(e); });
  return m;
}
