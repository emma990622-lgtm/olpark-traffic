// 운영자 화면: 관객 성향(연령·성별)으로 본 자가용 예상 — scripts/15_audience_car_model.py가 만든 audience_car.json
// 공연별 '늘어난 생활인구'의 성별·연령 구성과 공원 주차장 관객 차 대수로 다중회귀분석한 결과를 보여 주고,
// 고른 날짜의 KSPO DOME 공연(같은 가수의 지난 관객 구성이 있을 때)과 관객 유형별 예상 관객 차를 계산한다.
(async function () {
  const $ = (id) => document.getElementById(id);
  if (!$("audCar")) return;
  let A = null;
  try { A = await loadJSON("audience_car.json"); } catch (_) {}
  if (!A || !A.model || !A.model.coef) {
    $("acStatus").innerHTML = `<span class="chip">○ 아직 없음</span> 관객 성향 분석 자료(audience_car.json)를 불러오지 못했어요.`;
    return;
  }
  const M = A.model, C = M.coef, CAP = 2120;
  const fmt = (n) => Math.round(n).toLocaleString();
  const pct = (v) => (v > 0 ? "+" : "") + v + "%";

  // 예측: ln(관객 차) = b0 + b1·나이/10 + b2·여성비율 + b3·금요일(평일)  (80% 예측 범위)
  function predict(meanAge, female, weekdayEve) {
    const x = [1, meanAge / 10, female, weekdayEve ? 1 : 0];
    const m = x.reduce((s, v, i) => s + v * M.b[i], 0);
    let q = 0;
    for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) q += x[i] * M.XtXi[i][j] * x[j];
    const s = Math.sqrt(M.s2 * (1 + q));
    return { pred: Math.exp(m), lo: Math.exp(m - M.t80 * s), hi: Math.exp(m + M.t80 * s) };
  }
  const idol = predict(25, 0.92, false).pred;

  // ---------- 결과 요약 ----------
  const sure = (c) => (c.p < 0.05 && Math.sign(c.pctLo) === Math.sign(c.pctHi)) ? "● 뚜렷함" : (Math.sign(c.pctLo) === Math.sign(c.pctHi) ? "▲ 덜 뚜렷함" : "○ 뚜렷하지 않음");
  $("acStatus").innerHTML = A.meaningful
    ? `<span class="chip good">● 의미 있는 관계</span> <b>관객 평균 나이가 10살 많으면 공원 주차장 관객 차가 약 ${pct(C.age10.pct)}</b>
       (95% 범위 ${pct(C.age10.pctLo)}~${pct(C.age10.pctHi)}), <b>여성 비율이 10%p 높으면 약 ${pct(C.female.pct)}</b>
       (${pct(C.female.pctLo)}~${pct(C.female.pctHi)}) 달라졌어요. 금요일 저녁 공연은 주말보다 약 ${pct(C.fri.pct)}였어요.`
    : `<span class="chip">○ 아직 뚜렷하지 않음</span> 지금 자료로는 관객 연령·성별과 자가용 이용의 관계가 예측에 쓸 만큼 뚜렷하지 않아요.
       ${["age10", "female"].map((k) => `${C[k].label} 관객 차 ${Math.sign(C[k].pctLo) === Math.sign(C[k].pctHi)
         ? `약 ${pct(C[k].pct)}(95% 범위 ${pct(C[k].pctLo)}~${pct(C[k].pctHi)}, p값 ${C[k].p.toFixed(2)})`
         : `변화가 뚜렷하지 않음(${pct(C[k].pct)}, 95% 범위 ${pct(C[k].pctLo)}~${pct(C[k].pctHi)})`}`).join(" · ")}.
       ${M.improve != null ? `한 공연씩 빼고 맞혀 보면 평균값만 쓸 때보다 오차가 ${Math.round(M.improve * 100)}% 줄어드는 데 그쳐요. ` : ""}아래 계산은 참고만 하세요.`;

  $("acCoef").innerHTML = `<tr><th>조건</th><th>관객 차 변화</th><th>95% 범위</th><th>p값</th><th>판단</th></tr>` +
    ["age10", "female", "fri"].map((k) => `<tr><td>${C[k].label}</td><td class="nowrap"><b>${pct(C[k].pct)}</b></td>
      <td class="nowrap">${pct(C[k].pctLo)} ~ ${pct(C[k].pctHi)}</td><td class="nowrap">${C[k].p.toFixed(3)}</td>
      <td class="nowrap">${sure(C[k])}</td></tr>`).join("");

  // ---------- 고른 날짜 공연 + 유형별 계산기 ----------
  const sel = $("acPreset"), daySel = $("acDay");
  sel.innerHTML = A.presets.map((p, i) => `<option value="${i}">${p.label}</option>`).join("");
  sel.value = "0";

  function resultHTML(r, label) {
    const w = Math.min(100, Math.round((r.pred / CAP) * 100));
    return `<div class="ac-result-head">${label}</div>
      <div class="ac-num">관객 차 약 <b>${fmt(r.pred)}대</b> <span class="muted small">(80% 범위 ${fmt(r.lo)}~${fmt(r.hi)}대)</span></div>
      <div class="ac-bar" aria-hidden="true"><span style="width:${w}%"></span></div>
      <div class="muted small">공원 주차장 ${CAP.toLocaleString()}면 대비 약 ${w}% · 10~20대 여성 팬 중심 공연(약 ${fmt(idol)}대)의 약 ${(r.pred / idol).toFixed(1)}배
        · 관객 차만 센 값이라 공원 방문객 차는 따로 더해져요</div>`;
  }

  function update() {
    const d = $("date") && $("date").value;
    const up = (A.upcoming || []).find((u) => u.date === d);
    const p = A.presets[+sel.value];
    const wk = daySel.value === "wk";
    let html = "";
    if (up && up.match && up.match.length) {
      const r = { pred: up.pred, lo: up.lo, hi: up.hi };
      const a = up.ages;
      html += `<div class="ac-result is-match">${resultHTML(r, `${d} KSPO DOME · ${up.title}`)}
        <div class="small" style="margin-top:6px">같은 가수 지난 공연(${up.match.map((m) => m.date).join(", ")}) 관객 구성으로 계산:
          평균 약 <b>${up.meanAge}세</b>, 여성 ${Math.round(up.female * 100)}%,
          ${Object.entries(a).map(([k, v]) => `${k} ${Math.round(v * 100)}%`).join(" · ")}
          ${up.dayType === "fri" || up.dayType === "wk" ? " · 평일 저녁 공연으로 계산" : " · 주말·공휴일 공연으로 계산"}</div></div>`;
    } else if (up) {
      html += `<div class="ac-result"><div class="ac-result-head">${d} KSPO DOME · ${up.title}</div>
        <div class="muted small">이 가수의 지난 관객 구성 기록이 없어요(2024-06~2025-12 생활인구 기준). 아래에서 예상 관객 유형을 골라 보세요.</div></div>`;
    }
    const r = predict(p.meanAge, p.female, wk);
    html += `<div class="ac-result">${resultHTML(r, `관객 유형으로 계산: ${p.label} · ${wk ? "금요일·평일 저녁" : "주말·공휴일"}`)}
      <div class="muted small" style="margin-top:4px">가정: 평균 ${p.meanAge}세, 여성 ${Math.round(p.female * 100)}%</div></div>`;
    $("acPredict").innerHTML = html;
  }
  sel.addEventListener("change", update);
  daySel.addEventListener("change", update);
  // 날짜 선택(operator.js가 채움)이 바뀌면 다시 계산
  const hook = () => { if ($("date") && $("date").value) { $("date").addEventListener("change", update); update(); } else setTimeout(hook, 300); };
  hook();

  // ---------- 산점도: 관객 평균 나이 × 관객 차 ----------
  (function drawScatter() {
    const pts = (A.shows || []).filter((s) => s.ok && s.cars && (s.dayType === "sun" || s.dayType === "fri"));
    if (!pts.length) { $("acChart").innerHTML = ""; return; }
    const W = 760, H = 290, L = 54, R = 16, T = 30, B = 40;
    const xMin = 15, xMax = 65, yMax = Math.max(1600, ...pts.map((p) => p.cars)) * 1.05;
    const X = (v) => L + ((v - xMin) / (xMax - xMin)) * (W - L - R);
    const Y = (v) => H - B - (v / yMax) * (H - T - B);
    let g = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" font-size="11" role="img"
      aria-label="공연별 관객 평균 나이와 공원 주차장 관객 차 대수. 나이가 많을수록 차가 많은 경향">`;
    for (let v = 0; v <= yMax; v += 400) g += `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end" fill="var(--ink-2)">${v}</text>`;
    for (let v = 20; v <= 60; v += 10) g += `<text x="${X(v)}" y="${H - B + 16}" text-anchor="middle" fill="var(--ink-2)">${v}세</text>`;
    g += `<text x="${(L + W - R) / 2}" y="${H - 6}" text-anchor="middle" fill="var(--ink-2)">관객 평균 나이 (생활인구로 추정)</text>`;
    g += `<text x="${L - 6}" y="14" text-anchor="end" fill="var(--ink-2)">관객 차(대)</text>`;
    // 회귀선: 여성 비율은 공연 평균으로 두고 주말·금요일 각각
    const fAvg = pts.reduce((s, p) => s + p.female, 0) / pts.length;
    [[false, "var(--accent)", "주말"], [true, "var(--warn-ink)", "금요일"]].forEach(([wk, col]) => {
      let d = "";
      for (let a = 18; a <= 62; a += 2) d += (d ? "L" : "M") + X(a).toFixed(1) + " " + Y(predict(a, fAvg, wk).pred).toFixed(1);
      g += `<path d="${d}" fill="none" stroke="${col}" stroke-width="2" stroke-dasharray="${wk ? "5 4" : ""}"/>`;
    });
    pts.forEach((p) => {
      const x = X(Math.max(xMin, Math.min(xMax, p.meanAge))), y = Y(p.cars);
      const tip = `<title>${p.date} ${p.title} · 평균 ${p.meanAge}세 · 여성 ${Math.round(p.female * 100)}% · 관객 차 ${p.cars}대</title>`;
      g += p.dayType === "fri"
        ? `<path d="M${x} ${y - 6}L${x + 6} ${y + 5}L${x - 6} ${y + 5}Z" fill="var(--warn-bg)" stroke="var(--warn-ink)" stroke-width="1.5">${tip}</path>`
        : `<circle cx="${x}" cy="${y}" r="5" fill="var(--accent-soft)" stroke="var(--accent)" stroke-width="1.5">${tip}</circle>`;
    });
    g += `</svg>`;
    $("acChart").innerHTML = g;
    $("acLegend").innerHTML = `<span>● 주말·공휴일 공연 (실선: 회귀식)</span><span>▲ 금요일 저녁 공연 (점선: 회귀식)</span><span class="muted">점에 마우스를 올리면 공연 이름이 보여요</span>`;
  })();

  const S = A.sources, Me = A.method;
  $("acSrc").innerHTML =
    `출처: ${S.population}(${S.populationPeriod}) · 관객 차: ${S.cars} · 공연 일정: ${S.events}.<br>` +
    `방법: ${Me.composition}. 관객 차는 ${Me.cars}. 회귀식 ${Me.model}. 오차 범위는 ${Me.ci}.<br>` +
    `분석한 공연 ${M.n}회(가수 ${M.artists}팀), 설명력 R² ${M.r2}, 한 공연씩 빼고 맞혀 본 오차가 평균값만 쓸 때보다 ${Math.round(M.improve * 100)}% 작음(중앙값 기준 약 ±${M.looMedianErrPct}%). ` +
    `뺀 공연: ${Me.excluded}.<br>한계: ${Me.limits} · ${A.built} 계산`;
})();
