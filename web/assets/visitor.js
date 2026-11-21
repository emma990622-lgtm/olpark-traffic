// 방문객 혼잡 예측·분산 안내 (관객·운영자 화면 공통) — scripts/23_visitor_model.py가 만든 visitor_forecast.json
// 고른 날짜의 요일 유형·공연·날씨 예보를 모형 계수에 넣어 시간별 방문객(올림픽공원 동 생활인구)을 계산한다.
// predict()는 scripts/23의 design()과 같은 식이어야 한다.
(async function () {
  const $ = (id) => document.getElementById(id);
  if (!$("visitorCard")) return;
  const isOp = document.body.classList.contains("is-operator");
  let F = null, events = [], places = null;
  try { F = await loadJSON("visitor_forecast.json"); } catch (_) {}
  try { events = await loadJSON("events.json"); } catch (_) {}
  try { places = await loadJSON("places.json"); } catch (_) {}
  if (!F || !F.hourly) {
    $("vfStatus").innerHTML = `<span class="chip">○ 아직 없음</span> 방문객 예측 자료를 불러오지 못했어요.`;
    return;
  }
  const H = F.hourly, LV = F.levels;
  const n = (v) => Math.round(v).toLocaleString();
  const round100 = (v) => (Math.round(v / 100) * 100).toLocaleString();
  const BIG = ["핸드볼경기장", "올림픽홀"];
  const wxCache = {};

  function dayType(d) {
    const dow = new Date(d + "T00:00:00").getDay();
    if (dow === 0 || (F.holidays || []).includes(d)) return "일·공휴일";
    return dow === 6 ? "토" : "평일";
  }
  function level(v) {
    if (v < LV.p50) return { cls: "good", sym: "●", label: "여유" };
    if (v < LV.p80) return { cls: "", sym: "●", label: "보통" };
    if (v < LV.p95) return { cls: "warn", sym: "▲", label: "붐빔" };
    return { cls: "bad", sym: "■", label: "매우 붐빔" };
  }
  // 날씨 예보(Open-Meteo, 인증키 없음). 16일보다 먼 날·지난 날·실패 → null
  async function forecast(d) {
    if (d in wxCache) return wxCache[d];
    const days = (new Date(d + "T00:00:00") - new Date(new Date().toDateString())) / 86400000;
    if (days < 0 || days > 15) return (wxCache[d] = { none: days < 0 ? "지난 날이라 예보가 없어서" : "날씨 예보는 16일 앞까지만 나와서" });
    try {
      const w = F.weatherApi;
      const r = await fetch(`https://api.open-meteo.com/v1/forecast?latitude=${w.lat}&longitude=${w.lon}&hourly=apparent_temperature,precipitation&timezone=Asia%2FSeoul&start_date=${d}&end_date=${d}`);
      if (!r.ok) throw new Error(r.status);
      const j = await r.json();
      if (!j.hourly || j.hourly.time.length < 24) throw new Error("short");
      wxCache[d] = { feels: j.hourly.apparent_temperature, precip: j.hourly.precipitation };
    } catch (_) { wxCache[d] = { none: "날씨 예보를 불러오지 못해서" }; }
    return wxCache[d];
  }
  // 모형: ln(생활인구) = 요일 유형×시각 + 월 + 추세 + 공연(시작 기준 시간) + 다른 공연장 + 페스티벌 + 날씨
  function predict(d, h, ctx) {
    const dt = new Date(d + "T00:00:00");
    let x = H.base[ctx.type][h] + H.month[dt.getMonth()];
    const yrs = Math.min(H.trendCapYears, (dt - new Date(H.trendFrom + "T00:00:00")) / (365.25 * 86400000));
    x += H.trend * yrs;                                   // 추세는 자료가 있는 마지막 때 값에서 멈춘다(더 늘려 잡지 않음)
    if (ctx.start != null) {
      const rel = Math.floor((h * 60 - ctx.start) / 60);
      if (H.show[rel] != null) x += H.show[rel];
    }
    if (ctx.other) for (const k in H.other) { const [a, b] = k.split("-").map(Number); if (h >= a && h <= b) x += H.other[k]; }
    if (ctx.festival && h >= 10 && h <= 21) x += H.festival;
    if (h >= H.wxHours[0] && h <= H.wxHours[1]) {
      const p = ctx.wx ? ctx.wx.precip[h] : ctx.rain ? 1 : 0, f = ctx.wx ? ctx.wx.feels[h] : null;
      if (p >= 0.5) x += H.rain;
      if (p >= 3) x += H.heavy;
      if (f != null && f < 0) x += H.cold;
      if (f != null && f >= 30) x += H.hot;
    }
    return x;
  }

  let seq = 0;
  async function render() {
    const d = $("date") && $("date").value;
    if (!d) return;
    const mine = ++seq;                                   // 늦게 끝난 앞선 계산이 화면을 덮어쓰지 않게
    const todays = events.filter((e) => e.date === d);
    const kspo = todays.find((e) => e.venue === "KSPO DOME" && e.times && e.times.length);
    const mode = $("vfWx").value;
    const got = mode === "auto" ? await forecast(d) : null;
    const wx = got && !got.none ? got : null;
    if (mine !== seq) return;                             // 기다리는 동안 날짜·날씨 선택이 바뀜
    const ctx = { type: dayType(d), start: kspo ? toMin(kspo.times[0]) : null, wx, rain: mode === "rain",
                  other: todays.some((e) => BIG.includes(e.venue)), festival: todays.some((e) => /페스티벌|festival/i.test(e.title)) };
    const sh = ctx.start != null ? Math.floor(ctx.start / 60) : null;
    const from = sh != null ? Math.max(9, sh - 6) : 10, to = sh != null ? Math.min(23, sh + 5) : 21;
    const rows = [];
    for (let h = from; h <= to; h++) {
      const x = predict(d, h, ctx);
      const r = ctx.start != null ? H.residShow : H.resid;
      rows.push({ h, v: Math.exp(x), lo: Math.exp(x + r.lo), hi: Math.exp(x + r.hi), rainy: wx && wx.precip[h] >= 0.5 });
    }
    const peak = rows.reduce((a, b) => (b.v > a.v ? b : a));
    const pl = level(peak.v);
    const maxV = Math.max(...rows.map((r) => r.hi));
    // 분산 안내: 가장 붐비는 때보다 15% 넘게 덜 붐비는, 그 전의 가장 늦은 시각
    const early = rows.filter((r) => r.h < peak.h && r.v <= peak.v * 0.85).pop();
    const wxTxt = mode === "rain" ? "비가 온다고 가정" : mode === "dry" ? "비가 안 온다고 가정"
      : wx ? (rows.some((r) => r.rainy) ? "예보: 이 시간대에 비 소식이 있어요" : "예보: 이 시간대에 비 소식이 없어요")
      : `${got && got.none ? got.none : "예보가 없어서"} 비가 안 온다고 가정`;
    $("vfStatus").innerHTML =
      `<span class="chip ${pl.cls}">${pl.sym} ${pl.label}</span> ` +
      (kspo ? `<b>${kspo.times[0]}</b> KSPO DOME 공연이 있는 ${ctx.type === "평일" ? "평일" : ctx.type === "토" ? "토요일" : "일요일·공휴일"}이에요. ` : `KSPO DOME 공연이 없는 날이에요. `) +
      `공원 일대가 가장 붐비는 때는 <b>${peak.h}시쯤</b>(약 ${round100(peak.v)}명)으로 예상돼요.` +
      (early ? ` <b>${early.h + 1}시 전에 도착</b>하면 그때보다 약 ${Math.round((1 - early.v / peak.v) * 100)}% 덜 붐벼요.` : "") +
      ` <span class="muted small">(${wxTxt})</span>`;

    $("vfHours").innerHTML = `<tr><th>시각</th><th>예상 인원</th><th>붐비는 정도</th></tr>` + rows.map((r) => {
      const l = level(r.v);
      const tag = sh != null && r.h === sh ? " · 공연 시작" : "";
      return `<tr><td class="nowrap">${r.h}시${tag}${r.rainy ? " · 비" : ""}</td>
        <td><div style="display:flex;flex-wrap:wrap;align-items:center;gap:4px 8px"><span style="white-space:nowrap;min-width:5.5em">약 ${round100(r.v)}명</span>
          <span aria-hidden="true" style="flex:1 1 56px;min-width:56px;height:8px;background:var(--line);border-radius:4px;overflow:hidden"><span style="display:block;height:100%;width:${Math.round((r.v / maxV) * 100)}%;background:var(--${l.cls === "bad" ? "bad" : l.cls === "warn" ? "warn" : l.cls === "good" ? "good" : "none"})"></span></span></div></td>
        <td class="nowrap"><span class="chip ${l.cls}">${l.sym} ${l.label}</span></td></tr>`;
    }).join("");

    // 역별 쏠림
    const S = F.stations[ctx.type] || F.stations["일·공휴일"] || F.stations["평일"];
    const usedType = F.stations[ctx.type] ? ctx.type : F.stations["일·공휴일"] ? "일·공휴일" : "평일";
    if (S && kspo) {
      const walk = (name) => { const p = places && (places.stations || []).find((s) => s.name.replace("역", "") === name); return p ? `${p.line} · 걸어서 ${p.walkMin}분` : ""; };
      const top = S.list[0];
      const alt = S.list.slice(1).filter((s) => walk(s.name)).map((s) => `${s.name}역(${walk(s.name)})`);
      $("vfStations").innerHTML =
        `<div class="notice info" style="margin:12px 0 8px">공연일에 평소보다 늘어나는 지하철 하차 승객 10명 중 약 <b>${Math.round(top.share * 10)}명</b>이 <b>${top.name}역</b>에 몰려요.` +
        (alt.length ? ` 조금 더 걷더라도 ${alt.join(", ")}을 쓰면 역 안 혼잡을 피할 수 있어요.` : "") + `</div>
        <div class="table-scroll"><table class="list"><tr><th>역</th><th>평소 하차(하루)</th><th>공연일 하차</th><th>늘어난 승객 몫</th></tr>` +
        S.list.map((s) => `<tr><td class="nowrap">${s.name}역${walk(s.name) ? `<br><span class="muted small">${walk(s.name)}</span>` : ""}</td>
          <td class="nowrap">${n(s.base)}명</td><td class="nowrap">${n(s.show)}명</td><td class="nowrap"><b>${Math.round(s.share * 100)}%</b> (+${n(s.extra)}명)</td></tr>`).join("") +
        `</table></div><p class="muted small" style="margin:6px 0 0">${usedType} 기준: KSPO DOME 공연일 ${S.showDays}일과 큰 공연 없는 날 ${S.baseDays}일의 하루 하차 인원 중앙값${usedType !== ctx.type ? ` (${ctx.type}은 큰 공연 없는 날이 적어 ${usedType} 값으로 보여요)` : ""}.</p>`;
    } else $("vfStations").innerHTML = "";

    const V = F.valid;
    const effTable = (title, list) => `<h3 class="subhead">${title}</h3><div class="table-scroll"><table class="list"><tr><th>조건</th><th>변화</th><th>95% 범위</th></tr>` +
      list.map((e) => `<tr><td>${e.label}</td><td class="nowrap"><b>${e.pct > 0 ? "+" : ""}${e.pct}%</b></td><td class="nowrap">${e.lo > 0 ? "+" : ""}${e.lo}% ~ ${e.hi > 0 ? "+" : ""}${e.hi}%</td></tr>`).join("") + `</table></div>`;
    $("vfDetail").innerHTML = isOp
      ? effTable("시간별 방문객(생활인구)에 미치는 영향", H.effects) + effTable(`하루 지하철 하차(주변 5개 역 합, ${F.daily.n}일)에 미치는 영향`, F.daily.effects)
      : "";
    $("vfSrc").innerHTML =
      `예상 인원 = ${F.scopeNote} 붐비는 정도 기준: ${n(LV.p50)}명 미만 여유, ${n(LV.p80)}명 미만 보통, ${n(LV.p95)}명 미만 붐빔(${LV.note.split(".")[0]}). ` +
      `검증: ${V.train.slice(0, 7)}~${V.train.slice(13, 20)} 자료로 맞추고 ${V.test.slice(0, 7)}~${V.test.slice(13, 20)}을 맞혀 보니 공연 시간대 평균 오차 ${V.mapeShow}%` +
      `(같은 요일·시각 과거 중앙값만 쓰면 ${V.mapeShowBase}%), 공연일 가장 붐비는 시각을 1시간 안으로 맞힌 날 ${Math.round(V.peakHourWithin1 * 100)}%(${V.showDays}일). ` +
      `공연 시간대 예상의 80% 범위는 약 ${Math.round((Math.exp(H.residShow.lo) - 1) * 100)}% ~ +${Math.round((Math.exp(H.residShow.hi) - 1) * 100)}%. ` +
      `출처: ${F.source}. ${F.weatherApi.note}. 방법: ${F.method}. 계산일 ${F.built}.` +
      (isOp ? "" : ` <a href="data-guide.html">데이터 설명 보기</a>`);
  }

  $("vfWx").addEventListener("change", render);
  $("date").addEventListener("change", render);
  // 날짜 목록은 다른 스크립트가 채우므로 값이 생길 때까지 잠깐 기다린다
  let tries = 0, last = null;
  const t = setInterval(() => {
    const v = $("date").value;
    if (v && v !== last) { last = v; render(); }
    if (++tries > 40) clearInterval(t);
  }, 250);
})();
