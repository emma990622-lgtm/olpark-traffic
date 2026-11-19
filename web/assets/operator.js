// 운영자·기관 화면
(async function () {
  const [events, links, places, exits] = await Promise.all([
    loadJSON("events.json"), loadJSON("links.json"), loadPlaces(), loadJSON("exits_2024_07.json"),
  ]);
  const ref = kspoReference(exits);
  const exitProf = await loadJSON("exit_profile.json").catch(() => null);
  const cgSum = await loadJSON("congestion_summary.json").catch(() => null);   // 주차장 혼잡도 기록(구역별 만차)

  // 실시간 도로 자료 검증: 서울시 원본(TOPIS) 및 다른 출처(TMAP 실시간 교통)와 교차 비교
  Promise.all([loadJSON("road_source_check.json").catch(() => null), loadJSON("road_check.json").catch(() => null)]).then(([a, c]) => {
    const pct = (x) => Math.round(x * 100) + "%";
    const parts = [];
    if (a) {
      parts.push(`서울시 원본(TOPIS)과 비교(${a.checked}, ${a.n}개 구간): 등급 일치 <b>${pct(a.sameGrade)}</b>, 속도 차이 중앙값 ${a.medAbsDiff}km/h, 상관계수 <b>${a.corr}</b>`);
    }
    if (c && c.corridors) {
      parts.push(`긴 도로 이동시간을 TMAP과 비교(${c.checked}, ${c.corridors.n}개 도로, 600m 이상): 차이 중앙값 <b>${pct(c.corridors.medAbsDiff)}</b>, 30% 이내 ${pct(c.corridors.within30)}`);
    }
    if (c) {
      parts.push(`짧은 구간별 TMAP 비교(${c.checked}, ${c.n}개 구간): 등급 일치 ${pct(c.sameGrade)}, 한 단계 차이까지 ${pct(c.within1)}, 속도 차이 중앙값 ${c.medAbsDiff}km/h` +
        (c.long300 ? ` · 300m 초과 구간만 등급 일치 <b>${pct(c.long300.sameGrade)}</b>` : "") +
        (c.history && c.history.length > 1 ? ` (누적 검증 ${c.history.length}회)` : "") +
        " · 짧은 구간은 교차로 신호 대기 영향이 커 참고용");
    }
    if (parts.length) {
      document.getElementById("roadCheck").innerHTML = `
        <div class="verify-box">
          <div class="verify-title">실시간 도로 자료 교차검증 결과</div>
          <ol class="verify-list">${parts.map((p) => `<li>${p}</li>`).join("")}</ol>
        </div>`;
    }
  });

  const GATE_ROAD = { "남2문": "위례성대로", "북2문": "강동대로" };   // 현장 확인 필요
  const today = new Date().toISOString().slice(0, 10);
  const upcoming = events.filter((e) => e.date >= today && e.times.length);
  const byDate = groupByDate(upcoming);
  const $ = (id) => document.getElementById(id);
  let live = null;
  const LIVE_SLIDER_HINT = "슬라이더를 움직이거나 ▶ 버튼을 누르면 공연 2시간 전부터 종료 2시간 후까지 시간대별 변화를 볼 수 있어요.";

  [...byDate.keys()].forEach((d) => {
    const list = byDate.get(d);
    const seats = list.reduce((s, e) => s + (e.seats || 0), 0);
    const lv = levelOf(seats);
    const o = document.createElement("option");
    o.value = d;
    o.textContent = `${d} (${DOW[new Date(d + "T00:00:00").getDay()]}) · 혼잡 ${lv.label} · ${list.map((e) => e.venue).join(", ")}`;
    $("date").appendChild(o);
  });
  const firstBig = upcoming.find((e) => e.venue === "KSPO DOME");
  if (firstBig) $("date").value = firstBig.date;
  [120, 150, 180, 210].forEach((m) => {
    const o = document.createElement("option");
    o.value = m;
    o.textContent = m + "분" + (m === DEFAULT_SHOW_MIN ? " (기본)" : "");
    $("showMin").appendChild(o);
  });
  $("showMin").value = DEFAULT_SHOW_MIN;

  // 2024-07 비교 기준: 공원 큰 공연(KSPO·핸드볼·올림픽홀)이 없는 같은 시간대 평일 평균
  const ev24 = events.filter((e) => e.date.startsWith("2024-07"));
  const bigDates = new Set(ev24.filter((e) => ["KSPO DOME", "핸드볼경기장", "올림픽홀"].includes(e.venue)).map((e) => e.date));
  const quietWeekdays = Object.keys(exits.days).filter((d) => {
    const w = new Date(d + "T00:00:00").getDay();
    return w >= 1 && w <= 5 && !bigDates.has(d);
  });
  const nSlots = exits.days[quietWeekdays[0]].exits.length;
  const baseline = Array.from({ length: nSlots }, (_, i) =>
    quietWeekdays.reduce((s, d) => s + exits.days[d].exits[i], 0) / quietWeekdays.length);
  const slotStart = toMin(exits.slotStart);

  function render() {
    const d = $("date").value, list = byDate.get(d), showMin = +$("showMin").value;
    const seats = list.reduce((s, e) => s + (e.seats || 0), 0);
    const lv = levelOf(seats);
    const big = list.find((e) => e.venue === "KSPO DOME");
    const lastStart = Math.max(...list.flatMap((e) => e.times.map(toMin)));
    const lastEnd = lastStart + showMin;

    $("events").innerHTML = `<tr><th>공연장</th><th>공연명</th><th>시작 시각</th><th>예상 종료</th><th>좌석 규모(참고)</th></tr>` +
      list.map((e) => `<tr>
        <td class="nowrap"><span class="chip ${e.venue === "KSPO DOME" ? "accent" : ""}">${e.venue}</span></td>
        <td><b>${e.title}</b></td>
        <td class="nowrap">${e.times.join(", ")}</td>
        <td class="nowrap">${e.times.map((t) => toHHMM(toMin(t) + showMin)).join(", ")}</td>
        <td class="nowrap">${e.seats ? e.seats.toLocaleString() + "석" : "-"}</td>
      </tr>`).join("");

    const peakAt = big ? toHHMM(toMin(big.times[0]) + ref.lagMed) : "-";
    $("kpis").innerHTML = `
      <div class="kpi is-${lv.cls}">
        <div class="v"><span class="chip ${lv.cls}" style="font-size:16px;padding:5px 12px">${lv.sym} ${lv.label}</span></div>
        <div class="l">대응 수준 (좌석 합 약 ${seats.toLocaleString()}석 기준)</div>
      </div>
      <div class="kpi">
        <div class="v">${peakAt}</div>
        <div class="l">출차 최대 예상 시각 (2024-07 KSPO DOME ${ref.n}회: 시작 후 ${durText(ref.lagMin)}~${durText(ref.lagMax)}, 중앙값 기준)</div>
      </div>
      <div class="kpi">
        <div class="v">${big ? ref.peakMin + "~" + ref.peakMax + "대" : "-"}</div>
        <div class="l">15분 최대 출차 참고 범위</div>
      </div>
      <div class="kpi">
        <div class="v">${toHHMM(lastEnd)}</div>
        <div class="l">마지막 공연 예상 종료 (${showMin}분 가정)</div>
      </div>`;

    drawChart(big);
    drawBrief(d, list, lv, seats, big, peakAt, showMin);
    drawGates(big);
    renderRoadDay(d, list, showMin);
    setupTimeline(d, list, showMin);
  }

  // ---------- 3D 지도 시간 슬라이더: 공연 2시간 전 ~ 공연 끝나고 2시간 ----------
  const parkProf = await loadJSON("park_profile.json").catch(() => null);
  loadParkNight();
  const roadCache = {};
  const tl = { mode: "live", d: null, st: null, end: null, day: null, ref: null, refSt: null, timer: null };
  $("tInfo").textContent = LIVE_SLIDER_HINT;

  async function roadsByTime(folder) {
    if (roadCache[folder]) return roadCache[folder];
    const { roads, summary } = await loadCollectedFolder(folder);
    const m = new Map();
    m.park = new Map(summary.filter((r) => r["주차합계_parking_sum"]).map((r) => [toMin(r["수집시각"].slice(11, 16)), +r["주차합계_parking_sum"]]));
    roads.forEach((r) => {
      const t = toMin(r["수집시각"].slice(11, 16));
      if (!m.has(t)) m.set(t, {});
      m.get(t)[r["LINK_ID"]] = { spd: +r["속도_kmh"], idx: r["혼잡단계"] };
    });
    return (roadCache[folder] = m);
  }

  const nearest = (m, t, tol = 12) => {
    let best = null, bd = 1e9;
    for (const k of m.keys()) { const dd = Math.abs(k - t); if (dd < bd) { bd = dd; best = k; } }
    return best != null && bd <= tol ? m.get(best) : null;
  };

  async function setupTimeline(d, list, showMin) {
    const big = list.find((e) => e.venue === "KSPO DOME") || list.find((e) => e.venue === "핸드볼경기장") || list[0];
    const st = toMin(big.times[0]);
    const lastEnd = Math.max(...list.flatMap((e) => e.times.map(toMin))) + showMin;
    Object.assign(tl, { d, st, end: lastEnd, venue: big.venue, day: null, ref: null, refSt: null });
    const sl = $("tSlider");
    sl.min = st - 120; sl.max = lastEnd + 120;
    if (tl.mode !== "time" || +sl.value < +sl.min || +sl.value > +sl.max) sl.value = st;
    try {
      const folders = await listCollectedFolders();
      const dated = folders.filter((f) => /^\d{4}-\d{2}-\d{2}_/.test(f) && !/test|baseline/.test(f));
      const dayFs = dated.filter((f) => f.startsWith(d + "_"));
      if (dayFs.length) {
        const maps = await Promise.all(dayFs.map(roadsByTime));
        tl.day = new Map(maps.flatMap((m) => [...m.entries()]));
        tl.day.park = new Map(maps.flatMap((m) => [...m.park.entries()]));
      }
      const kspoDates = new Set(events.filter((e) => e.venue === "KSPO DOME").map((e) => e.date));
      const refDate = dated.filter((f) => !f.startsWith(d) && kspoDates.has(f.slice(0, 10)) && f.slice(0, 10) <= today).map((f) => f.slice(0, 10)).at(-1);
      if (refDate) {
        const re = events.find((e) => e.date === refDate && e.venue === "KSPO DOME");
        const maps = await Promise.all(dated.filter((f) => f.startsWith(refDate + "_")).map(roadsByTime));
        tl.ref = new Map(maps.flatMap((m) => [...m.entries()])); tl.refSt = toMin(re.times[0]); tl.refDate = refDate;
      }
    } catch (_) { /* 수집 기록을 못 불러와도 주차 예측은 보여 줌 */ }
    if (tl.mode === "time") showTime(+sl.value);
  }

  function phaseOf(t) {
    if (t < tl.st - 30) return "입장 시작";
    if (t < tl.st) return "입장 몰림";
    if (t < tl.end) return "공연 중";
    if (t < tl.end + 60) return "퇴장 몰림";
    return "퇴장 마무리";
  }

  function showTime(t) {
    tl.mode = "time"; $("tNow").classList.remove("on");
    const rel = t - tl.st;
    const sign = rel < 0 ? "−" : "+";
    $("tLabel").innerHTML = `${toHHMM(t)} <span class="muted small">(공연 시작 ${sign}${durText(Math.abs(rel)) || "0분"})</span><span class="phase">${phaseOf(t)}</span>`;
    let roads = null, src;
    if (tl.day && (roads = nearest(tl.day, t))) src = `도로: ${tl.d} 실측`;
    else if (tl.ref && (roads = nearest(tl.ref, tl.refSt + rel))) src = `도로: ${tl.refDate} KSPO DOME 공연의 같은 시점 실측(참고)`;
    else src = "도로: 이 시각 수집 기록이 없어 회색으로 보여요 (공연일 자동 수집 후 채워져요)";
    if (m3) m3.update({ roads: roads || {} });
    drawRoadMap($("map"), links, places, roads || {});
    let park = "";
    const realPark = tl.day && tl.day.park ? nearest(tl.day.park, t) : null;
    if (realPark != null) {
      const pa = parkActual(realPark);
      park += `<b>실측</b> 공원 주차 약 <b>${pa.est.toLocaleString()}대</b> (한국체육산업개발 실시간 값 ${realPark.toLocaleString()}대 − 출차 기록 없는 장기 주차 약 ${pa.ghost.toLocaleString()}대, ${tl.d} 수집)<br>`;
    }
    if (parkProf) {
      const i = parkProf.relMin.findIndex((x) => x >= rel);
      if (i >= 0) {
        const rng = parkProf.parkedMin ? ` <span>(공연에 따라 ${parkProf.parkedMin[i].toLocaleString()}~${parkProf.parkedMax[i].toLocaleString()}대)</span>` : "";
        park += `${realPark != null ? "참고: 과거 " : ""}공원 주차 약 <b>${parkProf.parked[i].toLocaleString()}대</b> / ${parkProf.capacity.toLocaleString()}면${rng} · 최근 15분 입차 ${parkProf.in15[i]}대 · 출차 ${parkProf.out15[i]}대
          <span>(2024년 7월 KSPO DOME 공연 ${parkProf.shows.length}회 중앙값${tl.venue === "KSPO DOME" ? "" : ", 이날은 KSPO DOME 공연이 아니라 참고만"})</span><br>`;
      }
    }
    $("tInfo").innerHTML = park + src;
  }

  $("tSlider").addEventListener("input", (e) => { stopPlay(); showTime(+e.target.value); });
  $("tNow").addEventListener("click", () => {
    stopPlay(); tl.mode = "live"; $("tNow").classList.add("on");
    $("tLabel").textContent = "지금 실시간";
    $("tInfo").textContent = LIVE_SLIDER_HINT;
    if (m3 && live) m3.update(live);
    drawRoadMap($("map"), links, places, live ? live.roads : null);
  });
  function stopPlay() { if (tl.timer) { clearInterval(tl.timer); tl.timer = null; $("tPlay").textContent = "▶"; } }
  $("tPlay").addEventListener("click", () => {
    if (tl.timer) return stopPlay();
    const sl = $("tSlider");
    if (tl.mode !== "time" || +sl.value >= +sl.max) sl.value = sl.min;
    $("tPlay").textContent = "❚❚";
    showTime(+sl.value);
    tl.timer = setInterval(() => {
      const v = +sl.value + 5;
      if (v > +sl.max) return stopPlay();
      sl.value = v; showTime(v);
    }, 700);
  });

  // 출차 곡선: 시작 시각이 가장 비슷한 2024-07 KSPO 공연일 vs 같은 시간대 평일 평균
  function drawChart(big) {
    const svg = $("chart");
    const waves = exits.kspoWaves;
    let refDay = null;
    if (big) {
      const s = toMin(big.times[0]);
      refDay = Object.keys(waves).sort((a, b) => Math.abs(toMin(waves[a].start) - s) - Math.abs(toMin(waves[b].start) - s))[0];
    }
    const series = refDay ? exits.days[refDay].exits : null;
    const W = 560, H = 260, L = 40, R = 12, T = 16, B = 30;
    const maxY = Math.max(...baseline, ...(series || [0])) * 1.12;
    const X = (i) => L + (i / (nSlots - 1)) * (W - L - R);
    const Y = (v) => H - B - (v / maxY) * (H - T - B);
    const path = (arr) => arr.map((v, i) => (i ? "L" : "M") + X(i).toFixed(1) + " " + Y(v).toFixed(1)).join("");
    const area = (arr) => `${path(arr)} L${X(arr.length - 1).toFixed(1)} ${(H - B).toFixed(1)} L${X(0).toFixed(1)} ${(H - B).toFixed(1)} Z`;
    let g = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" font-size="11">`;
    for (let v = 0; v <= maxY; v += 100) {
      g += `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)"/>
            <text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end" fill="var(--ink-2)">${v}</text>`;
    }
    for (let i = 0; i < nSlots; i += 8) {
      g += `<text x="${X(i)}" y="${H - 10}" text-anchor="middle" fill="var(--ink-2)">${toHHMM(slotStart + i * 15)}</text>`;
    }
    g += `<path d="${path(baseline)}" fill="none" stroke="var(--none)" stroke-width="2" stroke-dasharray="4 3"/>`;
    if (series) {
      g += `<path d="${area(series)}" fill="rgba(29, 78, 216, 0.08)"/>`;
      g += `<path d="${path(series)}" fill="none" stroke="var(--accent)" stroke-width="2.6"/>`;
      const si = (toMin(waves[refDay].start) - slotStart) / 15;
      g += `<line x1="${X(si)}" x2="${X(si)}" y1="${T}" y2="${H - B}" stroke="var(--accent)" stroke-dasharray="4 4"/>
            <text x="${X(si) + 5}" y="${T + 11}" fill="var(--accent)" font-weight="700">공연 시작</text>`;
    }
    g += `</svg>`;
    svg.outerHTML = g.replace("<svg ", '<svg id="chart" style="width:100%;height:auto" ');
    $("chartNote").innerHTML = series
      ? `<span style="color:var(--accent);font-weight:700">━</span> <b>${refDay} ${waves[refDay].title}</b> (시작 ${waves[refDay].start}, 15분 최대 ${waves[refDay].peak15}대, ${waves[refDay].peakTime})
         &nbsp;·&nbsp; <span style="color:var(--none);font-weight:700">┅</span> 같은 시간대 큰 공연 없는 평일 평균(${quietWeekdays.length}일).
         <br>2024년 자료는 출구 구분이 없고 일반 방문 차량이 섞여 있어 참고용이에요.`
      : "KSPO DOME 공연이 없는 날이라 참고 곡선이 없어요. 다른 공연장 곡선은 2025 데이터로 추가해요.";
  }

  // 출구별 대응: 2025 입출차 기록(KSPO DOME 공연)으로 출구별 비중과 빠지는 시간
  function drawGates(big) {
    if (!exitProf) { $("gateTable").innerHTML = "<tr><td>출차 분석 파일이 아직 없어요</td></tr>"; return; }
    const sm = exitProf.summary;
    const st = big ? toMin(big.times[0]) : null;
    const surge = st != null ? st + sm.surgeMin.med : null;
    const g = Object.entries(exitProf.gates);
    $("gateNote").innerHTML = big
      ? `${big.times[0]} 공연이면 <b>${toHHMM(surge)} 무렵</b>부터 출차가 집중되고, 공원 주차장 차의 절반은 약 <b>${sm.t50.med}분</b>, 90%는 약 <b>${sm.t90.med}분</b> 뒤(${toHHMM(surge + sm.t90.med)})에 빠져나가요.`
      : "이날은 KSPO DOME 공연이 없어요. 아래는 KSPO DOME 공연일 기준 참고값이에요.";
    $("gateTable").innerHTML = `<tr><th>출구</th><th>관객 차량 비중</th><th>절반 출차</th><th>90% 출차</th><th>연결 도로(현장 확인 필요)</th><th>요원 배치 참고 시간대</th></tr>` +
      g.map(([name, v], i) => {
        const pctVal = v.pct != null ? v.pct : Math.round(v.share * 100);
        const range = v.p25 != null ? `<span class="muted small">보통 ${Math.round(v.p25 * 100)}~${Math.round(v.p75 * 100)}%</span>` : "";
        const members = v.members ? `<br><span class="muted small">${v.members.map((m) => m.gate).join("·")} (일부 공연에서만 쓰임)</span>` : "";
        const t50 = v.t50 != null ? `약 ${v.t50}분` : "—";
        const t90 = v.t90 != null ? `약 ${v.t90}분` : "—";
        const when = v.t90 == null ? "-" : (surge != null ? `${toHHMM(surge - 15)} ~ ${toHHMM(surge + v.t90)}` : `몰리기 15분 전 ~ ${v.t90}분 뒤`);
        return `<tr>
          <td class="nowrap">${name}${members}</td>
          <td><div class="share-cell"><span class="share-bar"><i style="width:${pctVal}%"></i></span><b>${pctVal}%</b></div>${range}</td>
          <td class="nowrap">${t50}</td>
          <td class="nowrap">${t90}</td>
          <td class="nowrap">${GATE_ROAD[name] || "-"}</td>
          <td><b>${when}</b>${i === 0 ? ` <span class="chip warn">가장 많음 · 우선 배치</span>` : ""}</td>
        </tr>`;
      }).join("");
    const gm = exitProf.gateMeta || {};
    const gShows = gm.shows || Object.values(exitProf.gates)[0].shows;
    $("gateSrc").textContent = `2025년 입출차 기록(약 88% 받은 시점) 중 출구 기록이 있는 KSPO DOME 공연 ${gShows}회 기준. ` +
      `비중은 공연마다 출구별 비중(합 100%)을 구해 평균한 값이고, 그 출구가 안 쓰인 공연은 0%로 넣어 합이 100%가 돼요. ` +
      `절반 넘는 공연에서 쓰인 출구만 따로 보이고 나머지는 '그 밖의 출구'로 묶었어요. "보통"은 공연 4개 중 가운데 2개가 들어가는 범위예요. ` +
      `시간은 출차가 몰리기 시작한 때부터 잰 값이에요(2024년 7월 포함 전체 ${sm.shows}회). 다운로드 완료 후 다시 계산해요.`;
  }

  function drawBrief(d, list, lv, seats, big, peakAt, showMin) {
    let roadsTxt = "위례성대로, 강동대로, 양재대로, 올림픽로 (공연일 실측 후 속도가 많이 떨어지는 순서로 표시)";
    if (live && live.roads && Object.keys(live.roads).length) {
      const slow = links.map((l) => ({ l, r: live.roads[l.id] })).filter((x) => x.r)
        .sort((a, b) => a.r.spd - b.r.spd).slice(0, 5)
        .map((x) => `${x.l.road}(${x.l.from}→${x.l.to}) ${x.r.spd}km/h`);
      roadsTxt = slow.join(", ") + ` <span class="muted small">— ${live.roadTime} 수집값 기준 느린 구간</span>`;
    }
    const dt = new Date(d + "T00:00:00");
    $("brief").innerHTML = `
      <h3>올림픽공원 공연 혼잡 대응 요약 · ${d}(${DOW[dt.getDay()]})</h3>
      <div class="muted small">작성 ${new Date().toLocaleString("ko-KR")} · 올팍 공연 혼잡 대응 웹앱</div>
      <table>
        <tr><th>당일 공연</th><td>${list.map((e) => `<b>${e.venue}</b> ${e.times.join("·")} — ${e.title}`).join("<br>")}</td></tr>
        <tr><th>대응 수준</th><td><b>${lv.sym} ${lv.label}</b> (공원 공연 좌석 합 약 ${seats.toLocaleString()}석)</td></tr>
        <tr><th>출차 최대 예상</th><td>${big ? `<b>${peakAt} 무렵</b>, 15분에 ${ref.peakMin}~${ref.peakMax}대 (2024년 7월 KSPO DOME 공연 ${ref.n}회 기준 참고값)` : "참고 기록 없음"}</td></tr>
        <tr><th>주차장 만차</th><td>${cgSum ? `KSPO DOME 저녁 공연일 ${cgSum.kspoEveningDays}일 중 ${cgSum.kspoDaysWithFull}일 일부 구역 만차 기록. 첫 만차 보통 공연 ${cgSum.hoursBefore.med}시간 전${big ? `(${toHHMM(toMin(big.times[0]) - cgSum.hoursBefore.med * 60)} 무렵)` : ""}, 자주 차는 구역 ${Object.keys(cgSum.zoneFullDays).slice(0, 3).join("·")} → 그 전에 입구 안내 요원 배치 및 인근·환승 분산 주차 안내` : "-"}</td></tr>
        <tr><th>집중 관리 출구</th><td>${exitProf ? Object.entries(exitProf.gates).map(([n, v]) => `<b>${n}</b> ${v.pct != null ? v.pct : Math.round(v.share * 100)}%`).join(" · ") + ` (관객 차량 비중 합 100%, 2025 기록 공연 ${(exitProf.gateMeta || {}).shows || "-"}회 평균)` : "2025 입출차 데이터 반영 후 제시"}</td></tr>
        <tr><th>출차 소요</th><td>${exitProf ? `몰리기 시작해서 절반 약 <b>${exitProf.summary.t50.med}분</b>, 90% 약 <b>${exitProf.summary.t90.med}분</b> (KSPO DOME 공연 ${exitProf.summary.shows}회)` : "-"}</td></tr>
        <tr><th>영향 도로</th><td>${roadsTxt}</td></tr>
        <tr><th>관객 분산 안내</th><td>공원 주차장 혼잡 시 천호역 공영주차장(1,431면) + 5호선 올림픽공원역 환승 분산 주차 안내. 공원 차량 출입 22시까지(심야 행사 시 조정)</td></tr>
        <tr><th>기관별 협조 참고</th><td><b>한국체육산업개발</b>: 출구별 요원 배치 · <b>송파구청</b>: 주변 공영주차장 안내 · <b>관할 경찰서</b>: 출차 집중 시간대 교차로 관리 · <b>서울시</b>: 도로전광판(VMS) 안내</td></tr>
      </table>
      <div class="muted small">공연 길이 ${showMin}분 가정. 위 수치는 공공데이터 분석 기반 참고 근거이며, 실제 현장 배치와 교통 통제는 각 기관이 판단·결정합니다.</div>`;
  }

  // ---------- 공연 전후 도로 상황 ----------
  const hm = (ts) => { const t = ts.slice(11, 16); return toMin(t); };
  const median = (a) => { const b = a.slice().sort((x, y) => x - y); const n = b.length; return n ? (n % 2 ? b[(n - 1) / 2] : (b[n / 2 - 1] + b[n / 2]) / 2) : NaN; };

  async function loadDayFolders(fs) {
    const parts = await Promise.all(fs.map(loadCollectedFolder));
    const by = (k) => (a, b) => (a[k] < b[k] ? -1 : a[k] > b[k] ? 1 : 0);
    return { folder: fs.join(", "), summary: parts.flatMap((p) => p.summary).sort(by("수집시각")), roads: parts.flatMap((p) => p.roads).sort(by("수집시각")) };
  }

  async function renderRoadDay(d, list, showMin) {
    const note = $("roadDayNote");
    let folders;
    try { folders = await listCollectedFolders(); } catch (e) { note.textContent = "수집 기록을 불러오지 못했어요(" + e.message + ")."; return; }
    const dayF = folders.filter((f) => f.startsWith(d + "_") && !/test/.test(f));
    const isExample = !dayF.length;
    const target = isExample ? folders.filter((f) => /^\d{4}-\d{2}-\d{2}_/.test(f)).at(-1) : dayF.join(", ");
    if (!target) { note.textContent = "아직 수집된 기록이 없어요."; return; }
    const baseF = folders.filter((f) => f.includes("_baseline") && !f.startsWith(d)).at(-1);
    const [T, B] = await Promise.all([isExample ? loadCollectedFolder(target) : loadDayFolders(dayF), baseF ? loadCollectedFolder(baseF) : null]);
    note.innerHTML = isExample
      ? `이 날짜는 공연 당일 자동 수집(공연 약 2시간 전부터 약 6시간) 뒤에 채워져요. 아래는 가장 최근 수집 기록 <b>${target}</b> 예시예요.`
      : `수집 기록: <b>${target}</b>${B ? ` · 같은 시간대 공연 없는 날 비교: <b>${baseF}</b>` : " · 공연 없는 날 비교 기록은 11/20, 11/26 수집 후 표시"}`;

    const starts = isExample ? [] : list.flatMap((e) => e.times.map(toMin));
    const st = starts.length ? Math.min(...starts) : null;
    drawRoadChart(T, B, st, showMin);
    drawHeat(T, st, showMin);
    drawSlowTop(T, st);
  }

  function drawRoadChart(T, B, st, showMin) {
    const pts = T.summary.map((r) => ({ t: hm(r["수집시각"]), v: +r["지역평균속도_kmh"], bad: (+r["정체구간수"] || 0) + (+r["서행구간수"] || 0) })).filter((p) => p.v);
    const bpts = B ? B.summary.map((r) => ({ t: hm(r["수집시각"]), v: +r["지역평균속도_kmh"] })).filter((p) => p.v) : [];
    if (!pts.length) { $("roadChart").outerHTML = '<svg id="roadChart"></svg>'; return; }
    const ts = [...pts, ...bpts].map((p) => p.t).concat(st != null ? [st, st + showMin, st + ref.lagMed] : []);
    const t0 = Math.floor(Math.min(...ts) / 30) * 30, t1 = Math.ceil(Math.max(...ts) / 30) * 30;
    const W = 1000, H = 280, L = 44, R = 44, Tp = 18, Bt = 30;
    const vmax = Math.ceil(Math.max(...pts.map((p) => p.v), ...bpts.map((p) => p.v), 40) / 10) * 10;
    const cmax = 58;
    const X = (t) => L + ((t - t0) / Math.max(30, t1 - t0)) * (W - L - R);
    const Y = (v) => H - Bt - (v / vmax) * (H - Tp - Bt);
    const Yc = (c) => H - Bt - (c / cmax) * (H - Tp - Bt);
    const line = (arr) => arr.map((p, i) => (i ? "L" : "M") + X(p.t).toFixed(1) + " " + Y(p.v).toFixed(1)).join("");
    let g = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" font-size="11">`;
    for (let v = 0; v <= vmax; v += 10) g += `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end" fill="var(--ink-2)">${v}</text>`;
    for (let c = 0; c <= cmax; c += 20) g += `<text x="${W - R + 6}" y="${Yc(c) + 4}" fill="var(--bad)" opacity="0.8">${c}</text>`;
    for (let t = t0; t <= t1; t += 30) g += `<text x="${X(t)}" y="${H - 10}" text-anchor="middle" fill="var(--ink-2)">${toHHMM(t)}</text>`;
    const bw = Math.max(3, Math.min(18, (W - L - R) / Math.max(1, (t1 - t0) / 5) * 0.6));
    pts.forEach((p) => { g += `<rect x="${X(p.t) - bw / 2}" y="${Yc(p.bad)}" width="${bw}" height="${H - Bt - Yc(p.bad)}" rx="2" fill="var(--bad)" opacity="0.18"/>`; });
    if (bpts.length) g += `<path d="${line(bpts)}" fill="none" stroke="var(--none)" stroke-width="2" stroke-dasharray="5 4"/>`;
    g += `<path d="${line(pts)}" fill="none" stroke="var(--accent)" stroke-width="2.6"/>`;
    if (pts.length <= 4) {
      pts.forEach((p) => { g += `<circle cx="${X(p.t).toFixed(1)}" cy="${Y(p.v).toFixed(1)}" r="3.5" fill="var(--accent)"/>`; });
    }
    if (st != null) {
      [[st, "공연 시작"], [st + showMin, "예상 종료"], [st + ref.lagMed, "출차 최대 예상"]].forEach(([t, lab], i) => {
        g += `<line x1="${X(t)}" x2="${X(t)}" y1="${Tp}" y2="${H - Bt}" stroke="${i === 2 ? "var(--bad)" : "var(--ink-2)"}" stroke-dasharray="4 4"/>
              <text x="${X(t) + 4}" y="${Tp + 10 + i * 13}" fill="${i === 2 ? "var(--bad)" : "var(--ink-2)"}" font-weight="600">${lab} ${toHHMM(t)}</text>`;
      });
    }
    g += `<text x="${L}" y="${Tp - 5}" fill="var(--ink-2)">km/h</text><text x="${W - R + 6}" y="${Tp - 5}" fill="var(--bad)" opacity="0.85">구간 수</text></svg>`;
    $("roadChart").outerHTML = g.replace("<svg ", '<svg id="roadChart" style="width:100%;height:auto;margin-top:10px" ');
    $("roadChartLegend").innerHTML = `<span><i style="background:var(--accent)"></i>올림픽공원 주변 평균 속도</span>
      ${bpts.length ? '<span><i style="background:var(--none)"></i>같은 시간대 공연 없는 날 평균 속도</span>' : ""}
      <span><i style="background:var(--bad);opacity:.35;height:10px"></i>서행+정체 구간 수(58구간 중, 오른쪽 축)</span>`;
  }

  function drawHeat(T, st, showMin) {
    if (!T.roads.length) { $("heat").innerHTML = ""; return; }
    const times = [...new Set(T.roads.map((r) => r["수집시각"].slice(0, 16)))].sort();
    const byRoad = new Map();
    T.roads.forEach((r) => {
      const k = r["도로명"]; const t = r["수집시각"].slice(0, 16);
      if (!byRoad.has(k)) byRoad.set(k, new Map());
      const m = byRoad.get(k); if (!m.has(t)) m.set(t, []); m.get(t).push(r["혼잡단계"]);
    });
    const score = (arr) => arr.reduce((s, x) => s + (x === "정체" ? 2 : x === "서행" ? 1 : 0), 0) / arr.length;
    const color = (sc) => sc == null ? "#eef0f3" : sc < 0.4 ? "var(--good)" : sc < 1.0 ? "var(--warn)" : "var(--bad)";
    const gradeLabel = (sc) => sc == null ? "수집 없음" : sc < 0.4 ? "대부분 원활" : sc < 1.0 ? "서행 섞임" : "정체 많음";
    const rows = [...byRoad.entries()].map(([k, m]) => ({ k, cells: times.map((t) => (m.has(t) ? score(m.get(t)) : null)) }))
      .sort((a, b) => Math.max(...b.cells.map((c) => c ?? 0)) - Math.max(...a.cells.map((c) => c ?? 0)));
    const mark = (t) => st != null && [st, st + showMin, st + ref.lagMed].some((m) => Math.abs(hm(t + ":00") - m) < 3);
    let h = `<table class="heat"><tr><th></th>${times.map((t, i) => `<td class="tick">${i % 6 === 0 ? t.slice(11) : ""}</td>`).join("")}</tr>`;
    rows.forEach((r) => {
      h += `<tr><th>${r.k}</th>${r.cells.map((c, i) => `<td title="${r.k} ${times[i].slice(11)} · ${gradeLabel(c)}" aria-label="${r.k} ${times[i].slice(11)} ${gradeLabel(c)}" style="background:${color(c)};${mark(times[i]) ? "outline:2px solid var(--ink)" : ""}"></td>`).join("")}</tr>`;
    });
    h += `</table><div class="legend"><span><i style="background:var(--good)"></i>● 대부분 원활</span><span><i style="background:var(--warn)"></i>▲ 서행 섞임</span><span><i style="background:var(--bad)"></i>■ 정체 많음</span>${st != null ? "<span>▣ 검은 테두리: 공연 시작·예상 종료·출차 최대 예상</span>" : ""}</div>`;
    $("heat").innerHTML = h;
  }

  function drawSlowTop(T, st) {
    const byLink = new Map();
    T.roads.forEach((r) => { const k = r["LINK_ID"]; if (!byLink.has(k)) byLink.set(k, { r, pts: [] }); byLink.get(k).pts.push({ t: hm(r["수집시각"]), v: +r["속도_kmh"] }); });
    const res = [...byLink.values()].map(({ r, pts }) => {
      const before = st != null ? pts.filter((p) => p.t < st).map((p) => p.v) : pts.map((p) => p.v);
      const after = st != null ? pts.filter((p) => p.t >= st + 60) : pts;
      if (!before.length || !after.length) return null;
      const base = median(before); const worst = after.reduce((a, b) => (b.v < a.v ? b : a));
      return { name: `${r["도로명"]} ${r["시작지점"]}→${r["끝지점"]}`, base, worst: worst.v, at: toHHMM(worst.t), drop: base ? (base - worst.v) / base : 0 };
    }).filter(Boolean).sort((a, b) => b.drop - a.drop).slice(0, 5);

    if (!res.length) {
      $("slowTop").innerHTML = `<tr><td class="muted">비교할 구간 기록이 아직 충분하지 않아요.</td></tr>`;
      return;
    }
    $("slowTop").innerHTML = `<tr><th>도로 구간</th><th>${st != null ? "공연 전 보통 속도" : "보통 속도(중앙값)"}</th><th>가장 느렸을 때</th><th>속도 감소율</th></tr>` +
      res.map((x) => {
        const dropPct = Math.round(x.drop * 100);
        const cls = dropPct >= 35 ? "bad" : dropPct >= 15 ? "warn" : "";
        return `<tr>
          <td><b>${x.name}</b></td>
          <td class="nowrap">${x.base.toFixed(0)}km/h</td>
          <td class="nowrap">${x.worst.toFixed(0)}km/h <span class="muted small">(${x.at})</span></td>
          <td class="nowrap">${dropPct > 0 ? `<span class="chip ${cls}">−${dropPct}%</span>` : `0%`}</td>
        </tr>`;
      }).join("");
  }

  $("date").addEventListener("change", render);
  $("showMin").addEventListener("change", render);
  $("legend").innerHTML = legendHTML();
  drawRoadMap($("map"), links, places, null);
  let m3 = null;
  const start3D = async (lv) => {
    try {
      m3 = await initMap3D($("map3d"), { links, places, live: lv });
      if (!m3) throw new Error("3D 미지원");
      $("legend3d").innerHTML = legend3DHTML(m3.buildingSrc);
    } catch (e) {
      $("map3d").classList.add("failed"); $("flat").open = true;
      $("legend3d").innerHTML = `<p class="muted small">3D 지도를 열 수 없어 평면 지도로 보여 드려요 (${e.message || e}).</p>`;
    }
  };
  render();
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
        if (tl.mode === "live") { drawRoadMap($("map"), links, places, live.roads); if (m3) m3.update(live); }
        $("roadNote").textContent = liveNote(live);
      } catch (_) {}
    }, 120000);
  } catch (e) {
    start3D(null);
    $("roadNote").textContent = "최근 수집값을 불러오지 못했어요(" + e.message + ").";
  }
})();
