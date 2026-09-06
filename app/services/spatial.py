"""Spatial join: label each FIRMS fire point by proximity to OSM zones + power plants.

Pure Shapely logic — no model training. Each fire gets a rule-based
`fire_type_rule` field:
- "industrial"    — within 1 km of an OSM industrial-zone polygon OR a known
                    power plant (WRI Global Power Plant Database point); checked
                    first (industrial is the higher-value signal for this problem)
- "forest"        — not industrial, but within 3 km of a forest/vegetation polygon
- "other_natural" — not near either layer (e.g. agricultural burning, grassland)

The industrial match source is recorded per fire (`industrial_match_source`):
"osm", "power_plant_db", or "both" — so the dashboard can show that we fuse a
curated infrastructure database with open map data, not OSM alone.

Backward-compatible fields are kept: `near_industrial` + `distance_m` (meters to
the NO NEAREST industrial feature — OSM polygon or power plant, whichever is
closer; None when nothing is within 20 km), plus `near_vegetation` +
`vegetation_distance_m`, and `near_power_plant` + `power_plant_distance_m`.

Distances are measured with a per-fire UTM transverse-Mercator projection, so
meter values stay meaningful regardless of longitude (raw lon/lat degrees are
not linear in meters).

All geometries are (lon, lat) order, matching both FIRMS GeoJSON and our OSM
conversion.
"""

import logging
from functools import lru_cache

import pyproj
from shapely.errors import GEOSException
from shapely.geometry import shape
from shapely.ops import transform
from shapely.strtree import STRtree

logger = logging.getLogger(__name__)

NEAR_BUFFER_METERS = 1000
VEGETATION_BUFFER_METERS = 3000
SEARCH_RADIUS_METERS = 20000
_SEARCH_PAD_DEGREES = 0.3


def _utm_epsg_for_longitude(lon: float) -> int:
    """Pick a UTM zone EPSG code (northern hemisphere) for a longitude."""
    zone = int((lon + 180) // 6) + 1
    return 32600 + zone


@lru_cache(maxsize=64)
def _get_transformer(epsg: int) -> pyproj.Transformer:
    return pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)


def _utm_distance_meters(point, polygon: "object") -> float:
    """Project both geometries to the point's UTM zone and measure meters."""
    transformer = _get_transformer(_utm_epsg_for_longitude(point.x))
    projected_point = transform(transformer.transform, point)
    projected_polygon = transform(transformer.transform, polygon)
    return float(projected_polygon.distance(projected_point))


import numpy as np


def _nearest_distance_meters(
    point, polygons: list, tree: STRtree | None = None
) -> float | None:
    """Nearest distance (meters) from point to any polygon, or None if too far."""
    if not polygons:
        return None
    if tree is None:
        tree = STRtree(polygons)
    idx = tree.query_nearest(point)
    if idx is None or (hasattr(idx, "__len__") and len(idx) == 0):
        return None
    nearest_idx = int(np.asarray(idx).ravel()[0])
    nearest_poly = polygons[nearest_idx]
    if nearest_poly.distance(point) > _SEARCH_PAD_DEGREES:
        return None
    nearest = _utm_distance_meters(point, nearest_poly)
    return nearest if nearest <= SEARCH_RADIUS_METERS else None


def _nearest_power_plant(
    point,
    features: list,
    points: list | None = None,
    tree: STRtree | None = None,
) -> tuple[float | None, dict | None]:
    """Nearest power-plant point (meters) + its properties, or (None, None)."""
    if not features:
        return None, None
    if points is None:
        points = [shape(feature["geometry"]) for feature in features]
    if tree is None:
        tree = STRtree(points)
    idx = tree.query_nearest(point)
    if idx is None or (hasattr(idx, "__len__") and len(idx) == 0):
        return None, None
    nearest_idx = int(np.asarray(idx).ravel()[0])
    feature = features[nearest_idx]
    plant_point = points[nearest_idx]
    if plant_point.distance(point) > _SEARCH_PAD_DEGREES:
        return None, None
    distance_m = _utm_distance_meters(point, plant_point)
    if distance_m > SEARCH_RADIUS_METERS:
        return None, None
    return round(distance_m, 1), feature["properties"] or {}


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
    idx = tree.query_nearest(point)
    if idx is None or (hasattr(idx, "__len__") and len(idx) == 0):
        return None
    nearest_idx = int(np.asarray(idx).ravel()[0])
    poly = polygons[nearest_idx]
    feature = features[nearest_idx]
    if poly.distance(point) > _SEARCH_PAD_DEGREES:
        return None
    distance_m = _utm_distance_meters(point, poly)
    if distance_m > search_meters:
        return None
    props = feature["properties"] or {}
    return {
        "name": props.get("name"),
        "osm_id": props.get("osm_id"),
        "distance_m": round(distance_m, 1),
    }


