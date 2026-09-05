/* SIH26162 — Leaflet dashboard: FIRMS fire points × OSM industrial zones,
   with a toggle between individual detections and DBSCAN-clustered thermal sites. */
"use strict";

const FIRES_URL = "/api/flagged-fires";
const ZONES_URL = "/api/industrial-zones";
const SITES_URL = "/api/thermal-sites";

const CONFIDENCE_COLORS = {
  h: "#d7191c",
  n: "#fd8d3c",
  l: "#ffd700",
};
const CONFIDENCE_LABELS = { h: "high", n: "nominal", l: "low" };

const SITE_COLOR = "#7a2ea0";

const map = L.map("map").setView([22, 79], 5);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "&copy; OpenStreetMap contributors",
  maxZoom: 18,
}).addTo(map);

const zoneLayer = L.geoJSON(null, {
  style: {
    color: "#3388ff",
    weight: 1,
    fillColor: "#3388ff",
    fillOpacity: 0.18,
  },
  onEachFeature: (feature, layer) => {
    const props = feature.properties || {};
    const rows = [
      ["Name", props.name || "—"],
      ["Landuse", props.landuse || "—"],
      ["Industrial", props.industrial || "—"],
      ["OSM id", props.osm_id],
    ];
    layer.bindPopup(rows.map(([k, v]) => `<b>${k}:</b> ${v}`).join("<br>"));
  },
}).addTo(map);

const fireMarkers = new Map();
const fireLayer = L.layerGroup().addTo(map);
const siteLayer = L.layerGroup();

const SITE_LAYER_ID = "siteLayer";
const FIRE_LAYER_ID = "fireLayer";

const listEl = document.getElementById("list");
const summaryEl = document.getElementById("summary");
const detectionsBtn = document.getElementById("view-detections");
const sitesBtn = document.getElementById("view-sites");

const cache = { firesFC: null, zonesFC: null, sitesFC: null };
let currentView = "detections";

function confidenceColor(confidence) {
  return CONFIDENCE_COLORS[confidence] || "#888888";
}

function confidenceLabel(confidence) {
  return CONFIDENCE_LABELS[confidence] || confidence || "unknown";
}

function formatDistance(meters) {
  if (meters == null || !isFinite(meters)) return "—";
  return meters >= 1000
    ? `${(meters / 1000).toFixed(1)} km`
    : `${Math.round(meters)} m`;
}

function formatTime(acqDate, acqTime) {
  const time = String(acqTime).padStart(4, "0");
  return `${acqDate} ${time.slice(0, 2)}:${time.slice(2)} UTC`;
}

function firePopupContent(prop) {
  const persistent = prop.persistent_thermal_source
    ? `<p style="color:#b91c1c;font-weight:600;margin:4px 0">
         Persistent thermal source — ${prop.occurrence_count} occurrences in last 14 days</p>`
    : "";
  const flag = prop.near_industrial
    ? `<p style="color:#c0382b;font-weight:600;margin:4px 0">
         within ${formatDistance(prop.distance_m)} of industrial zone</p>`
    : "";
  const rows = [
    ["Confidence", confidenceLabel(prop.confidence)],
    ["Brightness", prop.bright_ti4 != null ? `${prop.bright_ti4} K` : "—"],
    ["FRP", prop.frp != null ? `${prop.frp} MW` : "—"],
    ["Observed", formatTime(prop.acq_date, prop.acq_time)],
    ["Satellite", prop.satellite || "—"],
    ["Day/night", prop.daynight || "—"],
    ["Nearest zone", formatDistance(prop.distance_m)],
  ];
  const body = rows.map(([k, v]) => `<div><b>${k}:</b> ${v}</div>`).join("");
  return `${persistent}${flag}${body}`;
}

function sitePopupContent(prop) {
  const rows = [
    ["Members", `${prop.member_count} recurring detection(s)`],
    ["Total occurrences", `${prop.total_occurrences} days / 14`],
    ["Nearest zone", prop.near_industrial_zone || "—"],
    ["Zone distance", formatDistance(prop.distance_m)],
  ];
  const body = rows.map(([k, v]) => `<div><b>${k}:</b> ${v}</div>`).join("");
  return `<p style="margin:0 0 4px;font-weight:600;color:${SITE_COLOR}">${prop.site_name}</p>${body}`;
}

