from app.services import spatial

# (lon, lat) order — as FIRMS and our OSM conversion output.
PLANT_POLY = {
    "type": "Feature",
    "id": "osm-way-1",
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
    "properties": {"landuse": "industrial", "name": "Test Plant"},
}

# A fire just outside the plant polygon (~1.1 km south).
FIRE_INSIDE = {
    "type": "Feature",
    "id": 0,
    "geometry": {"type": "Point", "coordinates": [72.55, 22.45]},
    "properties": {},
}
FIRE_500M_AWAY = {
    "type": "Feature",
    "id": 1,
    "geometry": {"type": "Point", "coordinates": [72.55, 22.505]},
    "properties": {},
}
FIRE_1_3KM_AWAY = {
    "type": "Feature",
    "id": 2,
    "geometry": {"type": "Point", "coordinates": [72.55, 22.513]},
    "properties": {},
}
FIRE_FAR_AWAY = {
    "type": "Feature",
    "id": 3,
    "geometry": {"type": "Point", "coordinates": [93.0, 12.0]},
    "properties": {},
}


def _run(fires):
    fc = {"type": "FeatureCollection", "features": fires}
    zones = {"type": "FeatureCollection", "features": [PLANT_POLY]}
    return spatial.annotate_fires(fc, zones)["features"]


def test_fire_inside_zone_flagged():
    feats = _run([FIRE_INSIDE])
    assert feats[0]["properties"]["near_industrial"] is True
    assert feats[0]["properties"]["distance_m"] < 1000


def test_fire_within_1km_flagged():
    feats = _run([FIRE_500M_AWAY])
    prop = feats[0]["properties"]
    assert prop["near_industrial"] is True
    assert 400 <= prop["distance_m"] <= 1000


def test_fire_over_1km_not_flagged():
    feats = _run([FIRE_1_3KM_AWAY])
    prop = feats[0]["properties"]
    assert prop["near_industrial"] is False
    assert prop["distance_m"] > 1000


def test_fire_far_away_not_flagged():
    feats = _run([FIRE_FAR_AWAY])
    prop = feats[0]["properties"]
    assert prop["near_industrial"] is False
    assert prop["distance_m"] is None


def test_all_features_have_annotation_fields():
    feats = _run([FIRE_INSIDE, FIRE_500M_AWAY, FIRE_1_3KM_AWAY, FIRE_FAR_AWAY])
    for feat in feats:
        assert "near_industrial" in feat["properties"]
        assert "distance_m" in feat["properties"]
    assert sum(f["properties"]["near_industrial"] for f in feats) == 2
