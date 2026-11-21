// 운영자 화면: 공연 당일 '실시간 입출차 감지'
// 실시간 주차 대수(/api/parking, 2분마다)를 이 브라우저에 쌓아 두고(localStorage),
// 공연 전에는 관객 차 절반·90%가 들어오는 시각(과거 공연 중앙값)을 예상 선으로 보이고,
// 공연 시작 뒤 대수가 갑자기 줄기 시작하면 "출차 시작"으로 보고 관객 차 절반·90%가 빠지는 시각을 안내한다.
// 규칙·'감지 뒤 걸린 시간'·입차 시각은 scripts/14_live_exit_calib.py가 과거 입출차 기록으로 맞춘 web/data/live_exit.json.
(async function () {
  const $ = (id) => document.getElementById(id);
  if (!$("liveExit")) return;
  const POLL_MS = 120000;                     // /api/parking 이 2분 동안 같은 값을 돌려준다
  const KEY = (d) => "olpark-live-" + d;      // 날짜별 기록
  const MARK = (d) => "olpark-live-mark-" + d;

  let cfg = null, events = [];
  try { cfg = await loadJSON("live_exit.json"); } catch (_) {}
  try { events = await loadJSON("events.json"); } catch (_) {}
  if (!cfg || !cfg.rule) {
    $("leStatus").innerHTML = `<span class="chip">○ 아직 없음</span> 감지 규칙 자료(live_exit.json)를 불러오지 못했어요.`;
    return;
  }
  await loadParkNight().catch(() => null);
  const R = cfg.rule, A = cfg.after, BT = cfg.backtest, E = cfg.entry, EB = cfg.entryBacktest;   // E·EB: 입차(없을 수 있음)

  // ---------- 감지 (과거 맞춤 규칙과 같은 방식) ----------
  // pts: [{m: 공연 시작 기준 분, v: 대수}] (시간순). M = 시작 뒤 지금까지 최고 대수.
  // 시작 earliestMin분 뒤부터, windowMin분 전보다 M×ratio 이상 줄고, 4분 이상 뒤 값도 더 낮으면 감지.
  function detectExit(pts) {
    let M = -Infinity;
    for (let i = 0; i < pts.length; i++) {
      const p = pts[i];
      if (p.m >= 0) M = Math.max(M, p.v);
      if (p.m < R.earliestMin || M < R.minPeak) continue;
      let j = -1;
      for (let k = i - 1; k >= 0; k--) if (pts[k].m <= p.m - R.windowMin + 1) { j = k; break; }
      if (j < 0 || p.m - pts[j].m > R.windowMin + 6) continue;       // 비교할 값이 너무 오래전이면 건너뜀
      if (pts[j].v - p.v < R.ratio * M) continue;
      const nx = pts.slice(i + 1).find((q) => q.m >= p.m + 4);
      if (!nx) return { state: "checking", at: p, M, drop: pts[j].v - p.v };
      if (nx.v < p.v) return { state: "found", at: p, M, drop: pts[j].v - p.v };
    }
    return { state: "none", M: isFinite(M) ? M : null };
  }
  // 최근 windowMin분 변화(감시 중 표시용)
  function recentDrop(pts) {
    const p = pts.at(-1);
    if (!p) return null;
    const q = [...pts].reverse().find((x) => x.m <= p.m - R.windowMin + 1);
    return q && p.m - q.m <= R.windowMin + 6 ? q.v - p.v : null;
  }

  // ---------- 오늘 공연 ----------
  const todayKST = new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Seoul" });
  const nowMinKST = () => { const [h, m] = new Date().toLocaleTimeString("en-GB", { timeZone: "Asia/Seoul", hour12: false }).split(":").map(Number); return h * 60 + m; };
  const testStart = new URLSearchParams(location.search).get("leStart");   // 시험용: ?leStart=17:00 이면 오늘을 그 시각 공연일로 봄
  const todayShows = events.filter((e) => e.date === todayKST && e.venue === "KSPO DOME" && e.times && e.times.length);
  let show = null;
  if (testStart && /^\d{1,2}:\d{2}$/.test(testStart)) show = { title: "시험 모드", start: testStart, test: true };
  else if (todayShows.length) {
    const times = todayShows.flatMap((e) => e.times.map((t) => ({ title: e.title, start: t }))).sort((a, b) => toMin(a.start) - toMin(b.start));
    show = times.filter((x) => toMin(x.start) <= nowMinKST() + 60).at(-1) || times[0];
  }
  const startMs = show ? new Date(`${todayKST}T${show.start.padStart(5, "0")}:00+09:00`).getTime() : null;

  const store = {
    get(k) { try { return JSON.parse(localStorage.getItem(k) || "[]"); } catch (_) { return []; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (_) {} },
  };
  const livePts = () => store.get(KEY(todayKST)).map(([ms, sum]) => ({ m: (ms - startMs) / 60000, v: parkActual(sum).est, sum, ms }));

  // ---------- 지난 공연 미리 보기 목록 ----------
  const list = (cfg.list || []).filter((x) => x.series && x.series.length);
  const sel = $("leReplay");
  sel.innerHTML = `<option value="">${show ? "오늘 실시간" : "오늘 (공연 없음)"}</option>` +
    list.map((x, i) => `<option value="${i}">${x.date} 시작 ${x.start}</option>`).join("");
  const replayPts = (x) => x.series.map((v, i) => ({ m: cfg.series.fromMin + i * cfg.series.stepMin, v }));

  // ---------- 그리기 ----------
  const hhmmKST = (ms) => new Date(ms).toLocaleTimeString("en-GB", { timeZone: "Asia/Seoul", hour: "2-digit", minute: "2-digit", hour12: false });
  const atText = (m, startHHMM) => `${toHHMM(toMin(startHHMM) + m)} <span class="muted small">(시작 +${Math.round(m)}분)</span>`;
  const kpi = (label, value, cls = "") => `<div class="kpi ${cls}"><div class="l">${label}</div><div class="v">${value}</div></div>`;

  function drawChart(pts, det, startHHMM, truth) {
    const W = 760, H = 260, L = 44, Rm = 12, T = 18, B = 30;
    const maxM = Math.max(330, ...pts.map((p) => p.m)), minM = Math.min(E ? -180 : -30, ...pts.map((p) => p.m));
    const vs = pts.map((p) => p.v), maxV = Math.max(100, ...vs) * 1.1;
    const X = (m) => L + ((m - minM) / (maxM - minM)) * (W - L - Rm);
    const Y = (v) => H - B - (v / maxV) * (H - T - B);
    let g = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" font-size="11" role="img" aria-label="공연 시작 기준 주차 대수 변화">`;
    const stepV = maxV > 1200 ? 500 : maxV > 500 ? 200 : 100;
    for (let v = 0; v <= maxV; v += stepV) g += `<line x1="${L}" x2="${W - Rm}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end" fill="var(--ink-2)">${v}</text>`;
    const s0 = toMin(startHHMM);
    for (let m = Math.ceil((s0 + minM) / 60) * 60 - s0; m <= maxM; m += 60) g += `<text x="${X(m)}" y="${H - 10}" text-anchor="middle" fill="var(--ink-2)">${toHHMM(toMin(startHHMM) + m)}</text>`;
    g += `<line x1="${X(0)}" x2="${X(0)}" y1="${T}" y2="${H - B}" stroke="var(--ink-3)" stroke-dasharray="4 4"/><text x="${X(0) + 4}" y="${T + 10}" fill="var(--ink-2)">공연 시작</text>`;
    // 예상 띠(가운데 50%) + 점선(중앙값). base = 기준 분(입차는 공연 시작, 출차는 감지 시각)
    let marks = "";                                                     // 띠를 모두 먼저 그리고 선·글자는 나중에(띠가 글자를 가리지 않게)
    const band = (base, a, lbl, fill, stroke, ink, row) => (marks += `
        <line x1="${X(base + a.med)}" x2="${X(base + a.med)}" y1="${T}" y2="${H - B}" stroke="${stroke}" stroke-dasharray="2 3"/>
        <text paint-order="stroke" stroke="var(--card)" stroke-width="3" stroke-linejoin="round" x="${X(base + a.med) + 3}" y="${H - B - 6 - row * 14}" fill="${ink}" font-weight="700">${lbl}</text>`,
      `<rect x="${X(base + a.p25)}" width="${Math.max(2, X(base + a.p75) - X(base + a.p25))}" y="${T}" height="${H - T - B}" fill="${fill}"/>`);
    if (E) g += band(0, E.half, "입차 절반 예상", "var(--warn-bg)", "var(--warn)", "var(--warn-ink)", 1) + band(0, E.most, "입차 90% 예상", "var(--warn-bg)", "var(--warn)", "var(--warn-ink)", 0);
    if (det && det.at) {
      const m = det.at.m;
      g += band(m, A.half, "출차 절반 예상", "var(--accent-soft)", "var(--accent)", "var(--accent)", 1) + band(m, A.most, "출차 90% 예상", "var(--accent-soft)", "var(--accent)", "var(--accent)", 0);
      g += `<line x1="${X(m)}" x2="${X(m)}" y1="${T}" y2="${H - B}" stroke="var(--bad)" stroke-width="2"/><text paint-order="stroke" stroke="var(--card)" stroke-width="3" stroke-linejoin="round" x="${X(m) + 4}" y="${T + 24}" fill="var(--bad-ink)" font-weight="700">▼ 출차 시작 감지</text>`;
    }
    if (truth) {
      [["in50", "실제 입차 절반"], ["in90", "실제 입차 90%"], ["abs50", "실제 출차 절반"], ["abs90", "실제 출차 90%"]].forEach(([k, lbl], i) => {
        if (truth[k] == null) return;
        g += `<line x1="${X(truth[k])}" x2="${X(truth[k])}" y1="${T}" y2="${H - B}" stroke="var(--good-ink)" stroke-width="1.5"/><text paint-order="stroke" stroke="var(--card)" stroke-width="3" stroke-linejoin="round" x="${X(truth[k]) + 3}" y="${T + 44 + (i % 2) * 14}" fill="var(--good-ink)">● ${lbl}</text>`;
      });
    }
    const path = pts.map((p, i) => (i ? "L" : "M") + X(p.m).toFixed(1) + " " + Y(p.v).toFixed(1)).join("");
    if (pts.length) g += `<path d="${path}" fill="none" stroke="var(--ink)" stroke-width="2.2"/>`;
    if (pts.length === 1) g += `<circle cx="${X(pts[0].m)}" cy="${Y(pts[0].v)}" r="3" fill="var(--ink)"/>`;
    g += marks + `</svg>`;
    $("leChart").innerHTML = g;
  }

  function render() {
    const replay = sel.value !== "" ? list[+sel.value] : null;
    if (!replay && !show) {
      $("leStatus").innerHTML = `<span class="chip">○ 오늘은 공연 없음</span> 오늘은 KSPO DOME 공연이 없어요. 공연일에 이 화면을 열어 두면 2분마다 주차 대수를 기록하며 자동으로 감지해요. 위 목록에서 지난 공연을 골라 어떻게 보이는지 미리 볼 수 있어요.`;
      $("leKpis").innerHTML = ""; drawChart([], null, "18:00", null); return;
    }
    const startHHMM = replay ? replay.start : show.start;
    const pts = replay ? replayPts(replay) : livePts();
    const det = detectExit(pts);
    const last = pts.at(-1);
    let status, k1;
    if (det.state === "found") {
      status = `<span class="chip bad">▼ 출차 시작 감지</span> 공연 시작 뒤 최고 ${Math.round(det.M).toLocaleString()}대에서 최근 ${R.windowMin}분 동안 ${Math.round(det.drop)}대가 줄었어요(기준 ${Math.round(R.ratio * det.M)}대).`;
      k1 = kpi("출차 시작 감지", atText(det.at.m, startHHMM), "is-bad");
    } else if (det.state === "checking") {
      status = `<span class="chip warn">▲ 확인 중</span> 대수가 빠르게 줄고 있어요. 다음 값(약 4분 뒤)도 줄면 '출차 시작'으로 확정해요.`;
      k1 = kpi("출차 시작 감지", "확인 중 ▲", "is-warn");
    } else {
      const lm = last ? last.m : null;
      const rd = pts.length ? recentDrop(pts) : null;
      status = lm == null ? `<span class="chip">○ 기록 시작 전</span> 실시간 주차 대수를 기다리는 중이에요.`
        : lm < 0 ? `<span class="chip">○ 공연 전</span> 공연 시작(${startHHMM}) 전이에요.${E ? ` 지난 공연을 보면 관객 차 절반은 ${toHHMM(toMin(startHHMM) + E.half.med)}쯤, 90%는 ${toHHMM(toMin(startHHMM) + E.most.med)}쯤 들어와요.` : ""} 기록은 계속 쌓여요.`
        : lm < R.earliestMin ? `<span class="chip good">○ 공연 중</span> 시작 ${R.earliestMin}분 뒤부터 감지해요(늦게 오는 관객 차를 빼려고).`
        : `<span class="chip good">○ 감시 중</span> 아직 출차 시작 신호가 없어요. 최근 ${R.windowMin}분 변화 ${rd == null ? "—" : (rd >= 0 ? "−" : "+") + Math.abs(Math.round(rd)) + "대"} / 감지 기준 −${Math.round(R.ratio * (det.M || 0))}대.`;
      k1 = kpi("출차 시작 감지", "아직 ○");
    }
    const f = det.state === "found" ? det.at.m : null;
    const range = (a) => f == null ? "감지 후 표시" :
      `${toHHMM(toMin(startHHMM) + f + a.med)} <span class="muted small">(보통 ${toHHMM(toMin(startHHMM) + f + a.p25)}~${toHHMM(toMin(startHHMM) + f + a.p75)})</span>`;
    const nowV = last ? `${Math.round(last.v).toLocaleString()}대` : "—";
    $("leStatus").innerHTML = status + (replay ? ` <span class="muted small">· 지난 공연(${replay.date}) 기록으로 다시 본 화면이에요.</span>` : "");
    const inRange = (a) => `${toHHMM(toMin(startHHMM) + a.med)} <span class="muted small">(보통 ${toHHMM(toMin(startHHMM) + a.p25)}~${toHHMM(toMin(startHHMM) + a.p75)})</span>`;
    $("leKpis").innerHTML = (E ? kpi("관객 차 절반이 들어오는 시각(예상)", inRange(E.half)) + kpi("관객 차 90%가 들어오는 시각(예상)", inRange(E.most)) : "") + k1 +
      kpi("관객 차 절반이 빠지는 시각(예상)", range(A.half)) +
      kpi("관객 차 90%가 빠지는 시각(예상)", range(A.most)) +
      kpi(replay ? "시작 뒤 최고 대수" : `지금 주차 대수(추정)${last && !replay ? ` · ${toHHMM(toMin(startHHMM) + last.m)}` : ""}`,
          replay ? `${Math.round(det.M || 0).toLocaleString()}대` : nowV);
    drawChart(pts, det.state === "found" ? det : null, startHHMM, replay);
    if (!replay) {
      const st = store.get(KEY(todayKST));
      const first = st[0] ? hhmmKST(st[0][0]) : null;
      $("leRec").textContent = first ? `이 브라우저 기록: ${first}부터 ${st.length}개 값${show.test ? " · 시험 모드" : ""}. 화면을 닫으면 그동안은 기록되지 않아요.` : "";
    } else $("leRec").textContent = "";
    const marks = store.get(MARK(todayKST));
    $("leMarks").textContent = marks.length ? "현장에서 누른 시각: " + marks.map(hhmmKST).join(", ") : "";
  }

  // ---------- 실시간 기록 ----------
  async function poll() {
    try {
      const r = await fetch("/api/parking");
      if (!r.ok) throw new Error("HTTP " + r.status);
      const j = await r.json();
      const sum = j.kspo && j.kspo.parking_sum;
      if (sum == null || !(sum > 0)) throw new Error("값 없음");
      const st = store.get(KEY(todayKST));
      st.push([Date.now(), sum]);
      store.set(KEY(todayKST), st.slice(-600));
      $("leErr").textContent = "";
    } catch (e) {
      $("leErr").textContent = `실시간 주차 값을 받지 못했어요(${e.message || e}). 2분 뒤 다시 시도해요.`;
    }
    if (sel.value === "") render();
  }
  if (show) {
    const inWindow = () => { const m = (Date.now() - startMs) / 60000; return m > -240 && m < 420; };
    if (inWindow()) poll();
    setInterval(() => { if (inWindow()) poll(); }, POLL_MS);
  }

  // 현장 확인용: 관객이 실제로 나오기 시작한 시각을 눌러 남기고, 기록을 CSV로 내려받기
  $("leMark").addEventListener("click", () => {
    const m = store.get(MARK(todayKST)); m.push(Date.now()); store.set(MARK(todayKST), m); render();
  });
  $("leCsv").addEventListener("click", () => {
    const fmt = (ms) => new Date(ms).toLocaleString("sv-SE", { timeZone: "Asia/Seoul" });
    const rows = [["시각(KST)", "parking_sum", "추정 대수", "구분"]];
    store.get(KEY(todayKST)).forEach(([ms, sum]) => rows.push([fmt(ms), sum, parkActual(sum).est, "실시간"]));
    store.get(MARK(todayKST)).forEach((ms) => rows.push([fmt(ms), "", "", "현장: 관객 나오기 시작"]));
    const det = show ? detectExit(livePts()) : null;
    if (det && det.state === "found") rows.push([fmt(det.at.ms), det.at.sum, Math.round(det.at.v), "화면: 출차 시작 감지"]);
    const blob = new Blob(["﻿" + rows.map((r) => r.join(",")).join("\n")], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = `live_exit_${todayKST}.csv`; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  });
  sel.addEventListener("change", render);

  const rel = (m) => (m < 0 ? `시작 ${-m}분 전` : m === 0 ? "시작 때" : `시작 ${m}분 뒤`);
  const night = parkActual(0).night;
  $("leSrc").innerHTML =
    `출처: 한국체육산업개발 실시간 주차현황(parking_sum, 2분마다) − 출차 기록 없는 차(새벽 ${night.date} ${night.time} 값 ${night.sum.toLocaleString()}대 − ${PARK_NIGHT_TRUE}대). ` +
    `규칙: ${cfg.method} ` +
    `<br>맞춘 자료: 입출차 기록 KSPO DOME 공연 ${BT.found}회(${BT.period}${BT.bySource ? ", " + Object.entries(BT.bySource).map(([k, v]) => `${k}년 ${v}회`).join("·") : ""}), ${cfg.built} 계산. ` +
    `한 공연씩 빼고 되짚어 본 평균 오차: 절반 시각 <b>${BT.half.live}분</b>(미리 예측 ${BT.half.before}분), 90% 시각 <b>${BT.most.live}분</b>(미리 예측 ${BT.most.before}분). ` +
    `감지 뒤 걸린 시간: 절반 보통 ${A.half.p25}~${A.half.p75}분, 90% 보통 ${A.most.p25}~${A.most.p75}분. 30분 넘게 이른 감지 ${BT.early30}회.` +
    (E && EB ? `<br>입차: ${cfg.entryMethod} 지난 공연 ${EB.shows}회 기준 절반은 ${rel(E.half.med)}(보통 ${rel(E.half.p25)}~${rel(E.half.p75)}), 90%는 ${rel(E.most.med)}(보통 ${rel(E.most.p25)}~${rel(E.most.p75)}). ` +
      `한 공연씩 빼고 되짚어 본 평균 오차: 절반 ${EB.half.before}분, 90% ${EB.most.before}분.` : "") +
    `<br>주의: 다른 행사 차, 중간 휴식(인터미션), 큰 주차장 정산 지연으로 틀릴 수 있어요. 현장 확인과 함께 참고하세요.`;
  render();
})();