function renderFireMarkers(features) {
  fireLayer.clearLayers();
  fireMarkers.clear();
  for (const feature of features) {
    const [lon, lat] = feature.geometry.coordinates;
    const props = feature.properties || {};
    const isPersistent = props.persistent_thermal_source;
    const marker = L.circleMarker([lat, lon], {
      radius: isPersistent ? 10 : 6,
      color: isPersistent
        ? "#b91c1c"
        : props.near_industrial
          ? "#1f2d3d"
          : "#333333",
      weight: isPersistent || props.near_industrial ? 2 : 1,
      dashArray: isPersistent ? "4 4" : null,
      fillColor: confidenceColor(props.confidence),
      fillOpacity: 0.85,
    })
      .bindPopup(firePopupContent(props))
      .addTo(fireLayer);
    fireMarkers.set(feature.id, marker);
  }
}

function renderSiteMarkers(sitesFC) {
  siteLayer.clearLayers();
  for (const feature of sitesFC.features || []) {
    const [lon, lat] = feature.geometry.coordinates;
    L.circleMarker([lat, lon], {
      radius: 12,
      color: "#3c1053",
      weight: 2,
      fillColor: SITE_COLOR,
      fillOpacity: 0.8,
    })
      .bindPopup(sitePopupContent(feature.properties))
      .addTo(siteLayer);
  }
}

function renderZones(featureCollection) {
  zoneLayer.clearLayers();
  zoneLayer.addData(featureCollection);
}

function sectionTitle(label) {
  const div = document.createElement("div");
  div.className = "empty";
  div.style.textAlign = "left";
  div.style.fontWeight = "600";
  div.style.padding = "12px 16px 4px";
  div.textContent = label;
  return div;
}

function buildEntry(feature) {
  const props = feature.properties;
  const entry = document.createElement("div");
  entry.className = "entry";

  const head = document.createElement("div");
  head.className = "head";
  const title = document.createElement("span");
  const satellite = props.satellite || "VIIRS";
  title.textContent = `Fire ${feature.id} · ${satellite}`;
  const dist = document.createElement("span");
  dist.className = "dist";
  dist.textContent = formatDistance(props.distance_m);
  head.append(title, dist);
  entry.appendChild(head);

  const dl = document.createElement("dl");
  const rows = [
    ["Confidence", confidenceLabel(props.confidence)],
    ["Brightness", props.bright_ti4 != null ? `${props.bright_ti4} K` : "—"],
    ["FRP", props.frp != null ? `${props.frp} MW` : "—"],
    ["Observed", formatTime(props.acq_date, props.acq_time)],
  ];
  if (props.persistent_thermal_source) {
    rows.push(["Occurrences", `${props.occurrence_count} days / 14`]);
  }
  for (const [k, v] of rows) {
    const dt = document.createElement("dt");
    dt.textContent = k;
    const dd = document.createElement("dd");
    dd.textContent = v;
    dl.append(dt, dd);
  }
  entry.appendChild(dl);

  entry.addEventListener("click", () => {
    const [lon, lat] = feature.geometry.coordinates;
    map.flyTo([lat, lon], 12);
    const marker = fireMarkers.get(feature.id);
    if (marker) marker.openPopup();
  });
  return entry;
}

function buildSiteEntry(feature) {
  const props = feature.properties;
  const entry = document.createElement("div");
  entry.className = "entry";
  entry.style.borderLeftColor = SITE_COLOR;

  const head = document.createElement("div");
  head.className = "head";
  const title = document.createElement("span");
  title.textContent = props.site_name;
  const count = document.createElement("span");
  count.className = "dist";
  count.textContent = `${props.member_count} members`;
  head.append(title, count);
  entry.appendChild(head);

  const dl = document.createElement("dl");
  const rows = [
    ["Total occurrences", `${props.total_occurrences} days / 14`],
    ["Nearest zone", props.near_industrial_zone || "—"],
    ["Zone distance", formatDistance(props.distance_m)],
  ];
  for (const [k, v] of rows) {
    const dt = document.createElement("dt");
    dt.textContent = k;
    const dd = document.createElement("dd");
    dd.textContent = v;
    dl.append(dt, dd);
  }
  entry.appendChild(dl);

  entry.addEventListener("click", () => {
    const [lon, lat] = feature.geometry.coordinates;
    map.flyTo([lat, lon], 13);
  });
  return entry;
}

