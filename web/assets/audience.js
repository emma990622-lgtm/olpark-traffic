// 관객 화면
(async function () {
  loadParkNight();
  const [events, links, allPlaces, exits] = await Promise.all([
    loadJSON("events.json"), loadJSON("links.json"), loadPlaces(), loadJSON("exits_2024_07.json"),
    loadSubwayTimes(),
  ]);
  const ref = kspoReference(exits);
  // 선택 자료: 공연 후 출차 소요(과거 기록 분석), 역 주차장 → 공원 주차장 운전 시간
  const optJSON = (n) => loadJSON(n).catch(() => null);
  const [exitProf, stDrive, cg] = await Promise.all([optJSON("exit_profile.json"), optJSON("station_drive.json"), optJSON("congestion_summary.json")]);
  let liveDrive = null;
  fetch("/api/drivetime").then((r) => (r.ok ? r.json() : null)).then((d) => { if (d && evSel.value) { liveDrive = d; render(); } }).catch(() => {});
  const today = new Date().toISOString().slice(0, 10);
  const upcoming = events.filter((e) => e.date >= today && e.times.length);
  const byDate = groupByDate(upcoming);
  let live = null;
  let places = placesFor(allPlaces, "KSPO DOME");   // 고른 공연장 기준 장소 정보
  let tMode = "go";                                   // 환승주차 탭: go(공연장 갈 때) / out(공연장에서 나올 때)
  document.getElementById("options").addEventListener("click", (e) => {
    const b = e.target.closest("[data-tmode]");
    if (b && b.dataset.tmode !== tMode) { tMode = b.dataset.tmode; render(); }
  });

  const $ = (id) => document.getElementById(id);
  const dateSel = $("date"), evSel = $("event");

  // 날짜 목록
  [...byDate.keys()].forEach((d) => {
    const dt = new Date(d + "T00:00:00");
    const o = document.createElement("option");
    o.value = d; o.textContent = `${d.slice(5).replace("-", "/")}(${DOW[dt.getDay()]}) · 공연 ${byDate.get(d).length}개`;
    dateSel.appendChild(o);
  });
  // 기본값: 가장 가까운 KSPO DOME 공연일
  const firstBig = upcoming.find((e) => e.venue === "KSPO DOME");
  if (firstBig) dateSel.value = firstBig.date;

  function fillEvents() {
    evSel.innerHTML = "";
    byDate.get(dateSel.value).forEach((e, i) => {
      e.times.forEach((t) => {
        const o = document.createElement("option");
        o.value = i + "|" + t;
        o.textContent = `${t} ${e.venue} · ${e.title}`;
        evSel.appendChild(o);
      });
    });
    const big = byDate.get(dateSel.value).findIndex((e) => e.venue === "KSPO DOME");
    if (big >= 0) evSel.value = big + "|" + byDate.get(dateSel.value)[big].times[0];
    render();
  }

  function current() {
    const [i, t] = evSel.value.split("|");
    return { ev: byDate.get(dateSel.value)[+i], start: t };
  }

  function render() {
    const { ev, start } = current();
    const venueChanged = places.venueName !== ev.venue;
    places = placesFor(allPlaces, ev.venue);
    if (venueChanged) showVenueOnMaps();
    const sameDay = byDate.get(dateSel.value);
    const seats = sameDay.reduce((s, e) => s + (e.seats || 0), 0);
    const lv = levelOf(seats);
    const startMin = toMin(start);
    const endMin = startMin + DEFAULT_SHOW_MIN;

    $("eventInfo").innerHTML = `
      <div class="event-head"><div class="title">${ev.title}</div></div>
      <div class="chips">
        <span class="chip accent">${ev.venue}</span>
        <span class="chip">시작 ${start}</span>
        <span class="chip">예상 종료 ${toHHMM(endMin)} (공연마다 다름)</span>
        <span class="chip ${lv.cls}">이날 공원 공연 ${sameDay.length}개 · 좌석 약 ${seats.toLocaleString()}석 · 혼잡 ${lv.label}</span>
      </div>`;

    renderCar(ev, startMin, endMin, seats, lv);
    $("walkSrc").textContent = places.venueKnown ? places.walkSource
      : `${ev.venue} 위치는 아직 계산 전이라 KSPO DOME 기준이에요`;
    $("subwayNote").textContent = subwayNote();
    renderTransit();
  }

  // 역 주차장 → 공원 주차장 운전 시간: 공연별 예측(TMAP 타임머신) > 지금 실시간 > 계산해 둔 값
  function driveOn(name, ev, start) {
    if (stDrive && stDrive.predicted) {
      const p = stDrive.predicted[`${dateSel.value} ${start}`];
      if (p && p[name] != null) return { min: p[name], src: `TMAP 예측, 시작 ${durText(stDrive.leadMin)} 전 출발` };
    }
    if (liveDrive && liveDrive.lots && liveDrive.lots[name] && liveDrive.lots[name].min != null)
      return { min: liveDrive.lots[name].min, src: `TMAP 실시간 ${String(liveDrive.time).slice(11, 16)}` };
    if (stDrive && stDrive.now && stDrive.now[name]) return { min: stDrive.now[name].min, src: `TMAP ${stDrive.measured} 기준` };
    return null;
  }

  function renderCar(ev, startMin, endMin, seats, lv) {
    const stay = (endMin + 30) - (startMin - 60);
    const lots = places.lots;
    const park = lots.filter((l) => l.kind === "park");
    const walk = lots.filter((l) => l.kind === "walk");
    const transfer = lots.filter((l) => l.kind === "transfer" && openAt(l.hours, endMin + 60));
    const closed = lots.filter((l) => l.kind === "transfer" && !openAt(l.hours, endMin + 60));
    const stOf = (key) => places.stations.find((s) => s.key === key);
    const liveOf = (name) => {
      if (!live || !live.lots) return null;
      const k = Object.keys(live.lots).find((n) => n.startsWith(name));
      return k ? live.lots[k] : null;
    };

    // 귀가 혼잡 참고: KSPO DOME 공연은 2024-07 실제 기록, 그 외는 아직 없음
    const isBig = ev.venue === "KSPO DOME";
    const ep = exitProf && exitProf.summary;
    const peakText = isBig && ep
      ? `공연 시작 약 ${durText(ep.surgeMin.med)} 뒤(${toHHMM(startMin + ep.surgeMin.med)} 무렵)부터 출차가 몰려요.
         그때부터 공원 주차장 차의 <b>절반이 빠지는 데 약 ${ep.t50.med}분</b>, <b>90%는 약 ${ep.t90.med}분</b> 걸려요
         <span class="muted small">(보통 ${ep.t50.p25}~${ep.t50.p75}분 / ${ep.t90.p25}~${ep.t90.p75}분, KSPO DOME 공연 ${ep.shows}회 입출차 기록${ep.bySource && ep.bySource["2024"] && ep.bySource["2025"]
           ? `: 2024년 7월 전체 기록 ${ep.bySource["2024"].shows}회는 절반 ${ep.bySource["2024"].t50}분, 2025년 일부 기록 ${ep.bySource["2025"].shows}회는 ${ep.bySource["2025"].t50}분` : ""})</span>`
      : isBig
        ? `공연 시작 약 ${durText(ref.lagMed)} 뒤(${toHHMM(startMin + ref.lagMed)} 무렵) 출차가 가장 몰려요. 15분에 ${ref.peakMin}~${ref.peakMax}대`
        : "이 공연장의 출차 기록은 2025 데이터로 채울 예정이에요";

    // 추천 (예측 모델 연결 전: 공연 규모 규칙)
    let reco;
    if (lv.key === "focus") {
      reco = `오늘은 <b>큰 공연</b>이 있어요. 공원 주차장은 일찍 차고 공연 후 출차가 한꺼번에 몰려요.
              <b>천호역 공영주차장에 대고 5호선</b>을 타면 공원 출구 정체를 피할 수 있어요.`;
    } else if (lv.key === "caution") {
      reco = `공연 규모가 중간이에요. 공원 주차장을 쓰되, 공연이 끝나고 <b>10~20분 늦게 출발</b>하는 것도 방법이에요.`;
    } else {
      reco = `오늘은 비교적 한산할 것으로 보여요. <b>공원 주차장</b>이 가장 편해요.`;
    }

    $("reco").innerHTML = `<div class="reco">${reco}
      <div class="muted small" style="margin-top:6px">지금은 공연 규모 기준 안내예요. 2025년 입출차 데이터로 만든 예측이 연결되면 시간까지 계산해 드려요.</div></div>`;

    const notices = [];
    if (endMin > toMin("21:30")) notices.push("공원 차량 출입은 22시까지예요(심야 행사 때는 조정). 늦게 끝나는 공연은 출차 안내를 확인하세요.");
    if (closed.length) notices.push(`공연 후 문을 닫아 뺀 주차장: ${closed.map((c) => c.name).join(", ")}`);

    const parkSum = live && live.summary ? Number(live.summary["주차합계_parking_sum"]) : NaN;
    const pa = Number.isFinite(parkSum) ? parkActual(parkSum) : null;
    const parkLive = pa
      ? `주차된 차 약 <b>${pa.est.toLocaleString()}대</b> · 빈자리 약 ${Math.max(0, park[0].cap - pa.est).toLocaleString()}면
         <span class="muted small">(${String(live.summary["수집시각"]).slice(11, 16)} 기준 추정. 한국체육산업개발 실시간 값 ${parkSum.toLocaleString()}대에서 출차 기록이 없는 장기 주차 약 ${pa.ghost.toLocaleString()}대를 뺐어요)</span>`
      : "공연일에 5분마다 수집";

    $("options").innerHTML = `
      ${notices.map((n) => `<div class="notice">${n}</div>`).join("")}
      <div class="opt ${lv.key === "normal" ? "recommended" : ""}">
        <div class="kind">공원 안</div>
        <h3>${park[0].name}</h3>
        <dl>
          <dt>${places.dome.name}까지</dt><dd>도보 약 ${park[0].walkMin}분 (구역마다 다름)</dd>
          <dt>예상 요금</dt><dd>${won(parkingFee(park[0], stay))} <span class="muted small">(${park[0].fee})</span></dd>
          <dt>도착할 때</dt><dd>${cg ? `KSPO DOME 저녁 공연 날 ${cg.kspoEveningDays}일 중 <b>${cg.kspoDaysWithFull}일</b>은 일부 구역이 만차였어요.
            첫 만차는 보통 공연 시작 <b>약 ${cg.hoursBefore.med}시간 전</b>(${cg.hoursBefore.p25}~${cg.hoursBefore.p75}시간 전)${isBig ? `, 오늘이면 <b>${toHHMM(startMin - cg.hoursBefore.med * 60)} 무렵</b>` : ""}이에요.
            <span class="muted small">(구역 ${cg.zones}곳 중 보통 ${cg.fullZones.med}곳, 한국체육산업개발 주차장 혼잡도 기록 ${cg.period[0].slice(0, 7)}~${cg.period[1].slice(0, 7)})</span>`
            : `만차 예상 시각 <span class="tag-pending">자료 준비 중</span>`}</dd>
          <dt>귀가할 때</dt><dd>${peakText}</dd>
          <dt>지금 주차</dt><dd>${parkLive}</dd>
        </dl>
      </div>
      <div class="opt">
        <div class="kind">걸어올 수 있는 곳</div>
        <h3>공원 바깥쪽 주차장 ${walk.length}곳</h3>
        <dl>
          <dt>${places.dome.name}까지</dt><dd>도보 약 ${Math.min(...walk.map((w) => w.walkMin))}~${Math.max(...walk.map((w) => w.walkMin))}분</dd>
          <dt>귀가할 때</dt><dd>공원 출구 쏠림을 덜 받는지 <span class="tag-pending">공연일 실측으로 확인 예정</span></dd>
          <dt>빈자리</dt><dd>실시간 정보 없음</dd>
        </dl>
        <div class="lots"><table>
          <tr><th>주차장</th><th>면수</th><th>도보</th><th>예상 요금</th></tr>
          ${walk.map((w) => `<tr><td>${w.name}</td><td>${w.cap}</td><td>${w.walkMin}분</td><td>${won(parkingFee(w, stay))}</td></tr>`).join("")}
        </table></div>
      </div>
      <div class="opt ${lv.key === "focus" ? "recommended" : ""}">
        <div class="kind">환승주차 (역 주차장 + 지하철)</div>
        <h3>공원 정체를 피하는 방법</h3>
        <div class="toggle tabs" role="tablist">
          <button data-tmode="go" class="${tMode === "go" ? "on" : ""}" role="tab">공연장 갈 때</button>
          <button data-tmode="out" class="${tMode === "out" ? "on" : ""}" role="tab">공연장에서 나올 때</button>
        </div>
        ${tMode === "go" ? transferGo(ev, startMin, park, stOf, liveOf, stay, transfer) : transferOutHTML(ev, startMin, endMin, park, stOf, transfer)}
      </div>`;
  }

  // 환승주차 · 공연장 갈 때: 관객이 2시간 넘게 나눠서 오므로 평소 시간으로 계산
  function transferGo(ev, startMin, park, stOf, liveOf, stay, transfer) {
    return `<p class="muted small">주차장에서 ${places.dome.name}까지. 관객이 나눠서 오므로 평소 시간으로 계산했어요. 도보는 TMAP, 지하철은 ${SUBWAY.official ? "서울교통공사 표준 운행시간" : "가정값"}이에요.</p>
      <div class="lots">
      ${transfer.map((t) => {
        const st = t.station ? stOf(t.station) : null;
        const lv2 = liveOf(t.name);
        const free = lv2 && lv2.now != null ? `빈자리 <b>${Math.max(0, lv2.cap - lv2.now)}면</b> <span class="muted small">(${String(lv2.time).slice(11, 16)} 기준)</span>` : (live && live.source === "live" ? "빈자리 정보 없음" : "빈자리: 공연일에 수집");
        const tt = transferTotal(t, st);
        return `<div class="tlot${t.notRecommended ? " skip" : ""}">
          <div class="tname">${t.name} <span class="muted small">${t.cap}면 · ${t.hours}</span></div>
          <div>${t.board ? t.board + "에서 " : ""}${t.route}</div>
          ${tt ? `<div class="ttotal">주차장 → ${places.dome.name} 총 <b>약 ${tt.total}분</b>
              <span class="muted small">· 공연 시작 30분 전에 닿으려면 ${toHHMM(startMin - 30 - tt.total)}까지 주차</span></div>
            <div class="muted small">도보 ${tt.walk1}분 + 대기 ${tt.wait}분 + 지하철 ${tt.ride}분${tt.transfer ? ` + 환승 ${tt.transfer}분` : ""} + 내려서 도보 ${tt.walk2}분 · 예상 요금 ${won(parkingFee(t, stay))}</div>`
            : `<div class="muted small">예상 요금 ${won(parkingFee(t, stay))}</div>`}
          ${(() => { const dv = driveOn(t.name, ev, toHHMM(startMin)); if (!dv) return "";
            const parkWalk = park[0].walkMin;
            return `<div class="small">차로 공원 주차장까지 더 가면 <b>약 ${dv.min}분</b> + 도보 ${parkWalk}분 = 총 ${dv.min + parkWalk}분
              <span class="muted">(${dv.src})</span>${tt ? (() => { const gap = tt.total - (dv.min + parkWalk);
              return gap > 0 ? `<br>도착만 보면 차로 가는 게 ${gap}분 빨라요. 나올 때 시간은 옆 탭에서 비교해 보세요` : `<br>여기 대고 지하철이 도착도 빨라요`; })() : ""}</div>`; })()}
          <div class="small">${free}</div>
          ${t.notRecommended ? `<div class="small warnline">비추천: ${t.notRecommended}</div>` : ""}
        </div>`;
      }).join("")}
      </div>`;
  }

  // 환승주차 · 공연장에서 나올 때: 관객이 한꺼번에 역으로 몰리는 경우
  function transferOutHTML(ev, startMin, endMin, park, stOf, transfer) {
    const ep = exitProf && ev.venue === "KSPO DOME" ? exitProf.summary : null;
    const parkWalk = Math.round(park[0].walkMin * CROWD.walkFactor);
    const parkOut = ep ? parkWalk + ep.t50.med : null;
    const rows = transfer.map((t) => {
      const st = t.station ? stOf(t.station) : null;
      const a = transferOut(t, st, ev, "med"), b = transferOut(t, st, ev, "high");
      if (!a) return `<div class="tlot"><div class="tname">${t.name}</div><div class="muted small">경로 정보 없음</div></div>`;
      return `<div class="tlot${t.notRecommended ? " skip" : ""}">
        <div class="tname">${t.name} <span class="muted small">${t.hours}</span></div>
        <div>${st.name}에서 ${t.board ? t.board.replace(/역$/, "") + "역 방향" : ""} 타고 돌아가기</div>
        <div class="ttotal">공연장 → 주차장 빠져나오기까지 <b>약 ${a.total}분</b>${b.total > a.total ? ` <span class="muted small">(관객이 많으면 약 ${b.total}분)</span>` : ""}
          <span class="muted small">· ${toHHMM(endMin)}에 끝나면 ${toHHMM(endMin + a.total)}쯤 출발</span></div>
        <div class="muted small">역까지 도보 ${a.walk2}분 + 개찰·승강장 줄 ${a.crowd}분 + 열차 대기 ${a.wait}분 + 지하철 ${a.ride}분${a.transfer ? ` + 환승 ${a.transfer}분` : ""} + 도보 ${a.walk1}분 + 출차 ${a.lotExit}분</div>
        <div class="small">${a.riders > 1000 ? `이 역으로 약 ${a.riders.toLocaleString()}명이 한꺼번에 몰려요` : "이 역은 공연 날에도 승차 인원이 거의 늘지 않아요"}</div>
        ${parkOut ? `<div class="small">${parkOut <= a.total ? `공원 주차장(약 ${parkOut}분)보다 ${a.total - parkOut}분 더 걸려요` : `공원 주차장(약 ${parkOut}분)보다 <b>${parkOut - a.total}분 빨라요</b>`}</div>` : ""}
        ${t.notRecommended ? `<div class="small warnline">비추천: ${t.notRecommended}</div>` : ""}
      </div>`;
    }).join("");
    return `<p class="muted small">공연이 끝나면 관객이 한꺼번에 역으로 몰려요. ${CROWD.source}를 보면 KSPO DOME 공연 날 올림픽공원역 승차가 평소보다 약 ${CROWD.riders.med.toLocaleString()}명 늘어요(9호선 71%, 5호선 29%). 공연 좌석 수에 맞춰 줄여 계산했어요.</p>
      ${ep ? `<div class="notice">비교: 공원 주차장은 차까지 도보 ${parkWalk}분 + 출차 대기(차 절반이 빠지는 데) 약 ${ep.t50.med}분 = <b>약 ${parkOut}분</b></div>` : ""}
      <div class="lots">${rows}</div>
      <p class="muted small">개찰구 처리량(분당 ${CROWD.gatePerMin}명), 열차 간격, 인파 속 도보 속도(30% 느림)는 가정값이에요. 11/21·22 공연일 실측으로 고칠 예정이에요.</p>`;
  }

  function renderTransit() {
    const sorted = places.stations.slice().sort((a, b) => a.walkMin - b.walkMin);
    $("stations").innerHTML = `<tr><th>역</th><th>노선</th><th>${places.dome.name}까지 도보</th></tr>` +
      sorted.map((s) => `<tr><td>${s.name}</td><td>${s.line}</td><td>약 ${s.walkMin}분${s.walkSrc === "TMAP 보행자 경로" ? "" : " (추정)"}</td></tr>`).join("");
    const near = sorted[0];
    $("stationTip").textContent = `${places.dome.name}은 ${near.name}(${near.line})이 가장 가까워요.` +
      (near.key === "olympic5" ? " 5호선은 강동역에서 갈라지니 마천행을 타세요." : "");
  }

  // 공연장이 바뀌면 지도에서 그 공연장을 표시하고 걷는 길도 그 공연장 기준으로
  function showVenueOnMaps() {
    drawRoadMap($("map"), links, places, live ? live.roads : null);
    if (m3) m3.setVenue(places);
  }

  // 이동 방법 전환
  document.querySelectorAll("#mode button").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll("#mode button").forEach((x) => x.classList.toggle("on", x === b));
    $("carSection").hidden = b.dataset.v !== "car";
    $("transitSection").hidden = b.dataset.v !== "transit";
  }));
  dateSel.addEventListener("change", fillEvents);
  evSel.addEventListener("change", render);

  // 지도 (먼저 회색으로 그리고, 수집값이 오면 다시 그림)
  $("legend").innerHTML = legendHTML();
  let m3 = null;
  drawRoadMap($("map"), links, places, null);
  const start3D = async (lv) => {
    try {
      m3 = await initMap3D($("map3d"), { links, places, live: lv, venues: allPlaces.venues });
      if (!m3) throw new Error("3D 미지원");
      m3.setVenue(places);
      $("legend3d").innerHTML = legend3DHTML(m3.buildingSrc);
    } catch (e) {
      $("map3d").classList.add("failed"); $("flat").open = true;
      $("legend3d").innerHTML = `<p class="muted small">3D 지도를 열 수 없어 평면 지도로 보여 드려요 (${e.message || e}).</p>`;
    }
  };
  fillEvents();
  try {
    live = await loadLive();
    if (live) {
      drawRoadMap($("map"), links, places, live.roads);
      $("roadNote").textContent = liveNote(live);
      render();
      start3D(live);
    } else start3D(null);
    // 실시간 연결이면 2분마다 새로 고침
    if (live && live.source === "live") setInterval(async () => {
      try { live = await loadLive(); drawRoadMap($("map"), links, places, live.roads); if (m3) m3.update(live); $("roadNote").textContent = liveNote(live); render(); } catch (_) {}
    }, 120000);
  } catch (e) {
    start3D(null);
    $("roadNote").textContent = "최근 수집값을 불러오지 못했어요(" + e.message + "). 도로는 회색으로 표시돼요.";
  }
})();
