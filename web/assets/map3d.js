// 3D 지도: 브이월드 건물(층수 높이) + 실제 모양 차도(속도 색) + TMAP 걷는 길 + 주차장·역·공연장
// MapLibre GL(무료 오픈소스) + OpenFreeMap 바탕지도(키 없음)
const MAP3D_STYLE = "https://tiles.openfreemap.org/styles/liberty";
const IDX_HEX = { "원활": "#16a34a", "서행": "#d97706", "정체": "#dc2626" };

function roadsGeoJSON(links, live, shapes = {}) {
  // 실시간 응답에 실제 도로 모양(xy)이 있으면 그걸, 없으면 시작~끝 직선. 모든 차도는 보행 가능(level=0).
  const liveById = {};
  ((live && live.links) || []).forEach((l) => { liveById[l.id] = l; });
  return {
    type: "FeatureCollection",
    features: links.map((l) => {
      const lv = liveById[l.id];
      const r = live && live.roads ? live.roads[l.id] : null;
      const coords = shapes[l.id] || (lv && lv.xy && lv.xy.length > 2 ? lv.xy : [l.a, l.b]);
      return {
        type: "Feature", geometry: { type: "LineString", coordinates: coords },
        properties: {
          lid: String(l.id),
          name: `${l.road} ${l.from}→${l.to}`,
          idx: r ? r.idx : "없음",
          spd: r ? r.spd : null,
          walkable: true,
          underpass: String(l.id) === "1230085700",
        },
      };
    }),
  };
}

