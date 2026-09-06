"""SIH26162 — Industrial fire detection via NASA FIRMS + OSM satellite data.

FastAPI app entry point. Serves the Leaflet dashboard (static) and the API
endpoints that fetch + enrich live fire data.
"""

import asyncio
import logging
from pathlib import Path

# pyrefly: ignore [missing-import]
import httpx

# pyrefly: ignore [missing-import]
from fastapi import FastAPI, HTTPException

# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware

# pyrefly: ignore [missing-import]
from fastapi.responses import FileResponse, HTMLResponse

# pyrefly: ignore [missing-import]
from fastapi.staticfiles import StaticFiles

from . import db
from .services import (
    clustering,
    firms,
    ml,
    osm,
    persistence,
    powerplants,
    spatial,
    summary,
)

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="SIH26162 Industrial Fire Detection",
    description="Live industrial fire + persistent thermal source detection using NASA FIRMS and OSM.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


PLACEHOLDER_INDEX = """<!doctype html>
<html><head><meta charset="utf-8"><title>SIH26162</title></head>
<body><h1>SIH26162 — Industrial Fire Detection</h1>
<p>Backend is running. Frontend map is coming in a later milestone.</p>
<p>Try <a href="/api/fires">/api/fires</a> for live NASA FIRMS hotspots (GeoJSON).</p>
</body></html>"""


@app.get("/", response_class=HTMLResponse)
async def index():
    path = STATIC_DIR / "index.html"
    if path.exists():
        return FileResponse(path)
    return PLACEHOLDER_INDEX


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/fires")
async def get_fires(days: int | None = None) -> dict:
    """Fetch live FIRMS hotspots (India bbox) and return clean GeoJSON.

    `days` overrides the FIRMS lookback window (default from settings/.env).
    Every returned detection is also appended to the local SQLite fire_history.
    """
    try:
        fires_fc = await firms.fetch_fires(days=days)
        db.record_featurecollection(fires_fc)
        return fires_fc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (httpx.HTTPError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=f"NASA FIRMS API error: {exc}") from exc


@app.get("/api/industrial-zones")
async def get_industrial_zones() -> dict:
    """Fetch or serve cached OSM industrial-zone polygons as GeoJSON."""
    try:
        return await osm.get_industrial_zones()
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/vegetation-zones")
async def get_vegetation_zones() -> dict:
    """Fetch or serve cached OSM forest/vegetation polygons as GeoJSON."""
    try:
        return await osm.get_vegetation_zones()
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/power-plants")
async def get_power_plants() -> dict:
    """India power plants (WRI Global Power Plant Database) as point GeoJSON."""
    try:
        return await powerplants.get_power_plants()
    except (RuntimeError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/flagged-fires")
async def get_flagged_fires(days: int | None = None) -> dict:
    """Live fires annotated with rule-based + ML fire type and persistence."""
    try:
        fires_fc = await firms.fetch_fires(days=days)
        db.record_featurecollection(fires_fc)
        industrial_fc, vegetation_fc, power_plants_fc = await _reference_layers()
        spatial.annotate_fires(fires_fc, industrial_fc, vegetation_fc, power_plants_fc)
        persistence.annotate_persistence(fires_fc)
        ml.annotate_fire_type_ml(fires_fc)
        summary.add_summary(fires_fc)
        return fires_fc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (httpx.HTTPError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=f"Upstream API error: {exc}") from exc


async def _reference_layers() -> tuple[dict, dict, dict]:
    """Fetch industrial + vegetation zones and power plants in parallel."""
    industrial_fc, vegetation_fc, power_plants_fc = await asyncio.gather(
        osm.get_industrial_zones(),
        osm.get_vegetation_zones(),
        powerplants.get_power_plants(),
    )
    return industrial_fc, vegetation_fc, power_plants_fc


@app.get("/api/thermal-sites")
async def get_thermal_sites(days: int | None = None) -> dict:
    """DBSCAN-cluster persistent recurrences into named industrial sites."""
    try:
        fires_fc = await firms.fetch_fires(days=days)
        db.record_featurecollection(fires_fc)
        industrial_fc, vegetation_fc, power_plants_fc = await _reference_layers()
        spatial.annotate_fires(fires_fc, industrial_fc, vegetation_fc, power_plants_fc)
        persistence.annotate_persistence(fires_fc)
        ml.annotate_fire_type_ml(fires_fc)
        return clustering.cluster_persistent_fires(fires_fc, industrial_fc)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (httpx.HTTPError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=f"Upstream API error: {exc}") from exc


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
