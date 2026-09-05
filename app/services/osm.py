"""OpenStreetMap industrial zone fetch via the Overpass API.

Queries `landuse=industrial` polygons for a set of regional bboxes (Gujarat,
Jharkhand, Maharashtra — the full-India box is too slow / times out), converts
the Overpass JSON response into a GeoJSON FeatureCollection, and caches the
result to a local file so Overpass is not hit on every request.

The primary mirror at overpass-api.de consistently rejected requests with 406
during development, so queries go straight to the kumi mirror.
"""

import json
import logging
import time
from pathlib import Path

import httpx
from shapely.geometry import Polygon

from ..config import settings

logger = logging.getLogger(__name__)

OVERPASS_URLS = ("https://overpass.kumi.systems/api/interpreter",)

OVERPASS_HEADERS = {"Accept": "application/json"}

OVERPASS_QUERY = (
    "[out:json][timeout:{timeout}];"
    '(way["landuse"="industrial"]({south},{west},{north},{east}););'
    "out body geom;"
)


def parse_state_bbox(bbox: str) -> tuple[float, float, float, float]:
    """Parse a state bbox 'west,south,east,north' into floats."""
    parts = [float(p.strip()) for p in bbox.split(",")]
    if len(parts) != 4 or not all(
        a < b for a, b in ((parts[0], parts[2]), (parts[1], parts[3]))
    ):
        raise ValueError(f"invalid state bbox: {bbox}")
    return parts[0], parts[1], parts[2], parts[3]


def tile_bbox(
    west: float,
    south: float,
    east: float,
    north: float,
    cols: int = 2,
    rows: int = 2,
) -> list[tuple[float, float, float, float]]:
    """Split a bbox into a cols-by-rows grid of smaller tiles.

    Whole-state boxes are too slow for Overpass (timeouts/504s), so queries are
    issued per tile. Tile seams may overlap by chance; results are de-duplicated
    downstream by OSM id.
    """
    tiles: list[tuple[float, float, float, float]] = []
    for col in range(cols):
        for row in range(rows):
            tile_west = west + (east - west) * col / cols
            tile_east = west + (east - west) * (col + 1) / cols
            tile_south = south + (north - south) * row / rows
            tile_north = south + (north - south) * (row + 1) / rows
            tiles.append((tile_west, tile_south, tile_east, tile_north))
    return tiles


def build_query(
    west: float, south: float, east: float, north: float, timeout: int
) -> str:
    """Build the Overpass query. Note Overpass bbox order is south,west,north,east."""
    return OVERPASS_QUERY.format(
        timeout=timeout, south=south, west=west, north=north, east=east
    )


def _way_to_polygon(element: dict) -> Polygon | None:
    points = element.get("geometry")
    if not isinstance(points, list) or len(points) < 4:
        return None
    coords = [(float(p["lon"]), float(p["lat"])) for p in points]
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    polygon = Polygon(coords)
    if polygon.is_valid and not polygon.is_empty:
        return polygon
    return None


def osm_elements_to_featurecollection(elements: list[dict]) -> dict:
    """Convert Overpass `way` elements into a GeoJSON polygon FeatureCollection.

    Only ways with a valid, non-empty polygon geometry are kept; every other
    element type (nodes, relations, degenerate ways) is dropped and logged.
    """
    features = []
    seen_ids = set()
    for element in elements:
        if element.get("type") != "way":
            continue
        osm_id = element.get("id")
        if osm_id is None or osm_id in seen_ids:
            continue
        polygon = _way_to_polygon(element)
        if polygon is None:
            logger.debug("skipping way %s: no valid polygon", osm_id)
            continue
        seen_ids.add(osm_id)
        features.append(
            {
                "type": "Feature",
                "id": f"osm-way-{osm_id}",
                "geometry": polygon.__geo_interface__,
                "properties": {
                    "osm_type": "way",
                    "osm_id": osm_id,
                    "name": element.get("tags", {}).get("name"),
                    "landuse": element.get("tags", {}).get("landuse"),
                    "industrial": element.get("tags", {}).get("industrial"),
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _cache_path() -> Path:
    return Path(settings.industrial_cache_file)


def _cache_is_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    age_seconds = time.time() - path.stat().st_mtime
    fresh = age_seconds < settings.industrial_cache_max_age_hours * 3600
    if fresh:
        logger.info("industrial zones cache is fresh (%.1f h old)", age_seconds / 3600)
    else:
        logger.info("industrial zones cache is stale (%.1f h old)", age_seconds / 3600)
    return fresh


def read_cache() -> dict | None:
    path = _cache_path()
    if not _cache_is_fresh(path):
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("could not read industrial zones cache: %s", exc)
        return None
    return data.get("feature_collection")


def write_cache(feature_collection: dict) -> None:
    payload = {
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "states": list(settings.industrial_states),
        "feature_collection": feature_collection,
    }
    path = _cache_path()
    path.write_text(json.dumps(payload), encoding="utf-8")
    logger.info(
        "cached %s industrial zone features to %s",
        len(feature_collection["features"]),
        path,
    )


async def fetch_region(
    west: float,
    south: float,
    east: float,
    north: float,
    client: httpx.AsyncClient,
    timeout: int,
) -> list[dict]:
    """Query each configured Overpass instance in order, returning first success."""
    query = build_query(west, south, east, north, timeout)
    last_error: Exception | None = None
    for base_url in OVERPASS_URLS:
        try:
            logger.info(
                "querying %s for bbox %s,%s,%s,%s", base_url, west, south, east, north
            )
            response = await client.get(
                base_url,
                params={"data": query},
                headers=OVERPASS_HEADERS,
                timeout=float(timeout),
            )
            response.raise_for_status()
            return response.json().get("elements", [])
        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            last_error = exc
            logger.warning("%s failed (%s) — trying next mirror", base_url, exc)
    raise RuntimeError(
        f"Overpass unavailable for bbox {west},{south},{east},{north}: {last_error}"
    )


async def get_industrial_zones(client: httpx.AsyncClient | None = None) -> dict:
    """Return industrial-zone polygons as a GeoJSON FeatureCollection.

    Serves from a fresh local cache if available; otherwise queries Overpass per
    state, split into tiles, and writes a new cache file. Individual tile
    failures are logged and skipped so a partial dataset still caches and the
    demo keeps working.
    """
    cached = read_cache()
    if cached is not None:
        return cached

    closer = False
    if client is None:
        client = httpx.AsyncClient(timeout=float(settings.overpass_timeout))
        closer = True
    try:
        elements: list[dict] = []
        failures = 0
        for state, bbox in settings.industrial_states.items():
            west, south, east, north = parse_state_bbox(bbox)
            for tile in tile_bbox(west, south, east, north):
                try:
                    tile_elements = await fetch_region(
                        *tile, client, settings.overpass_timeout
                    )
                    elements.extend(tile_elements)
                except RuntimeError as exc:
                    failures += 1
                    logger.error("skipping tile %s of %s after %s", tile, state, exc)
        logger.info(
            "%s industrial ways total, %s tile(s) failed", len(elements), failures
        )
        feature_collection = osm_elements_to_featurecollection(elements)
        write_cache(feature_collection)
        return feature_collection
    finally:
        if closer:
            await client.aclose()
