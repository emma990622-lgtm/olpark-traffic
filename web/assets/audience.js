// 관객 화면
(async function () {
  const [events, links, places, exits] = await Promise.all([
    loadJSON("events.json"), loadJSON("links.json"), loadPlaces(), loadJSON("exits_2024_07.json"),
  ]);
  const ref = kspoReference(exits);
  const today = new Date().toISOString().slice(0, 10);
  const upcoming = events.filter((e) => e.date >= today && e.times.length);
  const byDate = groupByDate(upcoming);
  let live = null;

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
    $("walkSrc").textContent = places.walkSource;
    renderTransit();
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
    const peakText = isBig
      ? `공연 시작 약 ${durText(ref.lagMed)} 뒤(${toHHMM(startMin + ref.lagMed)} 무렵) 출차가 가장 몰려요. 15분에 ${ref.peakMin}~${ref.peakMax}대`
      : "이 공연장의 과거 기록은 2025 데이터로 채울 예정이에요";

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

    const parkLive = live && live.summary ? `${live.summary["주차합계_parking_sum"]} (${String(live.summary["수집시각"]).slice(5, 16)} 기준, 주차 대수인지 빈자리인지 확인 중)` : "공연일에 5분마다 수집";

    $("options").innerHTML = `
      ${notices.map((n) => `<div class="notice">${n}</div>`).join("")}
      <div class="opt ${lv.key === "normal" ? "recommended" : ""}">
        <div class="kind">공원 안</div>
        <h3>${park[0].name}</h3>
        <dl>
          <dt>공연장까지</dt><dd>도보 약 ${park[0].walkMin}분 (구역마다 다름)</dd>
          <dt>예상 요금</dt><dd>${won(parkingFee(park[0], stay))} <span class="muted small">(${park[0].fee})</span></dd>
          <dt>도착할 때</dt><dd>만차 예상 시각 <span class="tag-pending">2025 데이터 반영 예정</span></dd>
          <dt>귀가할 때</dt><dd>${peakText}</dd>
          <dt>지금 주차</dt><dd>${parkLive}</dd>
        </dl>
      </div>
      <div class="opt">
        <div class="kind">걸어올 수 있는 곳</div>
        <h3>공원 바깥쪽 주차장 ${walk.length}곳</h3>
        <dl>
          <dt>공연장까지</dt><dd>도보 약 ${Math.min(...walk.map((w) => w.walkMin))}~${Math.max(...walk.map((w) => w.walkMin))}분</dd>
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
        <dl>
          <dt>귀가할 때</dt><dd>공원 출구 대기 없음. 대신 공연 직후 역이 붐벼요</dd>
          <dt>지하철 시간</dt><dd>정거장 수만 확인됨 <span class="tag-pending">역 간 소요시간 자료 확보 중</span></dd>
        </dl>
        <div class="lots"><table>
          <tr><th>주차장</th><th>경로</th><th>내려서 도보</th><th>예상 요금</th><th>빈자리</th></tr>
          ${transfer.map((t) => {
            const st = t.station ? stOf(t.station) : null;
            const lv2 = liveOf(t.name);
            const free = lv2 && lv2.now != null ? `${Math.max(0, lv2.cap - lv2.now)}면 <span class="muted small">(${String(lv2.time).slice(11, 16)})</span>` : (live && live.source === "live" ? "정보 없음" : "공연일에 수집");
            return `<tr><td>${t.name}<div class="muted small">${t.cap}면 · ${t.hours}</div></td>
                    <td>${t.route}</td><td>${st ? st.walkMin + "분" : "-"}</td>
                    <td>${won(parkingFee(t, stay))}</td><td>${free}</td></tr>`;
          }).join("")}
        </table></div>
      </div>`;
  }

  function renderTransit() {
    $("stations").innerHTML = `<tr><th>역</th><th>노선</th><th>KSPO DOME까지 도보(추정)</th></tr>` +
      places.stations.slice().sort((a, b) => a.walkMin - b.walkMin)
        .map((s) => `<tr><td>${s.name}</td><td>${s.line}</td><td>약 ${s.walkMin}분</td></tr>`).join("");
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
  drawRoadMap($("map"), links, places, null);
  fillEvents();
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
    $("roadNote").textContent = "최근 수집값을 불러오지 못했어요(" + e.message + "). 도로는 회색으로 표시돼요.";
  }
})();
