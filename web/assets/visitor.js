// 관객: '주로 공연장에 도착하는 시간' — scripts/31_arrival_profile.py가 만든 arrival_profile.json
// 1단계('어떤 공연에 가세요?')에서 고른 날짜·공연의 시작 시각과 요일 유형(평일 / 주말·공휴일)에 맞춰
// 공연 시작 6시간 전~시작 시간대별 예상 관객 도착 비중(%) 막대그래프를 그린다.
(async function () {
  const $ = (id) => document.getElementById(id);
  if (!$("visitorCard")) return;
  const chartBox = $("vfChart");
  const noteBox = $("vfNote");

  let A = null, events = [];
  try {
    [A, events] = await Promise.all([
      loadJSON("arrival_profile.json"),
      loadJSON("events.json").catch(() => []),
    ]);
  } catch (_) {}

  if (!A || !A.profiles) {
    $("vfStatus").innerHTML = `<span class="chip">○ 아직 없음</span> 지난 공연 도착 시간대 자료를 불러오지 못했어요.`;
    return;
  }

  const holSet = new Set(A.holidays || []);

  function isWeekendOrHoliday(d) {
    const dow = new Date(d + "T00:00:00").getDay();
    return dow === 0 || dow === 6 || holSet.has(d);
  }

  function dayLabel(d) {
    const dow = new Date(d + "T00:00:00").getDay();
    if (holSet.has(d) && dow !== 0 && dow !== 6) return `${DOW[dow]}요일·공휴일`;
    return `${DOW[dow]}요일`;
  }

  function selectedShow() {
    const d = $("date") && $("date").value;
    const evSel = $("event");
    if (!d || !evSel || !evSel.value) return null;
    const dayEvents = events.filter((e) => e.date === d && e.times && e.times.length);
    const [idxStr, start] = evSel.value.split("|");
    const ev = dayEvents[+idxStr];
    if (ev && start) return { date: d, start, ev, dayEvents };
    const opt = evSel.selectedOptions && evSel.selectedOptions[0];
    const m = opt && opt.textContent.match(/^(\d{1,2}:\d{2})\s+(.+?)\s+·\s+(.+)$/);
    if (!m) return null;
    return {
      date: d,
      start: m[1],
      ev: { date: d, venue: m[2], title: m[3], seats: null },
      dayEvents,
    };
  }

  function slotTier(pct) {
    if (pct >= 24) return { cls: "bad", sym: "■", label: "집중" };
    if (pct >= 15) return { cls: "warn", sym: "▲", label: "혼잡" };
    return { cls: "good", sym: "●", label: "여유" };
  }

  function formatClockRange(t0Min, t1Min) {
    const m0 = ((Math.round(t0Min) % 1440) + 1440) % 1440;
    const m1 = ((Math.round(t1Min) % 1440) + 1440) % 1440;
    const h0 = Math.floor(m0 / 60), min0 = m0 % 60;
    const h1 = Math.floor(m1 / 60), min1 = m1 % 60;
    if (min0 === 0 && min1 === 0) {
      return { html: `${h0}~${h1}시`, plain: `${toHHMM(t0Min)}~${toHHMM(t1Min)}` };
    }
    const s0 = `${String(h0).padStart(2, "0")}:${String(min0).padStart(2, "0")}`;
    const s1 = `${String(h1).padStart(2, "0")}:${String(min1).padStart(2, "0")}`;
    return { html: `${s0}~<br>${s1}`, plain: `${s0}~${s1}` };
  }

  function shortRelLabel(relHour) {
    return relHour === -1 ? "1시간 전" : `${-relHour - 1}~${-relHour}시간 전`;
  }

  function render() {
    const sel = selectedShow();
    if (!sel) return;
    const { date, start, ev, dayEvents } = sel;
    const wknd = isWeekendOrHoliday(date);
    const prof = A.profiles[wknd ? "weekend" : "weekday"] || A.profiles.all;
    const kindTxt = wknd ? "주말·공휴일" : "평일";
    const startMin = toMin(start);

    const slots = prof.slots.map((s) => {
      const t0 = startMin + s.fromMin;
      const t1 = startMin + s.toMin;
      const ck = formatClockRange(t0, t1);
      const tier = slotTier(s.pct);
      return { ...s, t0, t1, ck, tier };
    });

    const maxPct = Math.max(...slots.map((s) => s.pct), 1);
    const twoHourStart = toHHMM(startMin - 120);
    const peak2Pct = prof.last2hPct;

    $("vfStatus").innerHTML =
      `<span class="chip bad">■ 도착 집중</span> ` +
      `선택하신 <b>${start} ${ev.venue}</b> 공연(${dayLabel(date)})은 <b>${twoHourStart}~${start}</b>(시작 2시간 전~시작)에 관객의 <b>약 ${peak2Pct}%</b>가 몰릴 것으로 예상돼요. ` +
      `여유 있게 도착하려면 <b>${twoHourStart} 전</b>을 권해요.`;

    if (chartBox) {
      const ariaSummary = slots.map((s) => `${s.ck.plain}(${s.label}) 약 ${s.pct}%`).join(", ");
      chartBox.innerHTML =
        `<div class="arr-chart-box" role="region" aria-label="${ev.title} 예상 도착 시간대 막대그래프: ${ariaSummary}">
          <div class="arr-chart-head">
            <span class="arr-chart-title">${date.slice(5).replace("-", "/")}(${DOW[new Date(date + "T00:00:00").getDay()]}) · ${start} 시작 기준</span>
            <span class="arr-chart-legend" aria-hidden="true">
              <span class="lg-good">● 여유</span>
              <span class="lg-warn">▲ 혼잡</span>
              <span class="lg-bad">■ 집중</span>
            </span>
          </div>
          <div class="arr-bars">` +
        slots.map((s) => {
          const barH = Math.max(12, Math.round((s.pct / maxPct) * 100));
          const tip = `${s.ck.plain} (시작 ${s.label}): 평균 약 ${s.pct}% (지난 공연 가운데 50% 범위 ${Math.round(s.p25)}~${Math.round(s.p75)}%)`;
          return `<div class="arr-col is-${s.tier.cls}" title="${tip}">
            <div class="arr-val"><span aria-hidden="true">${s.tier.sym}</span> ${s.pct}%</div>
            <div class="arr-track"><div class="arr-fill" style="height:${barH}%"></div></div>
            <div class="arr-lbl">
              <span class="arr-clock">${s.ck.html}</span>
              <span class="arr-rel">${shortRelLabel(s.relHour)}</span>
            </div>
          </div>`;
        }).join("") +
        `</div>
          <div class="arr-start-row">
            <span class="arr-start-pill">▶ ${start} 공연 시작</span>
          </div>
        </div>`;
    }

    if (noteBox) {
      const activeModeBtn = document.querySelector("#mode button.on");
      const mode = activeModeBtn ? activeModeBtn.dataset.v : "car";
      const notes = [];

      if (mode === "car" && A.carEntry) {
        const C = A.carEntry;
        const halfClock = toHHMM(startMin + C.half.med);
        const mostClock = toHHMM(startMin + C.most.med);
        notes.push(
          `<div class="notice info" style="margin-top:10px"><b>차로 오시는 경우:</b> 지난 공연 ${C.shows}회에서 관객 차 절반(50%)은 <b>${halfClock}</b>(시작 ${Math.abs(C.half.med) >= 60 ? durText(Math.abs(C.half.med)) : Math.abs(C.half.med) + "분"} 전)까지, ` +
          `90%는 <b>${mostClock}</b>(시작 ${Math.abs(C.most.med)}분 전)까지 이미 주차장에 들어왔어요. 공연장 가까운 구역에 세우려면 <b>${twoHourStart} 전</b> 입차가 유리해요.</div>`
        );
      } else if (mode === "transit" && A.subwayTop) {
        const S = A.subwayTop;
        notes.push(
          `<div class="notice info" style="margin-top:10px"><b>대중교통으로 오시는 경우:</b> 공연일에 평소보다 늘어나는 지하철 하차 승객의 약 <b>${S.sharePct}%</b>가 <b>${S.topStation}</b>에 집중돼요. ` +
          `관객이 몰리는 <b>${twoHourStart}~${start}</b>에 오신다면 몽촌토성역(8호선)·한성백제역(9호선)에서 걸어오면 개찰구 혼잡을 줄일 수 있어요.</div>`
        );
      }

      if (ev.venue !== "KSPO DOME") {
        const otherKspo = dayEvents.find((x) => x.venue === "KSPO DOME" && x.times && x.times.length);
        const coNote = otherKspo
          ? ` 또한 이날은 <b>${otherKspo.times[0]} KSPO DOME</b> 공연도 함께 열려 <b>${toHHMM(toMin(otherKspo.times[0]) - 120)}~${otherKspo.times[0]}</b> 무렵 공원 전체가 더 붐빌 수 있어요.`
          : "";
        notes.push(
          `<p class="muted small" style="margin:8px 0 0">참고: <b>${ev.venue}</b>${ev.seats ? `(${ev.seats.toLocaleString()}석)` : ""}은 행정동 전체 생활인구(평소 약 2만 명)에서 단독 공연 유입만 따로 가려내기 어려워, ` +
          `선택하신 시작 시각(<b>${start}</b>, ${kindTxt})에 올림픽공원 대형 공연(KSPO DOME 단독 공연일 ${prof.shows}회) 도착 비중을 맞춘 참고치예요.${coNote}</p>`
        );
      } else {
        const otherBig = dayEvents.filter((x) => x !== ev && (x.venue === "올림픽홀" || x.venue === "핸드볼경기장"));
        if (otherBig.length) {
          notes.push(
            `<p class="muted small" style="margin:8px 0 0">참고: 이날은 같은 공원 안 ${otherBig.map((x) => `<b>${x.venue}</b>(${x.times.join("·")})`).join(", ")} 공연도 함께 열려 도착 시간대에 공원 일대가 평소 공연일보다 더 붐빌 수 있어요.</p>`
          );
        }
      }
      noteBox.innerHTML = notes.join("");
    }

    const P = A.profiles;
    $("vfSrc").innerHTML =
      `출처: ${A.source}. 방법: ${A.method}(${kindTxt} ${prof.shows}회 적용 — 전체 단독 공연일 ${P.all.shows}회: 평일 ${P.weekday.shows}회·주말 및 공휴일 ${P.weekend.shows}회, ` +
      `기간 ${A.period}, 다른 공연장 포함 단회차 ${A.crossCheckAllSingle.shows}회 교차검증 완료). ` +
      (A.carEntry ? `차량 입차 시각: ${A.carEntry.source}(공연 ${A.carEntry.shows}회). ` : "") +
      `계산일 ${A.built}. <a href="data-guide.html">데이터 설명 보기</a>`;
  }

  if ($("date")) $("date").addEventListener("change", () => setTimeout(render, 0));
  if ($("event")) $("event").addEventListener("change", render);
  document.querySelectorAll("#mode button").forEach((b) => {
    b.addEventListener("click", () => setTimeout(render, 0));
  });

  // 공연 목록은 audience.js가 채우므로 선택값이 생길 때까지 잠깐 기다린다
  let tries = 0, lastKey = "";
  const t = setInterval(() => {
    const key = `${$("date") && $("date").value}|${$("event") && $("event").value}`;
    if ($("event") && $("event").value && key !== lastKey) {
      lastKey = key;
      render();
      clearInterval(t);
    } else if (++tries > 40) {
      clearInterval(t);
    }
  }, 200);
})();
