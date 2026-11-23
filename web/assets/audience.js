// 관객 화면
(async function () {
  const [events, links, allPlaces] = await Promise.all([
    loadJSON("events.json"), loadJSON("links.json"), loadPlaces(),
  ]);

  const today = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);
  const upcoming = events.filter((e) => e.date >= today && e.times.length);
  const byDate = groupByDate(upcoming);
  let live = null;
  let places = placesFor(allPlaces, "KSPO DOME");   // 고른 공연장 기준 장소 정보

  const $ = (id) => document.getElementById(id);
  const dateSel = $("date"), evSel = $("event");

  // 날짜 목록 (다회차 공연일은 회차 수도 함께 표시)
  [...byDate.keys()].forEach((d) => {
    const dt = new Date(d + "T00:00:00");
    const dayEvents = byDate.get(d);
    const showCnt = dayEvents.reduce((s, e) => s + e.times.length, 0);
    const countTxt = showCnt > dayEvents.length
      ? `공연 ${dayEvents.length}개(${showCnt}회)`
      : `공연 ${dayEvents.length}개`;
    const o = document.createElement("option");
    o.value = d;
    o.textContent = `${d.slice(5).replace("-", "/")}(${DOW[dt.getDay()]}) · ${countTxt}`;
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
    // 예정 종료 = 시작 + 예매처(공식 판매처) 관람시간
    const runMin = ev.runMin || null;
    const endMin = runMin ? startMin + runMin : null;
    // runFrom: seller = 예매처 페이지에서 읽음, park = 올림픽공원 공식 일정의 관람시간 칸 (scripts/28이 매일 갱신)
    const runLink = ev.runSeller
      ? (ev.runUrl ? `<a href="${ev.runUrl}" target="_blank" rel="noopener">${ev.runSeller} 예매 페이지</a>` : `${ev.runSeller} 예매 페이지`) : "";
    const checked = ev.runChecked ? ` (${ev.runChecked} 확인)` : "";
    let runSrc;
    if (ev.runFrom === "park") {
      runSrc = (runMin ? `출처: 올림픽공원 공식 공연 일정의 관람시간 '${ev.runText}'${checked}`
        : `올림픽공원 공식 공연 일정에 관람시간 안내가 없어요${checked}`)
        + (runLink ? ` · 예매처: ${runLink}` : "");
    } else if (ev.runSeller) {
      runSrc = runMin ? `출처: ${runLink} 관람시간 '${ev.runText}'${checked}`
        : `${runLink}에 관람시간 안내가 없어요${checked}`;
    } else {
      runSrc = "예매처 관람시간은 아직 확인 전이에요";
    }
    const runNote = runMin
      ? `${runSrc}. 앙코르 등으로 실제로는 더 늦게 끝날 때가 많아요.`
      : `${runSrc}.`;

    $("eventInfo").innerHTML = `
      <div class="event-summary">
        <div class="event-head">
          <div class="title">${ev.title}</div>
          <div class="chips" style="margin-top:0">
            <span class="chip accent">${ev.venue}</span>
            <span class="chip ${lv.cls}">${lv.sym} 혼잡 ${lv.label}</span>
          </div>
        </div>
        <div class="stat-strip">
          <div class="stat-item">
            <div class="sk">공연 시작</div>
            <div class="sv">${start}</div>
          </div>
          <div class="stat-item">
            <div class="sk">예정 종료${runMin ? ` (관람시간 ${runMin}분)` : ""}</div>
            <div class="sv">${runMin ? toHHMM(endMin) : "관람시간 안내 없음"}</div>
          </div>
          <div class="stat-item">
            <div class="sk">이날 공원 전체 규모</div>
            <div class="sv">공연 ${sameDay.length}개 · 약 ${seats.toLocaleString()}석</div>
          </div>
        </div>
        <p class="muted small" style="margin:8px 0 0">${runNote}</p>
      </div>`;

    $("walkSrc").textContent = places.venueKnown ? places.walkSource
      : `${ev.venue} 위치는 아직 계산 전이라 KSPO DOME 기준이에요`;
    renderTransit();
  }

  function renderTransit() {
    const sorted = places.stations.slice().sort((a, b) => a.walkMin - b.walkMin);
    $("stations").innerHTML = `<tr><th>역 이름</th><th>운행 노선</th><th>${places.dome.name}까지 도보</th></tr>` +
      sorted.map((s, idx) => `<tr>
        <td class="nowrap">${s.name} ${idx === 0 ? `<span class="chip accent" style="padding:1px 7px;font-size:11px">최단</span>` : ""}</td>
        <td>${lineBadgesHTML(s.line)}</td>
        <td><b>약 ${s.walkMin}분</b>${s.walkSrc === "TMAP 보행자 경로" ? "" : ` <span class="muted small">(추정)</span>`}</td>
      </tr>`).join("");
    const near = sorted[0];
    $("stationTip").innerHTML = `<b>${places.dome.name}</b>은 <b>${near.name}(${near.line})</b>에서 가장 가까워요.` +
      (near.key === "olympic5" ? " 5호선은 강동역에서 하남검단산행과 갈라지니 꼭 <b>마천행</b> 열차를 확인하세요." : "");
  }

  // 공연장이 바뀌면 지도에서 그 공연장을 표시하고 걷는 길도 그 공연장 기준으로
  function showVenueOnMaps() {
    drawRoadMap($("map"), links, places, live ? live.roads : null);
    if (m3) m3.setVenue(places);
  }

  // 이동 방법 전환
  document.querySelectorAll("#mode button").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll("#mode button").forEach((x) => x.classList.toggle("on", x === b));
    $("exitGate").hidden = b.dataset.v !== "car";
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
      start3D(live);
    } else start3D(null);
    // 실시간 연결이면 2분마다 새로 고침
    if (live && live.source === "live") setInterval(async () => {
      try {
        live = await loadLive();
        drawRoadMap($("map"), links, places, live.roads);
        if (m3) m3.update(live);
        $("roadNote").textContent = liveNote(live);
      } catch (_) {}
    }, 120000);
  } catch (e) {
    start3D(null);
    $("roadNote").textContent = "최근 수집값을 불러오지 못했어요(" + e.message + "). 도로는 회색으로 표시돼요.";
  }
})();