async function initMap3D(el, { links, places, live, venues }) {
  if (!window.maplibregl) return null;   // 지도 엔진을 못 불러온 경우
  let shapes = {};
  try {
    const g = await fetch(CONFIG.dataDir + "link_shapes.geojson").then((r) => { if (!r.ok) throw 0; return r.json(); });
    g.features.forEach((f) => { shapes[f.properties.id] = f.geometry.coordinates; });
  } catch (_) { /* 도로 모양 파일이 없으면 시작~끝 직선 */ }
  const dome = places.dome;
  const initZoom = (el && el.clientWidth && el.clientWidth < 520) ? 14.72 : 14.98;
  const map = new maplibregl.Map({
    container: el, style: MAP3D_STYLE,
    center: [dome.lng - 0.0015, dome.lat - 0.0008], zoom: initZoom, pitch: 56, bearing: -18,
    antialias: true, attributionControl: { compact: true },
  });
  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");

  // 바탕지도 스타일만 준비되면 바로 그린다(타일이 다 올 때까지 기다리지 않음). 느린 회선을 위해 30초까지 기다림.
  await new Promise((ok, fail) => {
    let done = false;
    const fin = () => { if (!done) { done = true; ok(); } };
    if (map.isStyleLoaded()) fin();
    map.once("style.load", fin); map.once("load", fin);
    map.once("error", (e) => { if (!done && !map.isStyleLoaded()) { done = true; fail(e.error || e); } });
    setTimeout(() => { if (!done) { done = true; fail(new Error("지도 로딩 시간 초과")); } }, 30000);
  });

  // 1) 건물: 브이월드(층수 높이). 실패하면 바탕지도의 OpenStreetMap 건물을 그대로 둔다.
  let buildingSrc = "OpenStreetMap";
  try {
    const b = await fetch("/api/buildings").then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); });
    map.getStyle().layers.filter((ly) => ly.type === "fill-extrusion").forEach((ly) => map.setLayoutProperty(ly.id, "visibility", "none"));
    map.addSource("vw-buildings", { type: "geojson", data: b });
    map.addLayer({
      id: "vw-buildings", type: "fill-extrusion", source: "vw-buildings",
      paint: {
        "fill-extrusion-color": ["interpolate", ["linear"], ["get", "height"], 3, "#dfe3ea", 30, "#c5ccd8", 90, "#a9b3c4"],
        "fill-extrusion-height": ["get", "height"], "fill-extrusion-base": 0, "fill-extrusion-opacity": 0.88,
      },
    });
    buildingSrc = "브이월드 건물(층수 × 3.3m)";
  } catch (_) { /* 바탕지도 건물 사용 */ }

  // 2) 차도(지상 level=0, 모든 차도 보행 가능): 실시간 속도 색, 방향별로 살짝 띄워 양방향이 겹치지 않게
  map.addSource("roads", { type: "geojson", data: roadsGeoJSON(links, live, shapes) });
  map.addLayer({
    id: "roads", type: "line", source: "roads",
    layout: { "line-cap": "round", "line-join": "round" },
    paint: {
      "line-color": ["match", ["get", "idx"], "원활", IDX_HEX["원활"], "서행", IDX_HEX["서행"], "정체", IDX_HEX["정체"], "#a5acb8"],
      "line-width": ["interpolate", ["linear"], ["zoom"], 13, 3, 17, 9],
      "line-offset": ["interpolate", ["linear"], ["zoom"], 13, 1.5, 17, 5],
      "line-opacity": 0.95,
    },
  });

  // 2-1) 만남의광장~KSPO DOME 지상 보행광장 바닥면 (차도 위, 육교 상판 아래)
  let pedLoaded = false;
  try {
    const pedOver = await fetch(CONFIG.dataDir + "pedestrian_overpass.geojson").then((r) => { if (!r.ok) throw 0; return r.json(); });
    map.addSource("ped-overpass", { type: "geojson", data: pedOver });
    pedLoaded = true;
    map.addLayer({
      id: "ped-promenade-fill", type: "fill", source: "ped-overpass",
      filter: ["==", ["get", "featureRole"], "promenade"],
      paint: { "fill-color": "#fef3c7", "fill-opacity": 0.62 },
    });
    map.addLayer({
      id: "ped-promenade-border", type: "line", source: "ped-overpass",
      filter: ["==", ["get", "featureRole"], "promenade"],
      paint: { "line-color": "#d97706", "line-width": 1.3, "line-opacity": 0.65 },
    });
  } catch (_) { /* 입체 인도 파일 로드 실패 시 기본 지도만 표시 */ }

  // 3) 걷는 길(지상 기준 TMAP 보행자 경로): 육교 상판보다 아래에 두어 하부 차도를 따라가는 선은 육교 밑으로 지나가게 함
  let walkAll = [];
  try {
    const w = await fetch(CONFIG.dataDir + "walk_routes.geojson").then((r) => r.json());
    walkAll = w.features.filter((f) => f.properties.meters < 2500);
    walkAll.forEach((f) => { if (!f.properties.to) f.properties.to = "KSPO DOME"; });   // 예전 파일은 KSPO DOME 기준
  } catch (_) { /* 걷는 길 파일 없음 */ }
  const walkFor = (name) => {
    let f = walkAll.filter((x) => x.properties.to === name);
    if (!f.length && name === "뮤즈라이브") f = walkAll.filter((x) => x.properties.to === "올림픽홀");
    return { type: "FeatureCollection", features: f };
  };
  map.addSource("walk", { type: "geojson", data: walkFor(dome.name || "KSPO DOME") });
  map.addLayer({
    id: "walk", type: "line", source: "walk",
    layout: { "line-cap": "round", "line-join": "round" },
    paint: {
      "line-color": ["match", ["get", "kind"], "station", "#7b4fd6", "#2459d6"],
      "line-width": ["interpolate", ["linear"], ["zoom"], 13, 2, 17, 5],
      "line-dasharray": [1.2, 1.2],
    },
  });

  // 3-1) 차도 위 입체 보행 육교 상판·난간·주 보행축 (level=1: 하부 차도·지상 선 모두 위로 통과)
  if (pedLoaded) {
    map.addLayer({
      id: "ped-overpass-deck-flat", type: "fill", source: "ped-overpass",
      filter: ["==", ["get", "featureRole"], "overpass_deck"],
      paint: { "fill-color": "#fde68a", "fill-opacity": 0.96 },
    });
    map.addLayer({
      id: "ped-overpass-rails", type: "line", source: "ped-overpass",
      filter: ["all", ["==", ["get", "featureRole"], "edge"], ["==", ["get", "bridge"], true], ["!=", ["get", "primaryCorridor"], true]],
      layout: { "line-cap": "butt", "line-join": "round" },
      paint: { "line-color": "#92400e", "line-width": ["interpolate", ["linear"], ["zoom"], 13, 1.6, 17, 3.4], "line-opacity": 0.92 },
    });
    map.addLayer({
      id: "ped-overpass-3d", type: "fill-extrusion", source: "ped-overpass",
      filter: ["==", ["get", "featureRole"], "overpass_deck"],
      paint: {
        "fill-extrusion-color": "#fde68a",
        "fill-extrusion-base": ["get", "baseHeightM"],
        "fill-extrusion-height": ["get", "topHeightM"],
        "fill-extrusion-opacity": 0.94,
      },
    });
    map.addLayer({
      id: "ped-walkway-spine", type: "line", source: "ped-overpass",
      filter: ["==", ["get", "primaryCorridor"], true],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": "#b45309",
        "line-width": ["interpolate", ["linear"], ["zoom"], 13, 1.8, 17, 3.6],
        "line-dasharray": [1.8, 1.4],
        "line-opacity": 0.92,
      },
    });
  }

  // 4) 주차장·역·공연장 표시 (HTML 표식: 한글이 깨지지 않게)
  const mark = (lng, lat, label, cls) => {
    const d = document.createElement("div");
    d.className = "m3d " + cls;
    d.innerHTML = `<span>${label}</span>`;
    return new maplibregl.Marker({ element: d, anchor: "bottom" }).setLngLat([lng, lat]).addTo(map);
  };
  let markers = [];
  const drawMarkers = (pl) => {
    markers.forEach((m) => m.remove());
    markers = [];
    const vname = pl.dome.name || "KSPO DOME";
    // 다른 공연장은 흐리게, 고른 공연장은 진하게
    Object.values(venues || {}).forEach((v) => {
      if (v.name === vname || v.name === "뮤즈라이브" || !v.lat) return;
      markers.push(mark(v.lng, v.lat, v.name, "venue"));
    });
    pl.lots.filter((x) => x.lat && x.kind !== "transfer").forEach((x) =>
      markers.push(mark(x.lng, x.lat, (x.kind === "park" ? "P 공원 주차장" : "P " + x.name.replace(" 주차장", "").replace("올림픽공원 ", "")) + (x.walkMin ? ` · ${x.walkMin}분` : ""), "lot")));
    pl.stations.forEach((s) => markers.push(mark(s.lng, s.lat, `${s.name} · ${s.walkMin}분`, "st")));
    markers.push(mark(pl.dome.lng, pl.dome.lat, vname, "dome"));
  };
  drawMarkers(places);

  // 5) 눌렀을 때 설명
  const pop = new maplibregl.Popup({ closeButton: false, offset: 8 });
  map.on("click", "roads", (e) => {
    const p = e.features[0].properties;
    const under = p.underpass === true || p.underpass === "true";
    const walkNote = under ? "상부 보행 인도(육교) 아래 통과 · 차도 보행 가능" : "차도 · 보행 가능";
    pop.setLngLat(e.lngLat).setHTML(`<b>${p.name}</b><br>${p.spd && p.spd !== "null" ? p.spd + "km/h · " + p.idx : "수집값 없음"}<br><span class="muted small">${walkNote}</span>`).addTo(map);
  });
  const showPedPopup = (e) => {
    pop.setLngLat(e.lngLat).setHTML(
      `<b>만남의광장~KSPO DOME 보행 인도</b><br>보행자 전용 · 하부 차도 위로 지나가는 입체 인도(육교)<br><span class="muted small">아래 차도를 포함한 공원 차도도 보행 가능</span>`
    ).addTo(map);
  };
  ["ped-overpass-3d", "ped-promenade-fill", "ped-walkway-spine"].forEach((id) => {
    if (map.getLayer(id)) map.on("click", id, showPedPopup);
  });
  map.on("click", "walk", (e) => {
    const p = e.features[0].properties;
    pop.setLngLat(e.lngLat).setHTML(`<b>${p.from} → ${p.to}</b><br>걷는 길 ${p.meters}m · 약 ${p.minutes}분`).addTo(map);
  });
  ["roads", "ped-overpass-3d", "ped-promenade-fill", "walk"].forEach((id) => {
    if (!map.getLayer(id)) return;
    map.on("mouseenter", id, () => { map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseleave", id, () => { map.getCanvas().style.cursor = ""; });
  });

  let meMarker = null;
  const setUserLocation = (loc, opts = {}) => {
    if (meMarker) { meMarker.remove(); meMarker = null; }
    if (!loc) return;
    meMarker = mark(loc.lng, loc.lat, "● 내 위치", "me");
    if (opts.fly && distMeters(loc.lat, loc.lng, dome.lat, dome.lng) <= 3000) {
      map.easeTo({ center: [loc.lng, loc.lat], duration: 700 });
    }
  };
  if (typeof USER_GPS !== "undefined" && USER_GPS.loc) setUserLocation(USER_GPS.loc);

  return {
    map, buildingSrc,
    update(newLive) { const s = map.getSource("roads"); if (s) s.setData(roadsGeoJSON(links, newLive, shapes)); },
    setUserLocation,
    // 고른 공연장으로 바꾸기: 표식·걷는 길·지도 중심
    setVenue(pl) {
      drawMarkers(pl);
      map.getSource("walk").setData(walkFor(pl.dome.name || "KSPO DOME"));
      map.easeTo({ center: [pl.dome.lng - 0.0015, pl.dome.lat - 0.0008], duration: 800 });
    },
  };
}

function legend3DHTML(buildingSrc) {
  return `<div class="legend">
    <span><i style="background:${IDX_HEX["원활"]}"></i>● 원활</span>
    <span><i style="background:${IDX_HEX["서행"]}"></i>▲ 서행</span>
    <span><i style="background:${IDX_HEX["정체"]}"></i>■ 정체</span>
    <span><i style="background:#94a3b8"></i>— 수집값 없음</span>
    <span><i style="background:#fde68a;border:1.5px solid #b45309;height:7px"></i>보행 인도(차도 위 육교)</span>
    <span><i style="background:repeating-linear-gradient(90deg,#1d4ed8 0 5px,transparent 5px 9px)"></i>주차장→공연장 도보</span>
    <span><i style="background:repeating-linear-gradient(90deg,#7c3aed 0 5px,transparent 5px 9px)"></i>역→공연장 도보</span>
    <span>차도: 보행 가능 · 건물: ${buildingSrc}</span></div>`;
}
