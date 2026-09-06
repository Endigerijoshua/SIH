"""NASA FIRMS live fire/thermal hotspot fetch.

Uses the NASA FIRMS "area" API (CSV) and converts the response into clean GeoJSON.

Empirical notes (verified while building, keep for anyone touching this):
- The FIRMS WFS bbox filter returns 0 features for any bbox -> unusable for India.
- The unrestricted WFS `fires_snpp_24hrs` layer under-reports India (~16 points on
  2026-09-04) vs the CSV area API (208 points, same box/date) for the India box.
  Hence the CSV area API is the correct source.
- Region for India: `SouthEast_Asia`; India bbox used: `68,6,97,37`.

Reference: https://firms.modaps.eosdis.nasa.gov/api/area/csv
"""

import io
import logging

import httpx
import pandas as pd

from ..config import get_settings

logger = logging.getLogger(__name__)

FIRMS_AREA_URL = (
    "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{dataset}/{bbox}/{days}"
)

# Fields copied verbatim from each FIRMS CSV row onto the GeoJSON feature.
PROPERTY_FIELDS = (
    "confidence",
    "bright_ti4",
    "frp",
    "acq_date",
    "acq_time",
    "satellite",
    "daynight",
)


def parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    """Parse 'west,south,east,north' into floats, validating global bounds."""
    parts = [float(p.strip()) for p in bbox.split(",")]
    if len(parts) != 4:
        raise ValueError(f"bbox must be 'west,south,east,north', got: {bbox}")
    west, south, east, north = parts
    if not (-180 <= west < east <= 180) or not (-90 <= south < north <= 90):
        raise ValueError(f"invalid bbox: {bbox}")
    return west, south, east, north


def build_url(api_key: str, dataset: str, bbox: str, days: int) -> str:
    if not api_key:
        raise ValueError("FIRMS_MAP_KEY is not set. Add it to .env (see .env.example).")
    parsed = parse_bbox(bbox)
    bbox_comma = ",".join(str(v) for v in parsed)
    return FIRMS_AREA_URL.format(
        key=api_key, dataset=dataset, bbox=bbox_comma, days=days
    )


def _json_value(value):
    """Convert a pandas/numpy scalar into a plain JSON-safe Python value."""
    if value is None:
        return None
    if pd.isna(value):
        return None
    if isinstance(value, (str, bool)):
        return value
    if hasattr(value, "item"):
        return value.item()
    return value


def csv_to_geojson(csv_text: str) -> dict:
    """Convert FIRMS area-API CSV text into a GeoJSON FeatureCollection.

    Logs the input row count vs. produced feature count so any dropped
    detection is never silent.
    """
    df = pd.read_csv(io.StringIO(csv_text))
    total_rows = len(df)

    features = []
    dropped = 0
    for _, row in df.iterrows():
        lon, lat = row["longitude"], row["latitude"]
        if pd.isna(lon) or pd.isna(lat):
            dropped += 1
            continue
        props = {field: _json_value(row[field]) for field in PROPERTY_FIELDS}
        features.append(
            {
                "type": "Feature",
                "id": len(features),
                "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
                "properties": props,
            }
        )

    if dropped:
        logger.warning(
            "FIRMS CSV->GeoJSON dropped %s of %s rows (missing coordinates)",
            dropped,
            total_rows,
        )
    logger.info(
        "FIRMS CSV -> GeoJSON: %s rows parsed, %s features produced",
        total_rows,
        len(features),
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
    cfg = get_settings()
    api_key = api_key or cfg.firms_map_key
    dataset = dataset or cfg.firms_dataset
    bbox = bbox or cfg.firms_bbox
    days = days or cfg.firms_days

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
