# SIH26162 — AI-Based Detection of Industrial Fires & Persistent Thermal Sources

Smart India Hackathon 2026 (Software) entry. Uses **live NASA FIRMS satellite
hotspots** + **OpenStreetMap industrial zones** to flag fires near industry and
track **persistent thermal sources**, shown on a Leaflet map dashboard. No custom
ML training — classical geospatial logic + off-the-shelf scikit-learn only.

Tech: Python / FastAPI · Leaflet.js · SQLite · Shapely / GeoPandas · scikit-learn.

## Setup

1. Python 3.11+ required.
2. Install dependencies:

   ```
   python -m venv .venv
   .venv\Scripts\activate        # Windows
   pip install -r requirements.txt
   ```

3. Create `.env` from `.env.example` and set your NASA FIRMS MAP_KEY:
   (register free at https://firms.modaps.eosdis.nasa.gov/)

4. Run:

   ```
   uvicorn app.main:app --reload
   ```

5. Open http://localhost:8000 — API docs at http://localhost:8000/docs

## Endpoints

| Route         | Description                                                    |
| ------------- | -------------------------------------------------------------- |
| `/`           | Map dashboard (placeholder until frontend milestone)           |
| `/api/health` | Liveness check                                                 |
| `/api/fires`  | Live FIRMS hotspots for India bbox → GeoJSON FeatureCollection |

## Tests & lint

```
pytest
ruff check .
ruff format .
```

## Status

Milestones in priority order (see AGENTS.md): FIRMS fetch ✅ · OSM fetch → · spatial
join → · map dashboard → · persistence tracking → · DBSCAN (stretch) → · severity
ranking (stretch).