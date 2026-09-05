"""Spatial join: label each FIRMS fire point by proximity to OSM industrial zones.

Pure Shapely logic — no model training. A fire is flagged `near_industrial` when
it lies within 1 km of any industrial-zone polygon. `distance_m` reports the
distance in meters to the nearest polygon (None when nothing is within 20 km).

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
    tree = STRtree(polygons)
    candidates_index = tree.query(point.buffer(_SEARCH_PAD_DEGREES))
    candidates = [polygons[i] for i in candidates_index]
    if not candidates:
        return None
    nearest = min(_utm_distance_meters(point, poly) for poly in candidates)
    return nearest if nearest <= SEARCH_RADIUS_METERS else None


def annotate_fires(fires_fc: dict, industrial_fc: dict) -> dict:
    """Add `near_industrial` and `distance_m` to every fire feature.

    Mutates and returns the input FeatureCollection (fires_fc).
    """
    polygons = [shape(feature["geometry"]) for feature in industrial_fc["features"]]

    for feature in fires_fc["features"]:
        prop = feature["properties"]
        prop["near_industrial"] = False
        prop["distance_m"] = None
        try:
            point = shape(feature["geometry"])
        except (GEOSException, TypeError, ValueError):
            logger.warning("skipping malformed fire feature %s", feature.get("id"))
            continue
        if point.is_empty or point.geom_type != "Point":
            continue
        distance_m = _nearest_distance_meters(point, polygons)
        if distance_m is None:
            continue
        prop["distance_m"] = round(distance_m, 1)
        if distance_m <= NEAR_BUFFER_METERS:
            prop["near_industrial"] = True

    return fires_fc
