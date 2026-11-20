// 운영자 화면: 데이터 점검 결과 — scripts/19_data_quality.py가 만든 data_quality.json
// 원본 공공데이터에서 찾은 문제와 처리 방법, 2025 입출차 달별 받은 비율, 분석에서 뺀 공연 수를 한곳에 보인다.
(async function () {
  const $ = (id) => document.getElementById(id);
  if (!$("dataQuality")) return;
  let Q = null;
  try { Q = await loadJSON("data_quality.json"); } catch (_) {}
  if (!Q) {
    $("dqStatus").innerHTML = `<span class="chip">○ 아직 없음</span> 점검 결과 자료(data_quality.json)를 불러오지 못했어요.`;
    return;
  }
  const n = (v) => Number(v).toLocaleString();
  const pct = (v) => Math.round(v * 100) + "%";
  const c = Q.check;
  $("dqStatus").innerHTML = c
    ? `<span class="chip warn">▲ 일부만 받음</span> 2025년 입출차 전체 ${n(c.total)}줄 중 <b>${n(c.received)}줄</b>을 받았고, 겹친 줄 ${n(c.duplicates)}줄을 빼면
       <b>${n(c.usable)}줄(${pct(c.usableShare)})</b>을 써요. 기록 번호 범위로 보면 전체의 ${(c.spanShare * 100).toFixed(2)}%에 걸쳐 있어 통째로 빠진 달은 없어요.`
    : `<span class="chip">○ 아직 없음</span> 2025년 입출차 점검 결과가 아직 없어요.`;

  $("dqIssues").innerHTML = `<tr><th>데이터</th><th>찾은 문제</th><th>이렇게 처리했어요</th></tr>` +
    (Q.issues || []).map((x) => `<tr><td class="nowrap">${x.data}</td><td>${x.problem}</td><td>${x.handling}</td></tr>`).join("");

  $("dqMonths").innerHTML = (Q.months || []).length
    ? `<tr><th>달</th><th>받은 줄</th><th>기록 번호 폭</th><th>받은 비율</th><th>비고</th></tr>` +
      Q.months.map((m) => `<tr><td class="nowrap">${m.month}</td><td class="nowrap">${n(m.got)}</td><td class="nowrap">${n(m.span)}</td>
        <td class="nowrap"><b>${pct(m.ratio)}</b></td><td>${m.note ? "▲ " + m.note : "● 여러 날이 고르게 섞임"}</td></tr>`).join("")
    : `<tr><td>달별 점검 결과가 아직 없어요</td></tr>`;

  const sk = Object.values(Q.skipped || {});
  $("dqSkipped").innerHTML = sk.length
    ? `<tr><th>분석</th><th>쓴 공연</th><th>뺀 2025년 공연</th></tr>` +
      sk.map((s) => `<tr><td>${s.label}</td><td class="nowrap">${s.used != null ? n(s.used) + "회" : "—"}</td>
        <td class="nowrap">${s.skipped}회</td></tr>`).join("")
    : "";
  $("dqSrc").innerHTML =
    `받은 비율 = 받은 줄 ÷ 그 달 기록 번호 폭. 대수(차 몇 대)는 이 비율로 나눠 보정해요. 뺀 공연 = 원본이 잘렸거나 그 시간대 기록이 모자라 대수를 믿을 수 없는 공연. ` +
    `점검 방법: 저장소의 scripts/17_check_2025.py(인증키 없이 실행). ${Q.built ? "계산일 " + Q.built + ". " : ""}` +
    `<a href="data-guide.html">결과 데이터 설명서 보기</a>`;
})();
