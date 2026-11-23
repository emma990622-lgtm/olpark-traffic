// 관객: '공연 끝나고 어느 문으로 나갈까요?' — scripts/25_exit_gate_weather.py·30_exit_after_end.py가 만든 exit_gate.json
// 주차한 곳(=들어온 문) 고르기 → 지난 공연에서 같은 곳에 주차한 관객 차가 가장 빨리 빠진 출구.
// 날씨: 공연 날 출차 시간대 예보(/api/weather, 24시간 앞까지) 또는 직접 고르기 → 지난 공연에서 비·추위 때 출차가 늦어졌는지.
(async function () {
  const $ = (id) => document.getElementById(id);
  if (!$("exitGate")) return;
  let J = null, D = null;
  try {
    [J, D] = await Promise.all([
      loadJSON("exit_gate.json"),
      loadJSON("gate_directions.json").catch(() => null),
    ]);
  } catch (_) {}
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
  let wayPick = "none";

  // 문별 주차 구역 기준점 (좌표 출처: walk_tmap.json TMAP POI, places.json, links.json 서울시 도로 노드)
  const PARK_ZONE_REFS = [
    { gate: "북2", label: "P5·KSPO DOME 옆", lat: 37.51916, lng: 127.127514 },
    { gate: "북2", label: "P4·올림픽수영장 쪽", lat: 37.520531, lng: 127.128183 },
    { gate: "북2", label: "북2문 입출구", lat: 37.523691, lng: 127.128594 },
    { gate: "동2", label: "P2·올림픽홀 옆", lat: 37.514685, lng: 127.127509 },
    { gate: "동2", label: "P그·올림픽공원역 앞", lat: 37.516201, lng: 127.130923 },
    { gate: "동2", label: "동2문 교차로 쪽", lat: 37.515852, lng: 127.13068 },
    { gate: "동2", label: "P테·테니스장 쪽", lat: 37.51748, lng: 127.128132 },
    { gate: "남2", label: "P6·핸드볼경기장 옆", lat: 37.517379, lng: 127.126315 },
    { gate: "남2", label: "P7·우리금융아트홀 옆", lat: 37.516713, lng: 127.124981 },
    { gate: "남2", label: "P1A·남2문 쪽", lat: 37.513758, lng: 127.12307 },
    { gate: "other", label: "서1문·올림픽회관 주차장", lat: 37.518439, lng: 127.116172 },
    { gate: "other", label: "서2문·올림픽파크텔 쪽", lat: 37.520017, lng: 127.114123 },
    { gate: "other", label: "남3문 주차장", lat: 37.516121, lng: 127.118498 },
    { gate: "other", label: "남4문 주차장 쪽", lat: 37.516329, lng: 127.115835 },
    { gate: "other", label: "한성백제박물관 주차장", lat: 37.515347, lng: 127.120798 },
  ];

  // 주차한 곳 버튼
  const box = $("egZone");
  const btn = (g, label, sub) =>
    `<button type="button" data-g="${g}" aria-pressed="false"><b>${label}</b><span>${sub}</span></button>`;
  box.innerHTML =
    ["북2", "동2", "남2"].map((g) => btn(g, J.byEntry[g].zones.join("·"), `${ZONE[g]} · ${GATE(g)}으로 들어옴`)).join("") +
    btn("other", "그 밖의 주차장", "서1·서2·남3·남4문 주차장");

  // 가는 방면 빠른 버튼 (북서·북동 / 남서·남동 방위 순서로 배치, 외부 길찾기 API 호출 없음)
  const wayBox = $("egWay");
  const dirByKey = {};
  ((D && D.directions) || []).forEach((d) => { dirByKey[d.key] = d; });
  if (wayBox) {
    const order = ["nw", "ne", "sw", "se"].filter((k) => dirByKey[k]);
    if (order.length) {
      wayBox.innerHTML =
        `<button type="button" data-w="none" class="on span-all" aria-pressed="true"><b>방면 선택 안 함</b><span>공원 출구를 지날 때까지만 비교해요</span></button>` +
        order.map((k) => {
          const d = dirByKey[k];
          return `<button type="button" data-w="${d.key}" aria-pressed="false"><b>${d.label}</b><span>${d.sub}</span></button>`;
        }).join("");
      wayBox.addEventListener("click", (e) => {
        const b = e.target.closest("button[data-w]");
        if (!b) return;
        wayPick = b.dataset.w;
        wayBox.querySelectorAll("button").forEach((x) => {
          const on = x === b;
          x.classList.toggle("on", on);
          x.setAttribute("aria-pressed", on ? "true" : "false");
        });
        renderGate();
      });
    } else {
      wayBox.innerHTML = `<span class="muted small">방면별 둘레 도로 자료가 아직 없어요.</span>`;
    }
  }

  function selectZone(g) {
    pick = g;
    box.querySelectorAll("button").forEach((x) => {
      const on = x.dataset.g === g;
      x.classList.toggle("on", on);
      x.setAttribute("aria-pressed", on ? "true" : "false");
    });
    renderGate();
  }

  box.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-g]");
    if (!b) return;
    selectZone(b.dataset.g);
  });

  if ($("egGpsBtn")) {
    $("egGpsBtn").addEventListener("click", () => requestUserGPS({ trigger: "exitGate" }));
  }
  onUserGPS((g) => {
    const gpsBtn = $("egGpsBtn"), gpsNote = $("egGpsNote");
    if (!gpsBtn || !gpsNote) return;
    gpsBtn.disabled = g.status === "loading";
    if (g.status === "loading") {
      gpsBtn.textContent = "위치 확인 중…";
      gpsNote.textContent = "현재 위치를 확인하고 있어요…";
    } else if (g.status === "ok" && g.loc) {
      gpsBtn.textContent = "내 위치로 다시 찾기";
      const nearest = PARK_ZONE_REFS
        .map((r) => ({ ...r, dist: distMeters(g.loc.lat, g.loc.lng, r.lat, r.lng) }))
        .sort((a, b) => a.dist - b.dist)[0];
      if (nearest.dist <= 1200) {
        if (g.source === "exitGate" || pick === null) selectZone(nearest.gate);
        const zoneLabel = nearest.gate === "other" ? "그 밖의 주차장" : `${GATE(nearest.gate)} 구역(${J.byEntry[nearest.gate].zones.join("·")})`;
        gpsNote.innerHTML =
          `<span class="chip good">● GPS 반영</span> 현재 위치${g.loc.acc ? `(오차 약 ±${g.loc.acc}m)` : ""}에서 <b>${nearest.label}</b>(직선 약 ${Math.round(nearest.dist)}m)이 가장 가까워 <b>${zoneLabel}</b>을 골랐어요. ` +
          `공연장 안에서 누르셨거나 실제 주차한 곳이 다르면 아래 버튼을 직접 눌러 바꿔 주세요(기준 좌표: TMAP·서울시 도시데이터).`;
      } else {
        gpsNote.innerHTML =
          `<span class="chip">○ 공원 밖</span> 현재 위치가 올림픽공원에서 약 ${(nearest.dist / 1000).toFixed(1)}km 떨어져 있어 주차 구역을 자동으로 고르지 않았어요. 공원 주차장에서 누르거나 아래에서 직접 골라 주세요.`;
      }
    } else if (g.status === "off") {
      gpsBtn.textContent = "현재 위치(GPS)로 주차한 곳 찾기";
      gpsNote.textContent = "내 위치 표시를 껐어요. 아래에서 직접 고르거나 다시 버튼을 눌러 주세요.";
    } else if (g.status === "denied" || g.status === "error" || g.status === "unsupported") {
      gpsBtn.textContent = "현재 위치(GPS) 다시 확인";
      gpsNote.innerHTML = `<span class="chip warn">▲ 확인 안 됨</span> ${g.msg}`;
    }
  });

  function renderGate() {
    const out = $("egResult");
    const dir = wayPick !== "none" ? dirByKey[wayPick] : null;
    if (!pick) {
      out.innerHTML = `<span class="muted small">${dir
        ? `위에서 주차한 곳을 고르면 ‘${dir.label}’ 방면 둘레 도로까지 합쳐 가장 빠른 출구를 계산해 드려요.`
        : "주차한 곳을 고르면 가장 빨리 빠진 출구를 알려 드려요."}</span>`;
      return;
    }
    if (pick === "other") {
      const o = J.otherLots;
      out.innerHTML = `<div class="eg-reco"><span class="chip accent">▶ 들어온 문으로 나가세요</span>
        <p>서1·서2·남3·남4문 주차장은 공원 안쪽 길로 다른 문과 이어지지 않아요. 지난 공연에서 이 주차장에 세운 관객 차는
        ${Object.keys(o).map((g) => `${GATE(g)} ${Math.round(o[g].sameGate * 1000) / 10}%`).join(", ")}가 들어온 문으로 나갔어요.${dir
          ? ` <b>${dir.label}</b> 방면이어도 들어온 문으로 먼저 나간 뒤 바깥 큰길을 이용해야 해요.` : ""}</p></div>`;
      return;
    }
    const E = J.byEntry[pick];
    const L = J.gateLoad;

    // 가는 방면을 골랐을 때: 공원 안 출차 차이 + 출구→방면 합류 교차로 둘레 도로 시간 합산 비교
    if (dir && dir.byGate) {
      const comb = E.options.map((o) => {
        const inLate = o.gate === E.best ? 0 : o.vs[E.best].min;
        const road = dir.byGate[o.gate];
        const tot = +(inLate + road.roadMin).toFixed(1);
        return { gate: o.gate, inLate, road, tot };
      }).sort((a, b) => a.tot - b.tot);
      const g0 = comb[0], g1 = comb[1], g2 = comb[2];
      const gap1 = +(g1.tot - g0.tot).toFixed(1), gap2 = +(g2.tot - g0.tot).toFixed(1);
      let head, body;
      if (gap1 < 1.0) {
        head = `<span class="chip good">● 거의 비슷해요</span> <b>${dir.label}</b> 방면은 <b class="eg-gate">${GATE(g0.gate)}</b>·<b class="eg-gate">${GATE(g1.gate)}</b>이 비슷해요 (약 ${gap1}분 차이)`;
        body = `${E.zones.join("·")}에서 출구까지 걸리는 차이와 출구 밖에서 <b>${dir.hub}</b>까지 가는 시간을 합치면 ${GATE(g0.gate)}이 조금 이르지만, ${GATE(g1.gate)}과 약 ${gap1}분 차이라 교차로 신호 한 번이면 바뀔 수 있어요(${GATE(g2.gate)}은 약 ${gap2}분 더 걸려요).`;
      } else if (g0.gate !== E.best) {
        head = `<span class="chip good">● 가장 빠름</span> <b>${dir.label}</b> 방면은 <b class="eg-gate">${GATE(g0.gate)}</b>으로 나가세요`;
        body = `공원 안만 보면 ${GATE(E.best)}이 빠르지만, 출구 밖에서 <b>${dir.hub}</b>까지 돌아가는 시간을 합치면 <b>${GATE(g0.gate)}</b>이 ${GATE(g1.gate)}보다 약 <b>${gap1}분</b>, ${GATE(g2.gate)}보다 약 <b>${gap2}분</b> 빨라요.`;
      } else {
        head = `<span class="chip good">● 가장 빠름</span> <b>${dir.label}</b> 방면도 <b class="eg-gate">${GATE(g0.gate)}</b>으로 나가세요`;
        body = `출구 밖에서 합류 지점(<b>${dir.hub}</b>)까지 공원 둘레 도로를 도는 시간을 합쳐도 <b>${GATE(g0.gate)}</b>이 ${GATE(g1.gate)}보다 약 <b>${gap1}분</b>, ${GATE(g2.gate)}보다 약 <b>${gap2}분</b> 빨라요. 공원 안에서 다른 문으로 가로지르며 기다리는 것보다 바로 나가 바깥 큰길을 타는 편이 빨라요.`;
      }
      out.innerHTML =
        `<div class="eg-reco">${head}<p>${body}</p></div>
        <div class="table-scroll"><table class="list">
          <tr><th>출구 · 둘레 경로</th><th>공원 안</th><th>합류점까지</th><th>합계 비교</th></tr>` +
        comb.map((r, idx) => {
          const diff = +(r.tot - g0.tot).toFixed(1);
          const badge = idx === 0
            ? ` <span class="chip good">● 추천</span>`
            : (idx === 1 && gap1 < 1.0 ? ` <span class="chip">비슷함</span>` : "");
          return `<tr>
            <td><b>${GATE(r.gate)}</b>${badge}<br><span class="muted small">${r.road.via} (${(r.road.meters / 1000).toFixed(1)}km)</span></td>
            <td class="nowrap">${r.inLate === 0 ? "기준" : `+${r.inLate}분`}</td>
            <td class="nowrap">약 ${r.road.roadMin}분</td>
            <td class="nowrap">${idx === 0 ? "<b>가장 빠름</b>" : `▲ +${diff}분`}</td>
          </tr>`;
        }).join("") +
        `</table></div>
        <p class="muted small" style="margin:8px 0 0">합류 지점(<b>${dir.hub}</b>) 이후 목적지까지 걸리는 시간은 어느 문으로 나가든 같은 길이라 똑같아요.
        둘레 도로 시간은 KSPO DOME 공연 종료 시간대 실측 중앙값(${D.shows.length}회 공연·5분 간격 ${D.snapshots}회 수집, 서울시 실시간 도시데이터)이며 교차로 신호 대기 1~2분은 상황에 따라 달라질 수 있어요.</p>`;
      return;
    }

    const best = E.options.find((o) => o.gate === E.best);
    const rows = E.options.map((o) => {
      const v = o.gate === E.best ? null : o.vs[E.best];
      return { o, v, late: v ? v.min : 0 };
    }).sort((a, b) => a.late - b.late);
    const worst = rows[rows.length - 1];
    const wv = best.vs[worst.o.gate];
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
      이 비교는 공원 출구를 지날 때까지이며, 위에서 <b>가는 방면</b>을 고르면 공원 밖 둘레 도로 시간까지 합쳐 볼 수 있어요.</p>`;
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
  const dur = (m) => {
    const r = Math.round(m);
    if (r < 60) return `${r}분`;
    const h = Math.floor(r / 60), mm = r % 60;
    return mm ? `${h}시간 ${mm}분` : `${h}시간`;
  };
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
    const A = W.afterEnd && W.afterEnd.dry;
    let txt;
    if (rain) txt = `${verdict(T.wet)} 비 온 공연 ${T.wet.shows}회를 같은 공연의 비 안 온 회차와 비교했어요(${T.wet.tours}개 공연).
      관객 차 절반이 빠지는 때는 ${span(T.wet.p50)}, 마지막 10%가 남을 때까지(90% 출차)는 ${span(T.wet.p90)} 차이였어요.
      ${T.wet.p90.lo > 0 ? "<b>비 오는 날은 마지막 차들이 빠지는 데 더 오래 걸렸어요.</b> 늦게 나올 생각이면 시간을 넉넉히 잡으세요. " : ""}비 온 공연이 ${T.wet.shows}회뿐이라 확실하지는 않아요.`;
    else if (cold) txt = `${verdict(T.cold)} 추운 공연(출차 시간대 체감 0도 미만) ${T.cold.shows}회를 같은 공연의 덜 추운 회차와 비교하면(${T.cold.tours}개 공연)
      절반 출차 ${span(T.cold.p50)}, 90% 출차 ${span(T.cold.p90)} 차이로 <b>추위 때문에 늦어진다는 근거는 없어요.</b>
      공연을 가리지 않고 모든 추운 공연을 보면 절반 출차가 ${span(e.cold.p50)} 늦었는데, 추운 날 공연이 주로 길게 하는 연말 공연이라 생긴 차이로 보여요.`;
    else if (A) txt = `<span class="chip good">● 보통 날씨</span> 관객 차 절반이 빠지는 때는 보통 <b>공연 종료 후 약 ${dur(A.p50.med)}</b>(가운데 50% ${dur(A.p50.p25)}~${dur(A.p50.p75)}), 90%는 <b>종료 후 약 ${dur(A.p90.med)}</b>(${dur(A.p90.p25)}~${dur(A.p90.p75)})이에요(종료 시각이 확인된 지난 공연 ${A.shows}회 중앙값 · 전체 ${W.shows - W.wetShows}회 공연 시작 기준으로는 ${dur(W.dryMedian.p50)} / ${dur(W.dryMedian.p90)}).`;
    else txt = `<span class="chip good">● 보통 날씨</span> 관객 차 절반이 빠지는 때는 보통 공연 시작 후 ${dur(W.dryMedian.p50)}, 90%는 ${dur(W.dryMedian.p90)}예요(지난 공연 중앙값).`;
    $("egWeather").innerHTML = (note ? `<p class="muted small" style="margin:0 0 6px">${note}</p>` : "") + `<div class="eg-wx">${txt}</div>`;
  }
  $("egWx").addEventListener("change", renderWx);
  $("date").addEventListener("change", () => setTimeout(renderWx, 0));
  $("event").addEventListener("change", renderWx);

  // 차로 오는 관객에게만 보임 (이동 수단 토글은 audience.js에서 전환)
  const activeMode = document.querySelector("#mode button.on");
  if (activeMode) $("exitGate").hidden = activeMode.dataset.v !== "car";

  $("egSrc").innerHTML = `출처: ${J.source}. 방법: ${J.method}. KSPO DOME 공연 ${J.shows}회, 관객 차 ${J.cars.toLocaleString()}대. ` +
    `주차한 곳은 기록에 없어 들어온 문으로 대신했어요(공식 주차 안내의 문별 주차 구역). ` +
    (D ? `가는 방면별 둘레 도로: ${D.source}(공연 ${D.shows.length}회 출차 시간대·5분 간격 ${D.snapshots}회 수집, 상용 길찾기 API 호출 없음). ` : "") +
    (J.weather.afterEnd ? `공연 종료 후 출차 시간: ${J.weather.afterEnd.source}. ` : "") +
    `날씨: ${J.weatherSource}, 공연 ${J.weather.shows}회(${J.weather.period}). 계산일 ${J.built}. ` +
    `<a href="data-guide.html">데이터 설명 보기</a>`;
  renderGate();
  let tries = 0;
  const t = setInterval(() => { if ($("event").value || ++tries > 40) { clearInterval(t); renderWx(); } }, 250);
})();