function renderDetectionsSidebar(features) {
  const persistent = features
    .filter((f) => f.properties && f.properties.persistent_thermal_source)
    .sort(
      (a, b) =>
        b.properties.occurrence_count - a.properties.occurrence_count ||
        a.properties.distance_m - b.properties.distance_m,
    );
  const flagged = features
    .filter(
      (f) =>
        f.properties &&
        f.properties.near_industrial &&
        !f.properties.persistent_thermal_source,
    )
    .sort((a, b) => a.properties.distance_m - b.properties.distance_m);

  listEl.innerHTML = "";
  if (persistent.length === 0 && flagged.length === 0) {
    const el = document.createElement("div");
    el.className = "empty";
    el.textContent = "No persistent sources or flagged detections right now.";
    listEl.appendChild(el);
    return;
  }
  if (persistent.length > 0) {
    listEl.appendChild(
      sectionTitle(`Persistent thermal sources (${persistent.length})`),
    );
    for (const feature of persistent) listEl.appendChild(buildEntry(feature));
  }
  if (flagged.length > 0) {
    listEl.appendChild(
      sectionTitle(`Near industrial zones (${flagged.length})`),
    );
    for (const feature of flagged) listEl.appendChild(buildEntry(feature));
  }
  return { persistent: persistent.length, flagged: flagged.length };
}

function renderSitesSidebar(sitesFC) {
  const sites = sitesFC.features || [];
  const meta = sitesFC.meta || {};
  listEl.innerHTML = "";
  if (sites.length === 0) {
    const el = document.createElement("div");
    el.className = "empty";
    el.textContent = "No thermal sites — persistent sources are isolated, or none yet.";
    listEl.appendChild(el);
    return;
  }
  listEl.appendChild(sectionTitle(`Thermal sites (${sites.length})`));
  for (const feature of sites) listEl.appendChild(buildSiteEntry(feature));
  return meta;
}

function showError(message) {
  listEl.innerHTML = "";
  const el = document.createElement("div");
  el.className = "empty";
  el.textContent = message;
  listEl.appendChild(el);
}

function setViewButtons(view) {
  detectionsBtn.classList.toggle("active", view === "detections");
  sitesBtn.classList.toggle("active", view === "sites");
}

function showLayer(layer) {
  layer.addTo(map);
}

function hideLayer(layer) {
  if (map.hasLayer(layer)) map.removeLayer(layer);
}

async function loadDetections(force = false) {
  currentView = "detections";
  setViewButtons("detections");
  hideLayer(siteLayer);
  showLayer(fireLayer);
  summaryEl.textContent = "Fetching live data…";
  try {
    if (force || !cache.firesFC) {
      [cache.firesFC, cache.zonesFC] = await Promise.all([
        fetchJson(FIRES_URL),
        fetchJson(ZONES_URL),
      ]);
    }
    const features = cache.firesFC.features || [];
    renderFireMarkers(features);
    renderZones(cache.zonesFC);
    const counts = renderDetectionsSidebar(features);
    summaryEl.textContent =
      `${features.length} live hotspots · ` +
      `${counts.persistent} persistent thermal sources · ` +
      `${counts.flagged} flagged near industrial zones`;
  } catch (err) {
    console.error(err);
    showError(`Failed to load detections: ${err.message}`);
  }
}

async function loadSites(force = false) {
  currentView = "sites";
  setViewButtons("sites");
  hideLayer(fireLayer);
  summaryEl.textContent = "Clustering persistent sources…";
  try {
    if (force || !cache.sitesFC) {
      cache.sitesFC = await fetchJson(SITES_URL);
      if (cache.zonesFC) renderZones(cache.zonesFC);
    }
    renderSiteMarkers(cache.sitesFC);
    showLayer(siteLayer);
    const meta = renderSitesSidebar(cache.sitesFC);
    const sites = cache.sitesFC.features || [];
    summaryEl.textContent =
      `${sites.length} thermal site(s) from ${(meta && meta.persistent_count) || 0} ` +
      `persistent recurrences (${(meta && meta.unclustered) || 0} isolated)`;
  } catch (err) {
    console.error(err);
    showError(`Failed to load thermal sites: ${err.message}`);
  }
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${url} -> HTTP ${response.status}`);
  }
  return response.json();
}

detectionsBtn.addEventListener("click", () => loadDetections());
sitesBtn.addEventListener("click", () => loadSites());
document.getElementById("reload").addEventListener("click", () => {
  if (currentView === "sites") {
    cache.sitesFC = null;
    loadSites(true);
  } else {
    cache.firesFC = null;
    loadDetections(true);
  }
});

loadDetections();