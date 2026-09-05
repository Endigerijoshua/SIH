"""Spatial join: label each FIRMS fire point by proximity to OSM zones.

Pure Shapely logic — no model training. Each fire gets a single `fire_type`:
- "industrial"    — within 1 km of an industrial-zone polygon (checked first;
                    industrial is the higher-value signal for this problem)
- "forest"        — not industrial, but within 1 km of a forest/vegetation polygon
- "other_natural" — not near either layer (e.g. agricultural burning, grassland)

Backward-compatible fields are kept: `near_industrial` + `distance_m` (distance in
meters to the nearest industrial polygon, None when nothing is within 20 km),
plus `near_vegetation` + `vegetation_distance_m`.

Distances are measured with a per-fire UTM transverse-Mercator projection, so
meter values stay meaningful regardless of longitude (raw lon/lat degrees are
not linear in meters).

All geometries are (lon, lat) order, matching both FIRMS GeoJSON and our OSM
conversion.
"""

import logging

import pyproj
from shapely.errors import GEOSException
from shapely.geometry import shape
from shapely.ops import transform
from shapely.strtree import STRtree

logger = logging.getLogger(__name__)

NEAR_BUFFER_METERS = 1000
SEARCH_RADIUS_METERS = 20000
_SEARCH_PAD_DEGREES = 0.3


def _utm_epsg_for_longitude(lon: float) -> int:
    """Pick a UTM zone EPSG code (northern hemisphere) for a longitude."""
    zone = int((lon + 180) // 6) + 1
    return 32600 + zone


def _utm_distance_meters(point, polygon: "object") -> float:
    """Project both geometries to the point's UTM zone and measure meters."""
    transformer = pyproj.Transformer.from_crs(
        "EPSG:4326", _utm_epsg_for_longitude(point.x), always_xy=True
    )
    projected_point = transform(transformer.transform, point)
    projected_polygon = transform(transformer.transform, polygon)
    return float(projected_polygon.distance(projected_point))


def _nearest_distance_meters(point, polygons: list) -> float | None:
    """Nearest distance (meters) from point to any polygon, or None if too far."""
    if not polygons:
        return None
    tree = STRtree(polygons)
    candidates_index = tree.query(point.buffer(_SEARCH_PAD_DEGREES))
    candidates = [polygons[i] for i in candidates_index]
    if not candidates:
        return None
    nearest = min(_utm_distance_meters(point, poly) for poly in candidates)
    return nearest if nearest <= SEARCH_RADIUS_METERS else None


def nearest_zone_info(
    point, industrial_fc: dict, search_meters: int = SEARCH_RADIUS_METERS
) -> dict | None:
    """Nearest industrial-zone feature name, osm id, and distance.

    Returns None when no industrial polygon is within `search_meters`. Used by
    the clustering service to name recurring-fire "sites" after the industrial
    zone they sit next to.
    """
    features = industrial_fc["features"]
    if not features:
        return None
    polygons = [shape(feature["geometry"]) for feature in features]
    tree = STRtree(polygons)
    candidates_index = tree.query(point.buffer(_SEARCH_PAD_DEGREES))
    candidates = [(features[i], polygons[i]) for i in candidates_index]
    if not candidates:
        return None
    feature, poly = min(
        candidates,
        key=lambda fp: _utm_distance_meters(point, fp[1]),
    )
    distance_m = _utm_distance_meters(point, poly)
    if distance_m > search_meters:
        return None
    props = feature["properties"] or {}
    return {
        "name": props.get("name"),
        "osm_id": props.get("osm_id"),
        "distance_m": round(distance_m, 1),
    }


def _extract_point(feature: dict):
    """Return the feature's Point geometry, or None if it is unusable."""
    try:
        point = shape(feature["geometry"])
    except (GEOSException, TypeError, ValueError):
        logger.warning("skipping malformed fire feature %s", feature.get("id"))
        return None
    if point.is_empty or point.geom_type != "Point":
        return None
    return point


def annotate_fires(
    fires_fc: dict, industrial_fc: dict, vegetation_fc: dict | None = None
) -> dict:
    """Add fire type + proximity flags to every fire feature.

    Mutates and returns the input FeatureCollection (fires_fc). Classification
    priority: industrial first, then forest, else other_natural.
    """
    industrial_polygons = [
        shape(feature["geometry"]) for feature in industrial_fc["features"]
    ]
    vegetation_fc = vegetation_fc or {"type": "FeatureCollection", "features": []}
    vegetation_polygons = [
        shape(feature["geometry"]) for feature in vegetation_fc["features"]
    ]

    for feature in fires_fc["features"]:
        prop = feature["properties"]
        prop["near_industrial"] = False
        prop["distance_m"] = None
        prop["near_vegetation"] = False
        prop["vegetation_distance_m"] = None
        prop["fire_type"] = "other_natural"

        point = _extract_point(feature)
        if point is None:
            continue

        industrial_distance = _nearest_distance_meters(point, industrial_polygons)
        if industrial_distance is not None:
            prop["distance_m"] = round(industrial_distance, 1)
            if industrial_distance <= NEAR_BUFFER_METERS:
                prop["near_industrial"] = True
                prop["fire_type"] = "industrial"

        vegetation_distance = _nearest_distance_meters(point, vegetation_polygons)
        if vegetation_distance is not None:
            prop["vegetation_distance_m"] = round(vegetation_distance, 1)
            if vegetation_distance <= NEAR_BUFFER_METERS:
                prop["near_vegetation"] = True
                if prop["fire_type"] == "other_natural":
                    prop["fire_type"] = "forest"

    return fires_fc
