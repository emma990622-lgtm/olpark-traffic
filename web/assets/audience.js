// 관객 화면
(async function () {
  loadParkNight();
  const [events, links, allPlaces, exits] = await Promise.all([
    loadJSON("events.json"), loadJSON("links.json"), loadPlaces(), loadJSON("exits_2024_07.json"),
    loadSubwayTimes(),
  ]);
  const ref = kspoReference(exits, await loadJSON("kspo_waves.json").catch(() => null));
  // 선택 자료: 공연 후 출차 소요(과거 기록 분석), 역 주차장 → 공원 주차장 운전 시간
  const optJSON = (n) => loadJSON(n).catch(() => null);
  const [exitProf, stDrive, cg, audCar] = await Promise.all([
    optJSON("exit_profile.json"), optJSON("station_drive.json"), optJSON("congestion_summary.json"),
    optJSON("audience_car.json"),
  ]);
  let liveDrive = null;
  fetch("/api/drivetime").then((r) => (r.ok ? r.json() : null)).then((d) => {
    if (d && evSel.value) { liveDrive = d; render(); }
  }).catch(() => {});

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

  function lotFreeChip(lv2, capFallback) {
    if (!lv2 || lv2.now == null) {
      return `<span class="chip">${live && live.source === "live" ? "실시간 정보 없음" : "공연일에 수집"}</span>`;
    }
    const cap = lv2.cap || capFallback || 1;
    const free = Math.max(0, cap - lv2.now);
    const ratio = free / cap;
    const cls = free === 0 || ratio < 0.12 ? "bad" : ratio < 0.3 ? "warn" : "good";
    const sym = cls === "bad" ? "■" : cls === "warn" ? "▲" : "●";
    return `<span class="chip ${cls}">${sym} 빈자리 ${free.toLocaleString()}면 <span style="font-weight:500">(${String(lv2.time).slice(11, 16)})</span></span>`;
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
    // 예정 종료 = 시작 + 예매처(공식 판매처) 관람시간. 안내가 없으면 아래 계산에만 150분을 가정한다.
    const runMin = ev.runMin || null;
    const endMin = startMin + (runMin || DEFAULT_SHOW_MIN);
    const runLink = ev.runSeller ? `<a href="${ev.runUrl}" target="_blank" rel="noopener">${ev.runSeller} 예매 페이지</a>` : "";
    const runSrc = !ev.runSeller ? "예매처 관람시간은 아직 확인 전이에요"
      : runMin ? `출처: ${runLink} 관람시간 '${ev.runText}' (${ev.runChecked} 확인)`
      : `${runLink}에 관람시간 안내가 없어요 (${ev.runChecked} 확인)`;
    const runNote = runMin
      ? `${runSrc}. 앙코르 등으로 실제로는 더 늦게 끝날 때가 많아요.`
      : `${runSrc}. 아래 주차·출차 계산은 공연 시간을 ${DEFAULT_SHOW_MIN}분으로 가정했어요.`;

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
            <div class="sv">${runMin ? toHHMM(endMin) : "예매처 안내 없음"}</div>
          </div>
          <div class="stat-item">
            <div class="sk">이날 공원 전체 규모</div>
            <div class="sv">공연 ${sameDay.length}개 · 약 ${seats.toLocaleString()}석</div>
          </div>
        </div>
        <p class="muted small" style="margin:8px 0 0">${runNote}</p>
      </div>`;

    renderCar(ev, startMin, endMin, seats, lv, sameDay);
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

  function renderCar(ev, startMin, endMin, seats, lv, sameDay) {
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

    // 귀가 혼잡 참고: KSPO DOME 공연은 2024-07·2025 실제 기록, 그 외는 아직 없음
    const isBig = ev.venue === "KSPO DOME";
    const hasBigSameDay = sameDay.some((e) => e.venue === "KSPO DOME");
    const ep = exitProf && exitProf.summary;
    const peakText = isBig && ep
      ? `공연 시작 약 ${durText(ep.surgeMin.med)} 뒤(${toHHMM(startMin + ep.surgeMin.med)} 무렵)부터 출차가 몰려요.
         그때부터 관객 차의 <b>절반이 빠지는 데 약 ${ep.t50.med}분</b>, <b>90%는 약 ${ep.t90.med}분</b> 걸려요
         <span class="muted small">(보통 ${ep.t50.p25}~${ep.t50.p75}분 / ${ep.t90.p25}~${ep.t90.p75}분, KSPO DOME 공연 ${ep.shows}회 입출차 기록${ep.bySource && ep.bySource["2024"] && ep.bySource["2025"]
           ? `: 2024년 7월 전체 기록 ${ep.bySource["2024"].shows}회는 절반 ${ep.bySource["2024"].t50}분, 2025년 일부 기록 ${ep.bySource["2025"].shows}회는 ${ep.bySource["2025"].t50}분` : ""})</span>`
      : isBig
        ? `공연 시작 약 ${durText(ref.lagMed)} 뒤(${toHHMM(startMin + ref.lagMed)} 무렵) 출차가 가장 몰려요. 15분에 ${ref.peakMin}~${ref.peakMax}대 <span class="muted small">(공원 주차장 전체 출차, 평소 방문 차 포함)</span>`
        : "이 공연장의 출차 기록은 2025 데이터로 채울 예정이에요";

    // 추천 (예측 모델 연결 전: 공연 규모 기반 분산 안내)
    let reco, recoCls = "";
    if (lv.key === "focus") {
      reco = `오늘은 <b>큰 공연</b>이 있어요. 공원 주차장은 일찍 차고 공연 후 출차가 한꺼번에 몰려요.
              <b>천호역 공영주차장에 대고 5호선</b>으로 환승하면 출구 혼잡을 덜고 편하게 귀가할 수 있어요.`;
    } else if (lv.key === "caution") {
      recoCls = " is-caution";
      reco = `공연 규모가 중간이에요. 공원 주차장을 쓰되, 공연이 끝나고 <b>10~20분 여유를 두고 출발</b>하면 출구 대기 시간을 줄일 수 있어요.`;
    } else {
      recoCls = " is-normal";
      reco = `오늘은 비교적 한산할 것으로 보여요. <b>공원 주차장</b>을 이용하기 가장 편해요.`;
    }

    $("reco").innerHTML = `<div class="reco${recoCls}">
      <div class="reco-kicker">${lv.sym} 오늘의 주차 추천</div>
      <div>${reco}</div>
      <div class="muted small" style="margin-top:6px">지금은 공연 규모 기준 안내예요. 2025년 입출차 데이터로 만든 예측이 연결되면 시간까지 계산해 드려요.</div>
    </div>`;

    const notices = [];
    if (endMin > toMin("21:30")) notices.push("공원 차량 출입은 22시까지예요(심야 행사 때는 조정). 늦게 끝나는 공연은 현장 출차 안내를 확인해 주세요.");
    if (closed.length) notices.push(`공연 후 문을 닫아 제외한 주차장: ${closed.map((c) => c.name).join(", ")}`);

    const parkSum = live && live.summary ? Number(live.summary["주차합계_parking_sum"]) : NaN;
    const pa = Number.isFinite(parkSum) ? parkActual(parkSum) : null;
    let parkLiveBox = `<div class="live-lot-box"><span class="muted small">지금 주차 현황은 공연일에 5분마다 수집해요.</span></div>`;
    if (pa) {
      const freeEst = Math.max(0, park[0].cap - pa.est);
      const occPct = Math.min(100, Math.round((pa.est / park[0].cap) * 100));
      const occCls = occPct >= 85 ? "bad" : occPct >= 60 ? "warn" : "good";
      const occLabel = occPct >= 85 ? "■ 혼잡" : occPct >= 60 ? "▲ 보통" : "● 여유";
      parkLiveBox = `
        <div class="live-lot-box">
          <div class="live-lot-head">
            <span class="live-badge">지금 공원 주차 추정 (${String(live.summary["수집시각"]).slice(11, 16)} 기준)</span>
            <span class="chip ${occCls}">${occLabel} · 보정 점유 약 ${occPct}%</span>
          </div>
          <div class="live-lot-nums">
            빈자리 약 <span class="free-num">${freeEst.toLocaleString()}면</span>
            <span class="muted"> · 주차된 차 약 <b>${pa.est.toLocaleString()}대</b> / ${park[0].cap.toLocaleString()}면</span>
          </div>
          <div class="occ-bar ${occCls === "good" ? "" : "is-" + occCls}"><span style="width:${occPct}%"></span></div>
          <div class="muted small">한국체육산업개발 실시간 값 ${parkSum.toLocaleString()}대에서 출차 기록이 안 닫혀 실제로는 없는 차 약 ${pa.ghost.toLocaleString()}대(새벽 값 − 새벽에 실제로 서 있는 약 225대)를 뺀 보정값이에요.</div>
        </div>`;
    }

    // 관객 성향(연령·성별)으로 본 예상 관객 차: 같은 가수의 지난 공연 관객 구성이 있을 때만 (scripts/15)
    let carCrowdText = "";
    const ac = audCar && audCar.meaningful && isBig && (audCar.upcoming || []).find((u) => u.date === dateSel.value && u.match && u.match.length);
    if (ac) {
      const idol = (audCar.presets || [])[0];
      const base = idol ? (ac.dayType === "fri" || ac.dayType === "wk" ? idol.fri.pred : idol.sun.pred) : null;
      const ratio = base ? ac.pred / base : null;
      const many = ratio && ratio >= 1.4, few = ratio && ratio <= 0.8;
      carCrowdText = `지난 같은 가수 공연 관객은 평균 약 <b>${Math.round(ac.meanAge)}세</b>였어요.
        ${many ? "연령대가 높은 공연은 <b>차로 오는 관객이 많은 편</b>이라 공원 주차장이 일찍 찰 수 있어요."
          : few ? "젊은 관객이 많은 공연은 차로 오는 관객이 적은 편이에요."
          : "차로 오는 관객은 보통 수준으로 보여요."}
        예상 관객 차 <b>약 ${ac.pred.toLocaleString()}대</b>${base ? `(10~20대 팬 중심 공연의 약 ${ratio.toFixed(1)}배)` : ""}
        <span class="muted small">(보통 ${ac.lo.toLocaleString()}~${ac.hi.toLocaleString()}대 · 서울시 생활인구로 추정한 관객 구성과 공원 주차장 입출차 기록 ${audCar.model.n}회 공연 분석)</span>`;
    }

    const minWalk = Math.min(...walk.map((w) => w.walkMin));
    const maxWalk = Math.max(...walk.map((w) => w.walkMin));
    const walkCapSum = walk.reduce((s, w) => s + (w.cap || 0), 0);

    const arrivalCgText = cg
      ? `${!isBig ? `<span class="muted small">(참고: KSPO DOME 저녁 공연 기준${hasBigSameDay ? " · 오늘 동시 공연 있음" : ""})</span> ` : ""}KSPO DOME 저녁 공연 날 ${cg.kspoEveningDays}일 중 <b>${cg.kspoDaysWithFull}일</b>은 일부 구역이 만차였어요.
         첫 만차는 보통 공연 시작 <b>약 ${cg.hoursBefore.med}시간 전</b>(${cg.hoursBefore.p25}~${cg.hoursBefore.p75}시간 전)${isBig ? `, 오늘이면 <b>${toHHMM(startMin - cg.hoursBefore.med * 60)} 무렵</b>` : ""}이에요.
         <span class="muted small">(구역 ${cg.zones}곳 중 보통 ${cg.fullZones.med}곳, 한국체육산업개발 주차장 혼잡도 기록 ${cg.period[0].slice(0, 7)}~${cg.period[1].slice(0, 7)})</span>`
      : `만차 예상 시각 <span class="tag-pending">자료 준비 중</span>`;

    $("options").innerHTML = `
      ${notices.map((n) => `<div class="notice">${n}</div>`).join("")}

      <div class="opt ${lv.key === "normal" ? "recommended" : ""}">
        <div class="opt-top">
          <div class="kind">선택 1 · 공원 안</div>
          ${lv.key === "normal" ? `<span class="reco-pill">오늘의 추천</span>` : ""}
        </div>
        <h3>${park[0].name}</h3>
        <div class="opt-metrics">
          <div class="metric-card">
            <div class="mk">${places.dome.name} 도보</div>
            <div class="mv">약 ${park[0].walkMin}분</div>
            <div class="ms">구역마다 다름</div>
          </div>
          <div class="metric-card">
            <div class="mk">예상 주차 요금</div>
            <div class="mv">${won(parkingFee(park[0], stay))}</div>
            <div class="ms">${park[0].fee}</div>
          </div>
          <div class="metric-card">
            <div class="mk">출차 50% 소요</div>
            <div class="mv">${isBig && ep ? `약 ${ep.t50.med}분` : "준비 중"}</div>
            <div class="ms">${isBig && ep ? `90% 약 ${ep.t90.med}분 · 과거 ${ep.shows}회` : "2025 데이터 예정"}</div>
          </div>
        </div>
        ${parkLiveBox}
        <dl>
          <dt>도착할 때</dt><dd>${arrivalCgText}</dd>
          <dt>귀가할 때</dt><dd>${peakText}</dd>
          ${carCrowdText ? `<dt>차로 오는 관객</dt><dd>${carCrowdText}</dd>` : ""}
        </dl>
      </div>

      <div class="opt">
        <div class="opt-top">
          <div class="kind">선택 2 · 걸어올 수 있는 곳</div>
        </div>
        <h3>공원 바깥쪽 주차장 ${walk.length}곳</h3>
        <div class="opt-metrics">
          <div class="metric-card">
            <div class="mk">${places.dome.name} 도보</div>
            <div class="mv">약 ${minWalk}~${maxWalk}분</div>
            <div class="ms">TMAP 보행 경로</div>
          </div>
          <div class="metric-card">
            <div class="mk">주차 면수 합계</div>
            <div class="mv">${walkCapSum.toLocaleString()}면</div>
            <div class="ms">${walk.length}곳 합산</div>
          </div>
          <div class="metric-card">
            <div class="mk">실시간 빈자리</div>
            <div class="mv">정보 없음</div>
            <div class="ms">현장 확인 필요</div>
          </div>
        </div>
        <dl>
          <dt>귀가할 때</dt><dd>공원 내부 출구 정체 영향을 덜 받는지 <span class="tag-pending">공연일 실측으로 확인 예정</span></dd>
        </dl>
        <div class="lots">
          <div class="table-scroll">
            <table>
              <tr><th>주차장</th><th>면수</th><th>도보</th><th>예상 요금</th></tr>
              ${walk.map((w) => `<tr><td><b>${w.name}</b></td><td>${w.cap}면</td><td>약 ${w.walkMin}분</td><td>${won(parkingFee(w, stay))}</td></tr>`).join("")}
            </table>
          </div>
        </div>
      </div>

      <div class="opt ${lv.key === "focus" ? "recommended" : ""}">
        <div class="opt-top">
          <div class="kind">선택 3 · 환승주차 (역 공영주차장 + 지하철)</div>
          ${lv.key === "focus" ? `<span class="reco-pill">오늘의 추천</span>` : ""}
        </div>
        <h3>출구 혼잡을 덜어 주는 분산 주차</h3>
        <div class="toggle tabs" role="tablist">
          <button type="button" data-tmode="go" class="${tMode === "go" ? "on" : ""}" role="tab">공연장 갈 때</button>
          <button type="button" data-tmode="out" class="${tMode === "out" ? "on" : ""}" role="tab">공연장에서 나올 때</button>
        </div>
        ${tMode === "go" ? transferGo(ev, startMin, park, stOf, liveOf, stay, transfer) : transferOutHTML(ev, startMin, endMin, park, stOf, transfer)}
      </div>`;
  }

  // 환승주차 · 공연장 갈 때: 관객이 2시간 넘게 나눠서 오므로 평소 시간으로 계산
  function transferGo(ev, startMin, park, stOf, liveOf, stay, transfer) {
    return `<p class="muted small" style="margin:0 0 8px">주차장에서 ${places.dome.name}까지 이동 시간이에요. 관객이 나눠서 도착하므로 평소 시간으로 계산했어요. 도보는 TMAP, 지하철은 ${SUBWAY.official ? "서울교통공사 표준 운행시간" : "가정값"} 기준이에요.</p>
      <div class="tlot-list">
      ${transfer.map((t) => {
        const st = t.station ? stOf(t.station) : null;
        const lv2 = liveOf(t.name);
        const tt = transferTotal(t, st);
        const steps = tt ? `
          <div class="route-steps">
            <span class="step-pill">역까지 ${tt.walk1}분</span>
            <span class="step-arrow">→</span>
            <span class="step-pill is-subway">지하철 ${tt.ride}분 (대기 ${tt.wait}분${tt.transfer ? `·환승 ${tt.transfer}분` : ""})</span>
            <span class="step-arrow">→</span>
            <span class="step-pill">공연장 ${tt.walk2}분</span>
            <span class="step-pill">요금 ${won(parkingFee(t, stay))}</span>
          </div>` : `<div class="route-steps"><span class="step-pill">예상 요금 ${won(parkingFee(t, stay))}</span></div>`;

        const driveCmp = (() => {
          const dv = driveOn(t.name, ev, toHHMM(startMin));
          if (!dv) return "";
          const parkWalk = park[0].walkMin;
          const totalDrive = dv.min + parkWalk;
          const gapTxt = tt ? (() => {
            const gap = tt.total - totalDrive;
            return gap > 0
              ? `도착만 보면 차로 공원까지 가는 게 약 ${gap}분 빨라요. 귀가 출차 비교는 <b>‘공연장에서 나올 때’</b> 탭을 확인해 보세요.`
              : `여기서 주차하고 지하철을 타는 쪽이 도착도 빨라요.`;
          })() : "";
          return `<div class="tlot-compare">여기서 차로 공원 주차장까지 계속 가면 <b>약 ${dv.min}분</b> + 도보 ${parkWalk}분 = 총 ${totalDrive}분 <span>(${dv.src})</span>${gapTxt ? `<br>${gapTxt}` : ""}</div>`;
        })();

        return `<div class="tlot${t.notRecommended ? " skip" : ""}">
          <div class="tlot-head">
            <div>
              <div class="tname">${t.name}</div>
              <div class="tlot-meta">${t.cap.toLocaleString()}면 · 운영 ${t.hours}</div>
            </div>
            ${lotFreeChip(lv2, t.cap)}
          </div>
          <div class="tlot-route-desc">${t.board ? t.board + "에서 " : ""}${t.route}</div>
          ${tt ? `<div class="ttotal"><span>총 이동</span> <b>약 ${tt.total}분</b>
              <span class="muted small">· 시작 30분 전 도착 기준 <b>${toHHMM(startMin - 30 - tt.total)}</b>까지 주차 권장</span></div>` : ""}
          ${steps}
          ${driveCmp}
          ${t.notRecommended ? `<div class="warnline">비추천: ${t.notRecommended}</div>` : ""}
        </div>`;
      }).join("")}
      </div>`;
  }

  // 환승주차 · 공연장에서 나올 때: 관객이 한꺼번에 역으로 몰리는 경우 ("공연장 나오기 N분" 제외 규칙 준수)
  function transferOutHTML(ev, startMin, endMin, park, stOf, transfer) {
    const ep = exitProf && ev.venue === "KSPO DOME" ? exitProf.summary : null;
    const parkWalk = Math.round(park[0].walkMin * CROWD.walkFactor);
    const parkOut = ep ? parkWalk + ep.t50.med : null;
    const rows = transfer.map((t) => {
      const st = t.station ? stOf(t.station) : null;
      const a = transferOut(t, st, ev, "med"), b = transferOut(t, st, ev, "high");
      if (!a) return `<div class="tlot"><div class="tname">${t.name}</div><div class="muted small">경로 정보 없음</div></div>`;
      const diffBadge = parkOut != null
        ? (parkOut > a.total
            ? `<span class="chip good">● 공원 주차장보다 약 ${parkOut - a.total}분 빨라요</span>`
            : `<span class="chip">공원 주차장(약 ${parkOut}분) 대비 +${a.total - parkOut}분</span>`)
        : "";
      return `<div class="tlot${t.notRecommended ? " skip" : ""}">
        <div class="tlot-head">
          <div>
            <div class="tname">${t.name}</div>
            <div class="tlot-meta">운영 ${t.hours} · ${st.name} 승차 → ${t.board ? t.board.replace(/역$/, "") + "역 하차" : ""}</div>
          </div>
          ${diffBadge}
        </div>
        <div class="ttotal">
          <span>출차까지 총</span> <b>약 ${a.total}분</b>
          ${b.total > a.total ? `<span class="muted small">(혼잡 심할 때 약 ${b.total}분)</span>` : ""}
          <span class="muted small">· ${toHHMM(endMin)} 종료 시 <b>${toHHMM(endMin + a.total)}</b> 무렵 출발</span>
        </div>
        <div class="route-steps">
          <span class="step-pill">역까지 ${a.walk2}분</span>
          <span class="step-arrow">→</span>
          <span class="step-pill is-crowd">개찰·승강장 줄 ${a.crowd}분</span>
          <span class="step-arrow">→</span>
          <span class="step-pill is-subway">지하철 ${a.ride}분 (대기 ${a.wait}분${a.transfer ? `·환승 ${a.transfer}분` : ""})</span>
          <span class="step-arrow">→</span>
          <span class="step-pill">주차장 ${a.walk1}분 · 출차 ${a.lotExit}분</span>
        </div>
        <div class="tlot-compare">
          ${a.riders > 1000 ? `공연 종료 직후 ${st.name}으로 약 <b>${a.riders.toLocaleString()}명</b>이 몰리는 것을 반영했어요.` : `${st.name}은 공연 날에도 승차 인원이 거의 늘지 않아 개찰 대기가 짧아요.`}
        </div>
        ${t.notRecommended ? `<div class="warnline">비추천: ${t.notRecommended}</div>` : ""}
      </div>`;
    }).join("");
    return `<p class="muted small" style="margin:0 0 8px">공연 종료 직후 역으로 관객이 몰리는 상황을 반영했어요. ${CROWD.source} 기준 KSPO DOME 공연 날 올림픽공원역 승차가 같은 요일 평소 대비 약 ${CROWD.riders.med.toLocaleString()}명 늘어요(9호선 71%, 5호선 29%). 공연 좌석 수에 비례해 계산했어요.</p>
      ${ep ? `<div class="notice info">비교 기준(공원 안 주차장): 차까지 도보 ${parkWalk}분 + 출차 대기(차량 절반이 빠져나가는 시간) 약 ${ep.t50.med}분 = <b>약 ${parkOut}분</b></div>` : ""}
      <div class="tlot-list">${rows}</div>
      <p class="muted small" style="margin:10px 0 0">개찰구 처리량(분당 ${CROWD.gatePerMin}명), 열차 간격, 인파 속 보행 속도(30% 감속)는 가정값이며, 11/21·22 공연일 현장 실측으로 보정할 예정이에요.</p>`;
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
      try {
        live = await loadLive();
        drawRoadMap($("map"), links, places, live.roads);
        if (m3) m3.update(live);
        $("roadNote").textContent = liveNote(live);
        render();
      } catch (_) {}
    }, 120000);
  } catch (e) {
    start3D(null);
    $("roadNote").textContent = "최근 수집값을 불러오지 못했어요(" + e.message + "). 도로는 회색으로 표시돼요.";
  }
})();
