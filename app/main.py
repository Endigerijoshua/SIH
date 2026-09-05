"""SIH26162 — Industrial fire detection via NASA FIRMS + OSM satellite data.

FastAPI app entry point. Serves the Leaflet dashboard (static) and the API
endpoints that fetch + enrich live fire data.
"""

import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .services import clustering, firms, osm, persistence, spatial

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
    fires_fc = await firms.fetch_fires(days=days)
    db.record_featurecollection(fires_fc)
    return fires_fc


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


@app.get("/api/flagged-fires")
async def get_flagged_fires(days: int | None = None) -> dict:
    """Live fires annotated with fire type + industrial/persistence metadata."""
    fires_fc = await firms.fetch_fires(days=days)
    db.record_featurecollection(fires_fc)
    industrial_fc, vegetation_fc = await _osm_layers()
    spatial.annotate_fires(fires_fc, industrial_fc, vegetation_fc)
    persistence.annotate_persistence(fires_fc)
    return fires_fc


async def _osm_layers() -> tuple[dict, dict]:
    """Fetch industrial + vegetation zone layers in parallel."""
    industrial_fc, vegetation_fc = await asyncio.gather(
        osm.get_industrial_zones(), osm.get_vegetation_zones()
    )
    return industrial_fc, vegetation_fc


@app.get("/api/thermal-sites")
async def get_thermal_sites(days: int | None = None) -> dict:
    """DBSCAN-cluster persistent recurrences into named industrial sites."""
    fires_fc = await firms.fetch_fires(days=days)
    db.record_featurecollection(fires_fc)
    industrial_fc, vegetation_fc = await _osm_layers()
    spatial.annotate_fires(fires_fc, industrial_fc, vegetation_fc)
    persistence.annotate_persistence(fires_fc)
    return clustering.cluster_persistent_fires(fires_fc, industrial_fc)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
