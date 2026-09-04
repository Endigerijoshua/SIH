"""NASA FIRMS live fire/thermal hotspot fetch.

Uses the FIRMS CSV "area" API (verified working with bbox) and converts the
response into clean GeoJSON for the rest of the app. The WFS bbox variant is
broken (returns 0 features for any bbox) so we do not use it here.

Reference: https://firms.modaps.eosdis.nasa.gov/api/area/csv
"""

import csv
import io
import logging

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

FIRMS_AREA_URL = (
    "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{dataset}/{bbox}/{days}"
)

# FIRMS confidence codes (1-char) -> friendly label
CONFIDENCE_LABELS = {"l": "low", "n": "nominal", "h": "high"}

CSV_FLOAT_FIELDS = (
    "latitude",
    "longitude",
    "bright_ti4",
    "scan",
    "track",
    "bright_ti5",
    "frp",
)


def parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    """Parse 'minLon,minLat,maxLon,maxLat' into floats, validating India bounds."""
    parts = [float(p.strip()) for p in bbox.split(",")]
    if len(parts) != 4:
        raise ValueError(f"bbox must be 'minLon,minLat,maxLon,maxLat', got: {bbox}")
    min_lon, min_lat, max_lon, max_lat = parts
    if not (-180 <= min_lon < max_lon <= 180) or not (-90 <= min_lat < max_lat <= 90):
        raise ValueError(f"invalid bbox: {bbox}")
    return min_lon, min_lat, max_lon, max_lat


def build_url(api_key: str, dataset: str, bbox: str, days: int) -> str:
    if not api_key:
        raise ValueError("FIRMS_MAP_KEY is not set. Add it to .env (see .env.example).")
    parsed = parse_bbox(bbox)
    bbox_comma = ",".join(str(v) for v in parsed)
    return FIRMS_AREA_URL.format(
        key=api_key, dataset=dataset, bbox=bbox_comma, days=days
    )


def _normalize_props(raw: dict) -> dict:
    props = {
        "latitude": float(raw["latitude"]),
        "longitude": float(raw["longitude"]),
        "confidence": CONFIDENCE_LABELS.get(raw["confidence"], raw["confidence"]),
        "brightness": float(raw["bright_ti4"]) if raw.get("bright_ti4") else None,
        "frp": float(raw["frp"]) if raw.get("frp") else None,
        "acq_date": raw.get("acq_date", ""),
        "acq_time": raw.get("acq_time", "").zfill(4),
        "satellite": raw.get("satellite", ""),
        "instrument": raw.get("instrument", ""),
        "daynight": raw.get("daynight", ""),
        "source": "nasa_firms",
    }
    return props


def csv_to_geojson(csv_text: str) -> dict:
    """Convert FIRMS area-API CSV text into a GeoJSON FeatureCollection."""
    features = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for i, row in enumerate(reader):
        if not row.get("longitude"):
            continue
        props = _normalize_props(row)
        features.append(
            {
                "type": "Feature",
                "id": i,
                "geometry": {
                    "type": "Point",
                    "coordinates": [props["longitude"], props["latitude"]],
                },
                "properties": {k: v for k, v in props.items()},
            }
        )
    return {"type": "FeatureCollection", "features": features}


async def fetch_fires(
    api_key: str | None = None,
    dataset: str | None = None,
    bbox: str | None = None,
    days: int | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict:
    """Fetch live FIRMS hotspot detections for the configured India bbox.

    Returns a GeoJSON FeatureCollection. Raises ValueError on missing key,
    httpx.HTTPStatusError on a non-200 response, and httpx.RequestError on
    network failures.
    """
    api_key = api_key or settings.firms_map_key
    dataset = dataset or settings.firms_dataset
    bbox = bbox or settings.firms_bbox
    days = days or settings.firms_days

    url = build_url(api_key, dataset, bbox, days)
    logger.info("fetching FIRMS CSV: %s", url)

    closer = False
    if client is None:
        client = httpx.AsyncClient(timeout=60.0)
        closer = True
    try:
        response = await client.get(url)
        response.raise_for_status()
        return csv_to_geojson(response.text)
    finally:
        if closer:
            await client.aclose()