_SPATIAL_INDEX_CACHE: dict[int, tuple[list, STRtree | None]] = {}


def _get_spatial_index(fc: dict | None) -> tuple[list, STRtree | None]:
    if not fc or not fc.get("features"):
        return [], None
    key = id(fc)
    cached = _SPATIAL_INDEX_CACHE.get(key)
    if cached is not None:
        return cached
    polygons = [shape(feature["geometry"]) for feature in fc["features"]]
    tree = STRtree(polygons) if polygons else None
    _SPATIAL_INDEX_CACHE[key] = (polygons, tree)
    return polygons, tree


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
    fires_fc: dict,
    industrial_fc: dict,
    vegetation_fc: dict | None = None,
    power_plants_fc: dict | None = None,
) -> dict:
    """Add rule-based fire type + proximity flags to every fire feature.

    Mutates and returns the input FeatureCollection (fires_fc). Classification
    priority: industrial first (1 km buffer around OSM industrial polygons OR
    power-plant points), then forest (3 km vegetation buffer — OSM forest/wood
    polygons are conservative, so a wider radius is a fairer "near natural
    vegetation" definition), else other_natural. `distance_m` is the distance to
    whichever industrial feature (OSM polygon or power plant) is nearest.
    """
    industrial_polygons, industrial_tree = _get_spatial_index(industrial_fc)
    vegetation_polygons, vegetation_tree = _get_spatial_index(vegetation_fc)

    power_plants_fc = power_plants_fc or {"type": "FeatureCollection", "features": []}
    power_plant_features = power_plants_fc.get("features", [])
    power_plant_points, power_plant_tree = _get_spatial_index(power_plants_fc)

    for feature in fires_fc["features"]:
        prop = feature["properties"]
        prop["near_industrial"] = False
        prop["distance_m"] = None
        prop["near_vegetation"] = False
        prop["vegetation_distance_m"] = None
        prop["near_power_plant"] = False
        prop["power_plant_distance_m"] = None
        prop["industrial_match_source"] = None
        prop["fire_type_rule"] = "other_natural"

        point = _extract_point(feature)
        if point is None:
            continue

        industrial_distance = _nearest_distance_meters(
            point, industrial_polygons, industrial_tree
        )
        power_plant_distance, power_plant_props = _nearest_power_plant(
            point, power_plant_features, power_plant_points, power_plant_tree
        )

        if industrial_distance is not None:
            prop["distance_m"] = round(industrial_distance, 1)
        if power_plant_distance is not None and (
            industrial_distance is None or power_plant_distance < prop["distance_m"]
        ):
            prop["distance_m"] = round(power_plant_distance, 1)

        near_osm_industrial = (
            industrial_distance is not None
            and industrial_distance <= NEAR_BUFFER_METERS
        )
        near_power_plant = (
            power_plant_distance is not None
            and power_plant_distance <= NEAR_BUFFER_METERS
        )
        prop["near_power_plant"] = near_power_plant
        prop["near_industrial"] = near_osm_industrial or near_power_plant
        if power_plant_distance is not None:
            prop["power_plant_distance_m"] = round(power_plant_distance, 1)
            if power_plant_props:
                prop["power_plant_name"] = power_plant_props.get("name")
        prop["industrial_match_source"] = (
            "both"
            if near_osm_industrial and near_power_plant
            else "osm"
            if near_osm_industrial
            else "power_plant_db"
            if near_power_plant
            else None
        )
        if prop["near_industrial"]:
            prop["fire_type_rule"] = "industrial"

        vegetation_distance = _nearest_distance_meters(
            point, vegetation_polygons, vegetation_tree
        )
        if vegetation_distance is not None:
            prop["vegetation_distance_m"] = round(vegetation_distance, 1)
            if vegetation_distance <= VEGETATION_BUFFER_METERS:
                prop["near_vegetation"] = True
                if prop["fire_type_rule"] == "other_natural":
                    prop["fire_type_rule"] = "forest"

    return fires_fc
