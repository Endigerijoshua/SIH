/* SIH26162 — Leaflet dashboard: FIRMS fire points × OSM industrial zones ×
   WRI power plants, with NASA GIBS satellite imagery as a toggleable base layer
   and a switch between individual detections and clustered thermal sites. */
"use strict";

const FIRES_URL = "/api/flagged-fires";
const ZONES_URL = "/api/industrial-zones";
const SITES_URL = "/api/thermal-sites";
const POWER_PLANTS_URL = "/api/power-plants";

const CONFIDENCE_COLORS = {
  h: "#d7191c",
  n: "#fd8d3c",
  l: "#ffd700",
};
const CONFIDENCE_LABELS = { h: "high", n: "nominal", l: "low" };

const SITE_COLOR = "#7a2ea0";
const POWER_PLANT_COLOR = "#6a5acd";

// GIBS WAITS ~1 day to publish true-color; use yesterday so tiles always exist.
const GIBS_DATE = new Date(Date.now() - 24 * 3600 * 1000)
  .toISOString()
  .slice(0, 10);
const GIBS_BASE_URL =
  "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/{layer}/default/" +
  GIBS_DATE +
  "/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg";

const map = L.map("map").setView([22, 79], 5);

const osmTile = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "&copy; OpenStreetMap contributors",
  maxZoom: 18,
}).addTo(map);

const gibsMODIS = L.tileLayer(
  GIBS_BASE_URL.replace(
    "{layer}",
    "MODIS_Terra_CorrectedReflectance_TrueColor",
  ),
  { maxNativeZoom: 9, maxZoom: 18, attribution: "Imagery &copy; NASA GIBS" },
);
const gibsVIIRS = L.tileLayer(
  GIBS_BASE_URL.replace("{layer}", "VIIRS_SNPP_CorrectedReflectance_TrueColor"),
  { maxNativeZoom: 9, maxZoom: 18, attribution: "Imagery &copy; NASA GIBS" },
);

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

const powerPlantLayer = L.geoJSON(null, {
  pointToLayer: (feature, latlng) =>
    L.circleMarker(latlng, {
      radius: 4,
      color: "#1a1433",
      weight: 1,
      fillColor: POWER_PLANT_COLOR,
      fillOpacity: 0.8,
    }),
  onEachFeature: (feature, layer) => {
    const props = feature.properties || {};
    const rows = [
      ["Plant", props.name || "—"],
      ["Capacity", props.capacity_mw != null ? `${props.capacity_mw} MW` : "—"],
      ["Fuel", props.primary_fuel || "—"],
      ["Source", props.source || "—"],
    ];
    layer.bindPopup(rows.map(([k, v]) => `<b>${k}:</b> ${v}`).join("<br>"));
  },
}).addTo(map);

L.control
  .layers(
    {
      OpenStreetMap: osmTile,
      "NASA GIBS true-color (MODIS)": gibsMODIS,
      "NASA GIBS true-color (VIIRS)": gibsVIIRS,
    },
    {
      "Industrial zones (OSM)": zoneLayer,
      "Power plants (WRI)": powerPlantLayer,
    },
    { collapsed: false, position: "topright" },
  )
  .addTo(map);

const fireMarkers = new Map();
const fireLayer = L.layerGroup().addTo(map);
const siteLayer = L.layerGroup();

const SITE_LAYER_ID = "siteLayer";
const FIRE_LAYER_ID = "fireLayer";

const listEl = document.getElementById("list");
const summaryEl = document.getElementById("summary");
const detectionsBtn = document.getElementById("view-detections");
const sitesBtn = document.getElementById("view-sites");

const cache = { firesFC: null, zonesFC: null, sitesFC: null, powerFC: null };
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

function fireKvHtml(props) {
  const rows = [
    ["Confidence", confidenceLabel(props.confidence)],
    ["Brightness", props.bright_ti4 != null ? `${props.bright_ti4} K` : "—"],
    ["FRP", props.frp != null ? `${props.frp} MW` : "—"],
    ["Observed", formatTime(props.acq_date, props.acq_time)],
    ["Satellite", props.satellite || "—"],
    ["Day/night", props.daynight || "—"],
    ["Nearest industrial", formatDistance(props.distance_m)],
    ["Match source", props.industrial_match_source || "—"],
  ];
  if (props.near_power_plant) {
    rows.push(["Power plant", props.power_plant_name || "—"]);
    rows.push(["Plant distance", formatDistance(props.power_plant_distance_m)]);
  }
  if (props.fire_type_ml) rows.push(["ML type", props.fire_type_ml]);
  if (props.fire_type_ml_confidence != null) {
    rows.push(["ML confidence", Number(props.fire_type_ml_confidence).toFixed(2)]);
  }
  if (props.persistent_thermal_source) {
    rows.push(["Occurrences", `${props.occurrence_count} days / 14`]);
  }
  return rows.map(([k, v]) => `<div><b>${k}:</b> ${v}</div>`).join("");
}

function fireVerdictHtml(props) {
  const icon = props.summary_icon || "\u{1F525}";
  const headline = props.summary_headline || "Fire";
  const detail = props.summary_detail ? `<div class="detail">${props.summary_detail}</div>` : "";
  const persistent = props.summary_persistent
    ? `<div class="persist">${props.summary_persistent}</div>`
    : "";
  const reason = props.explanation
    ? `<div class="reason">${props.explanation}</div>`
    : "";
  return (
    `<div class="verdict"><span class="icon">${icon}</span>${headline}</div>` +
    detail +
    persistent +
    reason +
    `<details><summary>Details</summary><div class="kv">${fireKvHtml(props)}</div></details>`
  );
}

function firePopupContent(prop) {
  return `<div class="fb">${fireVerdictHtml(prop)}</div>`;
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

function renderPowerPlants(featureCollection) {
  powerPlantLayer.clearLayers();
  powerPlantLayer.addData(featureCollection);
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
  entry.insertAdjacentHTML("beforeend", fireVerdictHtml(props));

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
      [cache.firesFC, cache.zonesFC, cache.powerFC] = await Promise.all([
        fetchJson(FIRES_URL),
        fetchJson(ZONES_URL),
        fetchJson(POWER_PLANTS_URL),
      ]);
    }
    const features = cache.firesFC.features || [];
    renderFireMarkers(features);
    renderZones(cache.zonesFC);
    renderPowerPlants(cache.powerFC);
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
    let detail = "";
    try {
      const data = await response.json();
      if (data && data.detail) {
        detail = `: ${data.detail}`;
      }
    } catch {
      // Not JSON or empty body
    }
    throw new Error(`${url} -> HTTP ${response.status}${detail}`);
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