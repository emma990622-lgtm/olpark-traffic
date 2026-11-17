// 운영자·기관 화면
(async function () {
  const [events, links, places, exits] = await Promise.all([
    loadJSON("events.json"), loadJSON("links.json"), loadPlaces(), loadJSON("exits_2024_07.json"),
  ]);
  const ref = kspoReference(exits);
  const today = new Date().toISOString().slice(0, 10);
  const upcoming = events.filter((e) => e.date >= today && e.times.length);
  const byDate = groupByDate(upcoming);
  const $ = (id) => document.getElementById(id);
  let live = null;

  [...byDate.keys()].forEach((d) => {
    const list = byDate.get(d);
    const seats = list.reduce((s, e) => s + (e.seats || 0), 0);
    const o = document.createElement("option");
    o.value = d;
    o.textContent = `${d} (${DOW[new Date(d + "T00:00:00").getDay()]}) · ${levelOf(seats).label} · ${list.map((e) => e.venue).join(", ")}`;
    $("date").appendChild(o);
  });
  const firstBig = upcoming.find((e) => e.venue === "KSPO DOME");
  if (firstBig) $("date").value = firstBig.date;
  [120, 150, 180, 210].forEach((m) => {
    const o = document.createElement("option"); o.value = m; o.textContent = m + "분" + (m === DEFAULT_SHOW_MIN ? " (기본)" : "");
    $("showMin").appendChild(o);
  });
  $("showMin").value = DEFAULT_SHOW_MIN;

  // 2024-07 비교 기준: 공원 큰 공연(KSPO·핸드볼·올림픽홀)이 없는 평일의 평균
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

    $("events").innerHTML = `<tr><th>공연장</th><th>공연</th><th>시작</th><th>예상 종료</th><th>좌석(참고)</th></tr>` +
      list.map((e) => `<tr><td>${e.venue}</td><td>${e.title}</td><td>${e.times.join(", ")}</td>
        <td>${e.times.map((t) => toHHMM(toMin(t) + showMin)).join(", ")}</td>
        <td>${e.seats ? e.seats.toLocaleString() : "-"}</td></tr>`).join("");

    const peakAt = big ? toHHMM(toMin(big.times[0]) + ref.lagMed) : "-";
    $("kpis").innerHTML = `
      <div class="kpi"><div class="v"><span class="chip ${lv.cls}" style="font-size:18px">${lv.label}</span></div><div class="l">대응 수준 (좌석 합 ${seats.toLocaleString()}석 기준)</div></div>
      <div class="kpi"><div class="v">${peakAt}</div><div class="l">출차 최대 예상 시각 (2024-07 KSPO DOME ${ref.n}회: 시작 후 ${durText(ref.lagMin)}~${durText(ref.lagMax)}, 중앙값 기준)</div></div>
      <div class="kpi"><div class="v">${big ? ref.peakMin + "~" + ref.peakMax : "-"}</div><div class="l">15분 최대 출차 참고 범위(대)</div></div>
      <div class="kpi"><div class="v">${toHHMM(lastEnd)}</div><div class="l">마지막 공연 예상 종료</div></div>`;

    drawChart(big);
    drawBrief(d, list, lv, seats, big, peakAt, showMin);
  }

  // 출차 곡선: 시작 시각이 가장 비슷한 2024-07 KSPO 공연일 vs 공연 없는 평일 평균
  function drawChart(big) {
    const svg = $("chart");
    const waves = exits.kspoWaves;
    let refDay = null;
    if (big) {
      const s = toMin(big.times[0]);
      refDay = Object.keys(waves).sort((a, b) => Math.abs(toMin(waves[a].start) - s) - Math.abs(toMin(waves[b].start) - s))[0];
    }
    const series = refDay ? exits.days[refDay].exits : null;
    const W = 560, H = 260, L = 40, R = 12, T = 14, B = 30;
    const maxY = Math.max(...baseline, ...(series || [0])) * 1.1;
    const X = (i) => L + (i / (nSlots - 1)) * (W - L - R);
    const Y = (v) => H - B - (v / maxY) * (H - T - B);
    const path = (arr) => arr.map((v, i) => (i ? "L" : "M") + X(i).toFixed(1) + " " + Y(v).toFixed(1)).join("");
    let g = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" font-size="11">`;
    for (let v = 0; v <= maxY; v += 100) g += `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end" fill="var(--ink-2)">${v}</text>`;
    for (let i = 0; i < nSlots; i += 8) g += `<text x="${X(i)}" y="${H - 10}" text-anchor="middle" fill="var(--ink-2)">${toHHMM(slotStart + i * 15)}</text>`;
    g += `<path d="${path(baseline)}" fill="none" stroke="var(--none)" stroke-width="2"/>`;
    if (series) {
      g += `<path d="${path(series)}" fill="none" stroke="var(--accent)" stroke-width="2.5"/>`;
      const si = (toMin(waves[refDay].start) - slotStart) / 15;
      g += `<line x1="${X(si)}" x2="${X(si)}" y1="${T}" y2="${H - B}" stroke="var(--accent)" stroke-dasharray="4 4"/>
            <text x="${X(si) + 4}" y="${T + 10}" fill="var(--accent)">공연 시작</text>`;
    }
    g += `</svg>`;
    svg.outerHTML = g.replace("<svg ", '<svg id="chart" style="width:100%;height:auto" ');
    $("chartNote").innerHTML = series
      ? `<span style="color:var(--accent)">━</span> ${refDay} ${waves[refDay].title} (시작 ${waves[refDay].start}, 15분 최대 ${waves[refDay].peak15}대, ${waves[refDay].peakTime})
         &nbsp; <span style="color:var(--none)">━</span> 공원 큰 공연이 없는 평일 평균(${quietWeekdays.length}일).
         2024년 자료는 출구 구분이 없고 공원 방문 차량이 섞여 있어 참고용이에요.`
      : "KSPO DOME 공연이 없는 날이라 참고 곡선이 없어요. 다른 공연장 곡선은 2025 데이터로 추가해요.";
  }

  function drawBrief(d, list, lv, seats, big, peakAt, showMin) {
    // 영향 도로: 수집값이 있으면 지금 느린 순, 없으면 공원 접근 도로 목록
    let roadsTxt = "위례성대로, 강동대로, 양재대로, 올림픽로 (공연일 실측 후 속도가 많이 떨어지는 순서로 바뀜)";
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
        <tr><th>공연</th><td>${list.map((e) => `${e.venue} ${e.times.join("·")} ${e.title}`).join("<br>")}</td></tr>
        <tr><th>대응 수준</th><td>${lv.label} (공원 공연 좌석 합 약 ${seats.toLocaleString()}석)</td></tr>
        <tr><th>출차 최대 예상</th><td>${big ? `${peakAt} 무렵, 15분에 ${ref.peakMin}~${ref.peakMax}대 (2024년 7월 KSPO DOME 공연 ${ref.n}회 기준 참고값)` : "참고 기록 없음"}</td></tr>
        <tr><th>집중 관리 출구</th><td>2025 입출차 데이터 반영 후 제시 (동2문·남2문·북2문)</td></tr>
        <tr><th>영향 도로</th><td>${roadsTxt}</td></tr>
        <tr><th>관객 안내</th><td>공원 주차장 혼잡 시 천호역 공영주차장(1,431면) + 5호선 올림픽공원역 환승 안내. 공원 차량 출입 22시까지(심야 행사 시 조정)</td></tr>
        <tr><th>기관별 확인 요청</th><td>한국체육산업개발: 출구별 요원 배치 · 송파구청: 주변 공영주차장 안내 · 관할 경찰서: 출차 집중 시간대 교차로 관리 · 서울시: 도로전광판 안내</td></tr>
      </table>
      <div class="muted small">공연 길이 ${showMin}분 가정. 예측값은 참고용이며, 배치와 통제는 각 기관이 결정합니다.</div>`;
  }

  $("date").addEventListener("change", render);
  $("showMin").addEventListener("change", render);
  $("legend").innerHTML = legendHTML();
  drawRoadMap($("map"), links, places, null);
  render();
  try {
    live = await loadLive();
    if (live) {
      drawRoadMap($("map"), links, places, live.roads);
      $("roadNote").textContent = liveNote(live);
      render();
    }
    // 실시간 연결이면 2분마다 새로 고침
    if (live && live.source === "live") setInterval(async () => {
      try { live = await loadLive(); drawRoadMap($("map"), links, places, live.roads); $("roadNote").textContent = liveNote(live); render(); } catch (_) {}
    }, 120000);
  } catch (e) {
    $("roadNote").textContent = "최근 수집값을 불러오지 못했어요(" + e.message + ").";
  }
})();
