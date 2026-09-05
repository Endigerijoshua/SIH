# AGENTS.md — SIH26162 Industrial Fire Detection

Instructions for AI coding assistants working on this repo. Read this fully before
writing any code. When in doubt, prioritize the constraints in [NON-NEGOTIABLE RULES](#non-negotiable-rules).

## Project Overview

Smart India Hackathon 2026 (Software Edition) project. Problem ID **SIH26162** —
*"AI-Based Detection and Classification of Industrial Fires and Persistent Thermal
Sources Using NASA FIRMS, OSM & Satellite Data"*. Theme: Disaster Management.
Org: **NTRO**. Deadline: **30 September 2026**.

Goal: detect fire/thermal hotspots near industrial zones in India from **live NASA
FIRMS satellite data**, classify one-off fires vs. recurring **persistent thermal
sources**, rank by severity, and render everything on a live map dashboard
(Leaflet.js).

## Team Context (shapes ALL decisions)

- Beginner "vibecoder" BCA students. Heavy reliance on AI coding assistants. No deep
  ML / data-science background.
- Deliberate approach: **ZERO model training**. No custom ML/CV, no labeled datasets,
  no GPU. Every capability is built from free off-the-shelf APIs + classical geospatial
  logic + out-of-the-box algorithms (e.g. scikit-learn DBSCAN used as-is, never fitted
  on our own data).
- Priority order: (1) must run end-to-end and demo live, (2) must look technically
  credible to judges, (3) must stay debuggable by beginners.

## Tech Stack

| Layer      | Choice                                              | Why                                            |
| ---------- | --------------------------------------------------- | ---------------------------------------------- |
| Backend    | Python 3.11+ / FastAPI                              | Best geospatial lib support; simple async API  |
| Frontend   | Leaflet.js (plain JS)                               | Renders GeoJSON layers with minimal glue code  |
| Database   | SQLite (built-in `sqlite3` / SQLAlchemy)            | Zero setup. PostGIS upgrade only if bottleneck |
| GIS        | Shapely + GeoPandas                                 | Point-in-polygon, buffering, nearest-distance  |
| ML (naive) | scikit-learn DBSCAN (off-the-shelf, NOT trained)    | Groups recurring hotspots into "sites"         |

## Data Sources

### 1) NASA FIRMS (fire/thermal hotspots)
- `MAP_KEY` obtained (in `.env`, gitignored). ✅
- **PRIMARY SOURCE = CSV area API** (empirically verified — the WFS bbox filter returns
  0 features for every bbox tested, but the CSV area API respects the bbox correctly).
  Endpoint:
  ```
  https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{DATASET}/{bbox}/1
  ```
  - `DATASET` for VIIRS: `VIIRS_SNPP_NRT` (also `MODIS_NRT`, `VIIRS_NOAA20_NRT`,
    `VIIRS_NOAA21_NRT`).
  - `bbox` format: `west,south,east,north` (decimal, no CRS) — i.e. `68,6,97,37` for India.
  - The `/1` is the day-lookback window (1 = last 24h).
- Backend converts CSV → clean GeoJSON in `app/services/firms.py` using **pandas**
  (fields kept verbatim: `confidence`, `bright_ti4`, `frp`, `acq_date`, `acq_time`,
  `satellite`, `daynight`).
- Region coverage: `SouthEast_Asia` service includes India. India bbox used:
  `68,6,97,37` (verified — 208 live VIIRS fires returned on 2026-09-04).
- Refresh: ~15 min. Rate limit: 5,000 req / 10 min — safe to poll live during demo.
- CSV columns of interest: `latitude`, `longitude`, `confidence`
  (l/n/h = low/nominal/high), `bright_ti4` (brightness), `frp` (Fire Radiative Power;
  higher = more severe), `acq_date`, `acq_time`, `satellite`, `instrument`, `daynight`.
- WFS fallback (Do NOT use for bbox queries — bbox param returns 0): WFS works
  un-bounded, e.g.
  `https://firms.modaps.eosdis.nasa.gov/mapserver/wfs/SouthEast_Asia/{MAP_KEY}/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAME=ms:fires_snpp_24hrs&outputformat=geojson`
  Valid TYPENAMEs (from GetCapabilities): `ms:fires_snpp_24hrs`, `ms:fires_modis_24hrs`,
  `ms:fires_noaa20_24hrs`, `ms:fires_noaa21_24hrs` (+ `_7days`, `ms:fires_landsat_24hrs`).

### 2) OSM via Overpass API (industrial zones)
- Free, no API key.
- Industrial land-use: `way["landuse"="industrial"]`; named facilities: also pull
  `way["industrial"="*"]` / `building="industrial"` where relevant.
- Query pattern: `[out:json];(way["landuse"="industrial"](bbox););out body geom;`

## Architecture / Core Logic ("the AI")

1. **Spatial join**: for each FIRMS point, check if inside a 500m–1km buffer of an OSM
   industrial polygon (Shapely `within` / `distance` + GeoPandas sjoin). This alone
   separates *industrial fire* from *random/forest fire*.
2. **Persistence detection**: store each detection (SQLite) keyed by location+time;
   if a hotspot repeats at/near the same coordinates across days/weeks, flag it as a
   **"persistent thermal source"** (term is literally in the SIH title) — e.g.
   `"🔴 Persistent thermal source — Nth occurrence in X days"`.
3. **Severity scoring (rule-based, no training)**:
   - `confidence` (low/nominal/high)
   - `brightness` / `frp` (higher = more severe)
   - recurrence count (more occurrences = higher persistence severity)
4. **Optional stretch — DBSCAN**: cluster repeated hotspot coordinates over time into
   auto-named "sites" (out-of-the-box sklearn, `fit` on historical coords only).

## MVP Feature Scope (build top→bottom; each must work before next)

- [ ] 1. Backend endpoint: fetch live FIRMS data (India bbox) → clean GeoJSON — **✅ API-level done; see status section**
- [ ] 2. Backend endpoint: fetch OSM industrial polygons (same area)
- [ ] 3. Spatial join: label fire as "near industrial" + distance to nearest zone
- [ ] 4. Frontend map: fire points (color by confidence/severity) + industrial polygon
       layer, sidebar listing flagged detections
- [ ] 5. Persistence tracking: daily detections in DB, recurrence detection, persistent
       thermal source surfacing
- [ ] 6. (Stretch) DBSCAN clustering → named "sites"
- [ ] 7. (Stretch) Severity ranking / dashboard sort by risk score

## Non-Negotiable Rules

- **NO custom ML/CV model training. Ever.** No labeled data, no training loops, no GPU.
  Allowed: off-the-shelf pretrained/classical algorithms (sklearn DBSCAN) used as-is.
- **NO raw satellite raster processing** (Sentinel/Landsat imagery). FIRMS already
  pre-processes hotspots; that is the whole point.
- **No training pipeline files** in the repo (no `train.py`, no model checkpoints).
- Keep the DB simple: **SQLite first**. Do not add PostGIS/PostgreSQL unless SQLite is
  proven to be the bottleneck.
- Every dependency change must be justified and recorded in `requirements.txt` (pinned)
  or `pyproject.toml`.

## Repository Layout (adopt as scaffolding)

```
sih-fire-detection/
├── AGENTS.md
├── README.md                 # quickstart, setup steps, how to demo
├── requirements.txt          # pinned
├── .env.example              # MAP_KEY etc. (never commit real keys)
├── app/
│   ├── main.py               # FastAPI app entry, CORS, routes
│   ├── config.py             # env config (MAP_KEY, bbox, thresholds)
│   ├── services/
│   │   ├── firms.py          # FIRMS CSV area API fetch → clean GeoJSON
│   │   ├── osm.py            # Overpass industrial zones fetch
│   │   ├── spatial.py        # sjoin / buffering / nearest-distance
│   │   ├── persistence.py    # recurrence detection & severity scoring
│   │   └── clustering.py     # (stretch) DBSCAN site grouping
│   ├── db.py                 # SQLite schema + access helpers
│   └── models.py             # Pydantic schemas / dataclasses
├── static/
│   └── index.html + app.js   # Leaflet map + sidebar
└── tests/
```

## Commands (verify/adjust during setup)

- Install: `pip install -r requirements.txt`
- Run: `uvicorn app.main:app --reload` (default http://localhost:8000)
- Map: open `http://localhost:8000/` in a browser
- Lint/format: `ruff check .` and `ruff format .` (add ruff to requirements)
- Tests: `pytest`

## Coding Conventions

- Python 3.11+, type hints on all signatures.
- All external API calls via `httpx` (async) where possible; timeouts always set.
- GeoJSON flows through the app as source of truth: FIRMS → GeoJSON, backend enriches →
  GeoJSON, Leaflet renders GeoJSON.
- Clearly separate code that must be debuggable by beginners (keep pure logic functions
  small, one responsibility each).
- Never log or commit API keys. Use `.env` + `python-dotenv`; commit only `.env.example`.
- Comments in code are fine but keep code self-explanatory first.

## Known Gaps / Things to Confirm During Setup

1. ~~FIRMS MAP_KEY~~ — **done**, in `.env` (`FIRMS_MAP_KEY`).
2. **FIRMS region + bbox** — **done**: use `api/area/csv` with bbox `68,6,97,37`
   (verified 208 live VIIRS India fires on 2026-09-04). WFS bbox filter is broken
   (returns 0); do not rely on it for bbox queries.
3. **Overpass query working set** — confirm tag choice (`landuse=industrial`) returns
   sensible polygons for India; tune bbox size for response limits.
4. **DBSCAN** — decide `eps`/`min_samples` sensible for kilometer-scale coordinates.

## Definition of Done

- `uvicorn app.main:app` starts cleanly.
- FIRMS endpoint returns non-empty GeoJSON for the India bbox.
- OSM endpoint returns industrial polygons.
- Map renders both layers; fire points color-coded, sidebar populated.
- Persistence endpoint reports recurrence counts / persistent sources over the demo DB.
- `pytest` passes; `ruff` clean.

## Current Status (keep updated)

- [x] FIRMS MAP_KEY obtained (stored in `.env`)
- [x] Confirmed FIRMS region name / bbox for India (`api/area/csv`, bbox `68,6,97,37`)
- [x] Backend scaffold created (FastAPI project structure)
- [x] FIRMS fetch endpoint working (`GET /api/fires`, default `FIRMS_DAYS=3` —
       lookback configurable via `?days= N` too)
- [x] OSM Overpass fetch working (tiled state bboxes, 24h file cache, kumi mirror)
- [x] Spatial join logic working (UTM-projected nearest-distance; 1 km near flag)
- [x] Frontend map rendering both layers (Leaflet; fires color-coded, zones translucent,
       sidebar with flagged + persistent sections)
- [x] Persistence tracking implemented (`fire_history` SQLite table accumulates every
       detection on `/api/fires` and `/api/flagged-fires`; flags `persistent_thermal_source`
       for 2+ distinct days within 300 m in last 14 days, with `occurrence_count`; 22 tests, ruff clean)
- [ ] DBSCAN clustering (stretch)
- [ ] Deployed somewhere accessible for demo