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
    $("parkingStatus").textContent = "출구 비교 자료 불러오기 실패";
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
  $("parkingStatus").hidden = true;
  const btn = (g, label, sub) =>
    `<button type="button" data-g="${g}" aria-pressed="false"><b>${label}</b><span>${sub}</span></button>`;
  box.innerHTML =
    ["북2", "동2", "남2"].map((g) => btn(g, J.byEntry[g].zones.join("·"), `${ZONE[g]} · ${GATE(g)} 진입`)).join("") +
    btn("other", "그 밖의 주차장", "서1·서2·남3·남4문 주차장");

  // 가는 방면 빠른 버튼 (북서·북동 / 남서·남동 방위 순서로 배치, 외부 길찾기 API 호출 없음)
  const wayBox = $("egWay");
  const dirByKey = {};
  ((D && D.directions) || []).forEach((d) => { dirByKey[d.key] = d; });
  if (wayBox) {
    const order = ["nw", "ne", "sw", "se"].filter((k) => dirByKey[k]);
    if (order.length) {
      wayBox.innerHTML =
        `<button type="button" data-w="none" class="on span-all" aria-pressed="true"><b>방면 선택 안 함</b></button>` +
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
        wayBox.dispatchEvent(new Event("park-direction-selected"));
      });
    } else {
      $("skipDirection").hidden = false;
    }
  }

  function selectZone(g, advance = true) {
    pick = g;
    box.querySelectorAll("button").forEach((x) => {
      const on = x.dataset.g === g;
      x.classList.toggle("on", on);
      x.setAttribute("aria-pressed", on ? "true" : "false");
    });
    renderGate();
    if (advance) $("exitGate").dispatchEvent(new Event("park-zone-selected"));
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
      gpsNote.textContent = "현재 위치 확인 중";
    } else if (g.status === "ok" && g.loc) {
      gpsBtn.textContent = "내 위치로 다시 찾기";
      const nearest = PARK_ZONE_REFS
        .map((r) => ({ ...r, dist: distMeters(g.loc.lat, g.loc.lng, r.lat, r.lng) }))
        .sort((a, b) => a.dist - b.dist)[0];
      if (nearest.dist <= 1200) {
        if (g.source === "exitGate" || pick === null) selectZone(nearest.gate, g.source === "exitGate");
        const zoneLabel = nearest.gate === "other" ? "그 밖의 주차장" : `${GATE(nearest.gate)} 구역(${J.byEntry[nearest.gate].zones.join("·")})`;
        gpsNote.innerHTML =
          `GPS 추천 구역 · ${zoneLabel}`;
      } else {
        gpsNote.innerHTML =
          "공원 밖 · 주차 구역 직접 선택";
      }
    } else if (g.status === "off") {
      gpsBtn.textContent = "현재 위치(GPS)로 주차한 곳 찾기";
      gpsNote.textContent = "현재 위치 표시 해제";
    } else if (g.status === "denied" || g.status === "error" || g.status === "unsupported") {
      gpsBtn.textContent = "현재 위치(GPS) 다시 확인";
      gpsNote.innerHTML = `<span class="chip warn">▲ 확인 안 됨</span> ${g.msg}`;
    }
  });

  function renderGate() {
    const out = $("egResult");
    if (!pick) return;

    if (pick === "other") {
      out.innerHTML = '<div class="eg-reco"><strong class="eg-gate">진입한 문으로 출차</strong></div>';
      return;
    }

    const entry = J.byEntry[pick];
    const direction = dirByKey[wayPick];
    const compareRoad = direction && entry.options.every(option => direction.byGate?.[option.gate]);
    const routes = entry.options.map(option => {
      const gate = option.gate;
      const parkDifference = gate === entry.best ? 0 : option.vs[entry.best].min;
      const road = compareRoad ? direction.byGate[gate] : null;
      return {
        gate,
        path: road ? road.via : J.way[gate],
        score: road ? +(parkDifference + road.roadMin).toFixed(1) : parkDifference,
      };
    }).sort((first, second) => first.score - second.score);

    const cards = routes.map((route, index) => {
      const difference = +(route.score - routes[0].score).toFixed(1);
      const label = difference === 0 ? "가장 빠름" : difference < 1 ? "시간 차이 작음" : `${index + 1}순위`;
      const detail = difference > 0 ? `<p class="exit-option-difference">가장 빠른 출구보다 약 ${difference}분 더 소요</p>` : "";
      return `<li class="exit-option${difference === 0 ? " is-recommended" : ""}">
        <div class="exit-option-header">
          <strong class="exit-option-name">${GATE(route.gate)}</strong>
          <span class="exit-option-rank">${label}</span>
        </div>
        ${detail}
        <p class="exit-option-route"><span>이동 경로</span><b>${route.path}</b></p>
      </li>`;
    });
    const scope = compareRoad ? `공원 출구부터 ${direction.hub}까지 포함` : "공원 출구까지 비교";
    out.innerHTML = `<p class="result-scope">올림픽공원 과거 출차 기록${compareRoad ? "과 서울시 도로 실측" : ""} 기준 · ${scope}</p>
      <ul class="exit-options" aria-label="출구별 비교">${cards.join("")}</ul>`;
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
      } catch (_) { return { none: "날씨 예보 불러오기 실패" }; }
    }
    const t0 = toMin(s.start) + 150, t1 = toMin(s.start) + 270;
    const hs = [];
    for (let m = t0; m <= t1; m += 60) {
      const day = new Date(s.date + "T00:00:00"); day.setMinutes(m);
      const ds = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, "0")}-${String(day.getDate()).padStart(2, "0")}`;
      const h = wxAll.find((x) => x.date === ds && x.hour === day.getHours());
      if (h) hs.push(h);
    }
    if (!hs.length) return { none: "공연 시간대 예보 없음 (24시간 이내 예보 제공)" };
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
      if (!s || s.venue !== "KSPO DOME") note = "KSPO DOME 공연 예보만 제공";
      else {
        const f = await forecastRain(s);
        if (mine !== wxSeq) return;
        if (f.none) note = f.none;
        else {
          rain = f.rain >= 1; cold = f.temp != null && f.temp < 0;
          note = `서울시 예보: 출차 시간대 비 ${Math.round(f.rain * 10) / 10}mm${f.temp != null ? `, 기온 ${f.temp}도` : ""}.`;
        }
      }
    }
    const T = W.effectTour;
    const A = W.afterEnd && W.afterEnd.dry;
    let txt;
    if (rain || cold) {
      const comparison = rain ? T.wet : T.cold;
      txt = `동일 공연 회차 ${comparison.shows}회 비교<br>
        차량 50% 출차 ${span(comparison.p50)}<br>
        차량 90% 출차 ${span(comparison.p90)}`;
    } else {
      const p50 = A ? A.p50.med : W.dryMedian.p50;
      const p90 = A ? A.p90.med : W.dryMedian.p90;
      txt = `공연 ${A ? "종료" : "시작"} 후 출차 중앙값<br>차량 50% 약 ${dur(p50)} · 90% 약 ${dur(p90)}`;
    }
    $("egWeather").innerHTML = (note ? `<p class="muted small" style="margin:0 0 6px">${note}</p>` : "") + `<div class="eg-wx">${txt}</div>`;
  }
  $("egWx").addEventListener("change", renderWx);
  $("date").addEventListener("change", () => setTimeout(renderWx, 0));
  $("event").addEventListener("change", renderWx);


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
