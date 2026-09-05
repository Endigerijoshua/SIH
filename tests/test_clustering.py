"""Tests for DBSCAN site clustering of persistent thermal sources."""

from app.services import clustering

PLANT_POLY = {
    "type": "Feature",
    "id": "osm-way-1",
    "properties": {"name": "Test Plant", "landuse": "industrial"},
    "geometry": {
        "type": "Polygon",
        "coordinates": [
            [
                [72.50, 22.40],
                [72.60, 22.40],
                [72.60, 22.50],
                [72.50, 22.50],
                [72.50, 22.40],
            ]
        ],
    },
}


def _points(coords, persistent=True):
    features = []
    for i, (lon, lat) in enumerate(coords):
        features.append(
            {
                "type": "Feature",
                "id": i,
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "persistent_thermal_source": persistent,
                    "occurrence_count": 2,
                    "near_industrial": False,
                    "distance_m": None,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _zones():
    return {
        "type": "FeatureCollection",
        "features": [PLANT_POLY],
    }


def test_two_close_recurrences_form_one_site():
    fc = _points([(72.55, 22.45), (72.5504, 22.45)])
    result = clustering.cluster_persistent_fires(fc, _zones())
    sites = result["features"]
    assert len(sites) == 1
    assert sites[0]["properties"]["member_count"] == 2
    assert result["meta"]["unclustered"] == 0


def test_far_recurrence_stays_unclustered():
    fc = _points([(72.55, 22.45), (72.5504, 22.45), (72.55, 23.5)])
    result = clustering.cluster_persistent_fires(fc, _zones())
    assert len(result["features"]) == 1
    assert result["meta"]["unclustered"] == 1


def test_non_persistent_fires_are_ignored():
    fc = _points([(72.55, 22.45), (72.5504, 22.45)], persistent=False)
    result = clustering.cluster_persistent_fires(fc, _zones())
    assert result["features"] == []
    assert result["meta"]["persistent_count"] == 0


def test_site_named_after_nearest_industrial_zone():
    fc = _points([(72.55, 22.45), (72.5504, 22.45)])
    result = clustering.cluster_persistent_fires(fc, _zones())
    site = result["features"][0]
    assert site["properties"]["site_name"].startswith("Site near Test Plant")
    assert site["properties"]["near_industrial_zone"] == "Test Plant"


def test_no_persistent_points_yields_no_sites():
    result = clustering.cluster_persistent_fires(_points([]), _zones())
    assert result["features"] == []
    assert result["meta"]["persistent_count"] == 0