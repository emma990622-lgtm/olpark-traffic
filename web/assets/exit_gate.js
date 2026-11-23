// 관객: '공연 끝나고 어느 문으로 나갈까요?' — scripts/25_exit_gate_weather.py가 만든 exit_gate.json
// 주차한 곳(=들어온 문) 고르기 → 지난 공연에서 같은 곳에 주차한 관객 차가 가장 빨리 빠진 출구.
// 날씨: 공연 날 출차 시간대 예보(/api/weather, 24시간 앞까지) 또는 직접 고르기 → 지난 공연에서 비·추위 때 출차가 늦어졌는지.
(async function () {
  const $ = (id) => document.getElementById(id);
  if (!$("exitGate")) return;
  let J = null;
  try { J = await loadJSON("exit_gate.json"); } catch (_) {}
  if (!J || !J.byEntry) {
    $("egResult").innerHTML = `<span class="chip">○ 아직 없음</span> 출구 비교 자료를 불러오지 못했어요.`;
    return;
  }
  const GATE = (g) => g + "문";
  const ZONE = {
    "북2": "KSPO DOME·올림픽수영장 옆",
    "동2": "올림픽홀·테니스장·올림픽공원역 쪽",
    "남2": "핸드볼경기장·우리금융아트홀 쪽",
  };
  let pick = null;

  // 주차한 곳 버튼
  const box = $("egZone");
  const btn = (g, label, sub) =>
    `<button type="button" data-g="${g}" aria-pressed="false"><b>${label}</b><span>${sub}</span></button>`;
  box.innerHTML =
    ["북2", "동2", "남2"].map((g) => btn(g, J.byEntry[g].zones.join("·"), `${ZONE[g]} · ${GATE(g)}으로 들어옴`)).join("") +
    btn("other", "그 밖의 주차장", "서1·서2·남3·남4문 주차장");
  box.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-g]");
    if (!b) return;
    pick = b.dataset.g;
    box.querySelectorAll("button").forEach((x) => {
      x.classList.toggle("on", x === b);
      x.setAttribute("aria-pressed", x === b ? "true" : "false");
    });
    renderGate();
  });

  function renderGate() {
    const out = $("egResult");
    if (!pick) {
      out.innerHTML = `<span class="muted small">주차한 곳을 고르면 가장 빨리 빠진 출구를 알려 드려요.</span>`;
      return;
    }
    if (pick === "other") {
      const o = J.otherLots;
      out.innerHTML = `<div class="eg-reco"><span class="chip accent">▶ 들어온 문으로 나가세요</span>
        <p>서1·서2·남3·남4문 주차장은 공원 안쪽 길로 다른 문과 이어지지 않아요. 지난 공연에서 이 주차장에 세운 관객 차는
        ${Object.keys(o).map((g) => `${GATE(g)} ${Math.round(o[g].sameGate * 1000) / 10}%`).join(", ")}가 들어온 문으로 나갔어요.</p></div>`;
      return;
    }
    const E = J.byEntry[pick];
    const best = E.options.find((o) => o.gate === E.best);
    const rows = E.options.map((o) => {
      const v = o.gate === E.best ? null : o.vs[E.best];
      return { o, v, late: v ? v.min : 0 };
    }).sort((a, b) => a.late - b.late);
    const worst = rows[rows.length - 1];
    const wv = best.vs[worst.o.gate];
    const L = J.gateLoad;
    out.innerHTML =
      `<div class="eg-reco"><span class="chip good">● 가장 빠름</span> <b class="eg-gate">${GATE(E.best)}</b>으로 나가세요
        <p>지난 KSPO DOME 공연 ${wv.n}회에서 ${E.zones.join("·")}에 세운 차(${GATE(pick)}으로 들어온 차)를 비교했어요.
        ${GATE(E.best)}으로 나간 차가 ${GATE(worst.o.gate)}으로 나간 차보다 <b>${Math.abs(wv.min)}분</b> 일찍 빠졌어요(중앙값, 공연 ${Math.round(wv.fasterShare * 100)}%에서 더 빨랐어요).</p></div>
      <div class="table-scroll"><table class="list"><tr><th>출구 · 나간 뒤 방향</th><th>${GATE(E.best)}보다</th></tr>` +
      rows.map(({ o, v }) => `<tr><td><b>${GATE(o.gate)}</b>${o.gate === E.best ? ` <span class="chip good">● 가장 빠름</span>` : ""}<br><span class="muted small">${J.way[o.gate]}</span></td>
        <td class="nowrap">${v ? `▲ ${v.min}분 늦음<br><span class="muted small">더 빨랐던 공연 ${Math.round(v.fasterShare * 100)}%</span>` : "기준"}</td>
</tr>`).join("") +
      `</table></div>
      <p class="muted small" style="margin:8px 0 0">공연 한 번에 관객 차가 동2문 약 ${L["동2"].carsPerShow}대, 북2문 약 ${L["북2"].carsPerShow}대, 남2문 약 ${L["남2"].carsPerShow}대 나가요.
      집 방향이 출구와 다르면 공원 밖에서 돌아가는 시간이 더 들 수 있어요(이 비교는 공원 출구를 지나는 때까지예요).</p>`;
  }

  // 날씨
  let wxAll = null, wxSeq = 0;
  function show() {                                       // 고른 공연의 날짜·시작 시각
    const d = $("date") && $("date").value;
    const o = $("event") && $("event").selectedOptions[0];
    const m = o && o.textContent.match(/^(\d{1,2}:\d{2})\s+(.+?)\s+·/);
    return d && m ? { date: d, start: m[1], venue: m[2] } : null;
  }
  async function forecastRain(s) {                       // 출차 시간대(시작 2.5~4.5시간 뒤) 예보
    if (!wxAll) {
      try {
        const r = await fetch("/api/weather");
        if (!r.ok) throw new Error(r.status);
        wxAll = (await r.json()).hours || [];
      } catch (_) { return { none: "날씨 예보를 불러오지 못했어요" }; }
    }
    const t0 = toMin(s.start) + 150, t1 = toMin(s.start) + 270;
    const hs = [];
    for (let m = t0; m <= t1; m += 60) {
      const day = new Date(s.date + "T00:00:00"); day.setMinutes(m);
      const ds = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, "0")}-${String(day.getDate()).padStart(2, "0")}`;
      const h = wxAll.find((x) => x.date === ds && x.hour === day.getHours());
      if (h) hs.push(h);
    }
    if (!hs.length) return { none: "이 공연의 출차 시간대 예보는 아직 없어요(서울시 예보는 24시간 앞까지)" };
    const rain = hs.reduce((a, h) => a + (h.precip || 0), 0);
    const temps = hs.map((h) => h.temp).filter((v) => v != null);
    return { rain, temp: temps.length ? Math.min(...temps) : null };
  }
  const sg = (v) => { const r = Math.round(v); return (r > 0 ? "+" : r < 0 ? "−" : "") + Math.abs(r); };
  const span = (e) => `${sg(e.min)}분(95% 범위 ${sg(e.lo)}~${sg(e.hi)}분)`;
  const hm = (m) => `${Math.floor(m / 60)}시간 ${Math.round(m % 60)}분`;
  async function renderWx() {
    const W = J.weather, mine = ++wxSeq;
    const mode = $("egWx").value;
    const s = show();
    let rain = mode === "rain", cold = mode === "cold", note = "";
    if (mode === "auto") {
      if (!s || s.venue !== "KSPO DOME") note = "KSPO DOME 공연을 고르면 그 공연 출차 시간대 예보를 볼게요.";
      else {
        const f = await forecastRain(s);
        if (mine !== wxSeq) return;
        if (f.none) note = f.none + ". 아래에서 직접 골라 볼 수 있어요.";
        else {
          rain = f.rain >= 1; cold = f.temp != null && f.temp < 0;
          note = `서울시 예보: 출차 시간대 비 ${Math.round(f.rain * 10) / 10}mm${f.temp != null ? `, 기온 ${f.temp}도` : ""}.`;
        }
      }
    }
    const e = W.effect, T = W.effectTour;
    // 판단은 '같은 공연(투어)끼리' 비교의 95% 범위로(공연마다 길이가 달라 날씨와 섞이는 것을 막음).
    // 절반 출차(p50)나 마지막 차들(p90) 중 하나라도 범위가 모두 0보다 크면 '늦어질 수 있어요'
    const late = (x) => x.p50.lo > 0 || x.p90.lo > 0;
    const verdict = (x) => late(x) ? `<span class="chip warn">▲ 늦어질 수 있어요</span>` : `<span class="chip">○ 늦어진다는 근거 없음</span>`;
    let txt;
    if (rain) txt = `${verdict(T.wet)} 비 온 공연 ${T.wet.shows}회를 같은 공연의 비 안 온 회차와 비교했어요(${T.wet.tours}개 공연).
      관객 차 절반이 빠지는 때는 ${span(T.wet.p50)}, 마지막 10%가 남을 때까지(90% 출차)는 ${span(T.wet.p90)} 차이였어요.
      ${T.wet.p90.lo > 0 ? "<b>비 오는 날은 마지막 차들이 빠지는 데 더 오래 걸렸어요.</b> 늦게 나올 생각이면 시간을 넉넉히 잡으세요. " : ""}비 온 공연이 ${T.wet.shows}회뿐이라 확실하지는 않아요.`;
    else if (cold) txt = `${verdict(T.cold)} 추운 공연(출차 시간대 체감 0도 미만) ${T.cold.shows}회를 같은 공연의 덜 추운 회차와 비교하면(${T.cold.tours}개 공연)
      절반 출차 ${span(T.cold.p50)}, 90% 출차 ${span(T.cold.p90)} 차이로 <b>추위 때문에 늦어진다는 근거는 없어요.</b>
      공연을 가리지 않고 모든 추운 공연을 보면 절반 출차가 ${span(e.cold.p50)} 늦었는데, 추운 날 공연이 주로 길게 하는 연말 공연이라 생긴 차이로 보여요.`;
    else txt = `<span class="chip good">● 보통 날씨</span> 관객 차 절반이 빠지는 때는 보통 공연 시작 후 ${hm(W.dryMedian.p50)}, 90%는 ${hm(W.dryMedian.p90)}예요(지난 공연 중앙값).`;
    $("egWeather").innerHTML = (note ? `<p class="muted small" style="margin:0 0 6px">${note}</p>` : "") + `<div class="eg-wx">${txt}</div>`;
  }
  $("egWx").addEventListener("change", renderWx);
  $("date").addEventListener("change", () => setTimeout(renderWx, 0));
  $("event").addEventListener("change", renderWx);

  // 차로 오는 관객에게만 보임 (이동 수단 토글은 audience.js에서 전환)
  const activeMode = document.querySelector("#mode button.on");
  if (activeMode) $("exitGate").hidden = activeMode.dataset.v !== "car";

  $("egSrc").innerHTML = `출처: ${J.source}. 방법: ${J.method}. KSPO DOME 공연 ${J.shows}회, 관객 차 ${J.cars.toLocaleString()}대. ` +
    `주차한 곳은 기록에 없어 들어온 문으로 대신했어요(공식 주차 안내의 문별 주차 구역). 날씨: ${J.weatherSource}, 공연 ${J.weather.shows}회(${J.weather.period}). 계산일 ${J.built}. ` +
    `<a href="data-guide.html">데이터 설명 보기</a>`;
  renderGate();
  let tries = 0;
  const t = setInterval(() => { if ($("event").value || ++tries > 40) { clearInterval(t); renderWx(); } }, 250);
})();
