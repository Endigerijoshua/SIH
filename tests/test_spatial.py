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

# Forest polygon overlapping the plant so a point inside both exists.
FOREST_POLY = {
    "type": "Feature",
    "id": "osm-way-2",
    "geometry": {
        "type": "Polygon",
        "coordinates": [
            [
                [72.15, 22.40],
                [72.75, 22.40],
                [72.75, 22.50],
                [72.15, 22.50],
                [72.15, 22.40],
            ]
        ],
    },
    "properties": {"landuse": "forest", "name": "Test Forest"},
}

# A fire inside the forest polygon, far from the plant.
FIRE_IN_FOREST = {
    "type": "Feature",
    "id": 4,
    "geometry": {"type": "Point", "coordinates": [72.15, 22.45]},
    "properties": {},
}

# A fire inside the forest polygon AND inside the plant polygon.
FIRE_IN_BOTH = {
    "type": "Feature",
    "id": 5,
    "geometry": {"type": "Point", "coordinates": [72.55, 22.49]},
    "properties": {},
}

FOREST_FC = {"type": "FeatureCollection", "features": [FOREST_POLY]}

# WRI-style power-plant points. One sits right next to the OSM polygon (so a
# fire there matches both sources); one sits far from any OSM polygon.
POWER_PLANT_NEAR = {
    "type": "Feature",
    "id": "wri-pp-1",
    "geometry": {"type": "Point", "coordinates": [72.55, 22.506]},
    "properties": {"name": "Halo Thermal", "source": "power_plant_db"},
}
POWER_PLANT_SOLO = {
    "type": "Feature",
    "id": "wri-pp-2",
    "geometry": {"type": "Point", "coordinates": [74.05, 15.0]},
    "properties": {"name": "Solo Thermal", "source": "power_plant_db"},
}

# A fire ~440 m south of the solo power plant, far from any OSM polygon.
FIRE_SOLO_NEAR_PLANT = {
    "type": "Feature",
    "id": 6,
    "geometry": {"type": "Point", "coordinates": [74.05, 15.004]},
    "properties": {},
}


def _run(fires, vegetation_fc=None, power_plants_fc=None):
    fc = {"type": "FeatureCollection", "features": fires}
    zones = {"type": "FeatureCollection", "features": [PLANT_POLY]}
    return spatial.annotate_fires(fc, zones, vegetation_fc, power_plants_fc)["features"]


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
    feats = _run(
        [
            FIRE_INSIDE,
            FIRE_500M_AWAY,
            FIRE_1_3KM_AWAY,
            FIRE_FAR_AWAY,
            FIRE_SOLO_NEAR_PLANT,
        ]
    )
    for feat in feats:
        assert "near_industrial" in feat["properties"]
        assert "distance_m" in feat["properties"]
        assert "fire_type_rule" in feat["properties"]
        assert "near_vegetation" in feat["properties"]
        assert "vegetation_distance_m" in feat["properties"]
        assert "near_power_plant" in feat["properties"]
        assert "power_plant_distance_m" in feat["properties"]
        assert "industrial_match_source" in feat["properties"]
    assert sum(f["properties"]["near_industrial"] for f in feats) == 2


def test_fire_near_power_plant_only_is_industrial():
    pp = {"type": "FeatureCollection", "features": [POWER_PLANT_SOLO]}
    feats = _run([FIRE_SOLO_NEAR_PLANT], power_plants_fc=pp)
    prop = feats[0]["properties"]
    assert prop["fire_type_rule"] == "industrial"
    assert prop["near_industrial"] is True
    assert prop["near_power_plant"] is True
    assert prop["industrial_match_source"] == "power_plant_db"
    assert prop["power_plant_distance_m"] <= 500
    assert prop["power_plant_name"] == "Solo Thermal"


def test_fire_near_power_plant_and_osm_marks_both():
    pp = {"type": "FeatureCollection", "features": [POWER_PLANT_NEAR]}
    feats = _run([FIRE_500M_AWAY], power_plants_fc=pp)
    prop = feats[0]["properties"]
    assert prop["near_industrial"] is True
    assert prop["industrial_match_source"] == "both"
    assert prop["near_power_plant"] is True
    assert prop["distance_m"] <= 300  # power plant is the nearer source


def test_power_plant_within_radar_but_over_1km_not_industrial():
    plant = {
        "type": "Feature",
        "id": "wri-pp-3",
        "geometry": {"type": "Point", "coordinates": [72.55, 22.463]},
        "properties": {"name": "Far Plant", "source": "power_plant_db"},
    }
    pp = {"type": "FeatureCollection", "features": [plant]}
    feats = _run([FIRE_INSIDE], power_plants_fc=pp)
    prop = feats[0]["properties"]
    assert prop["near_power_plant"] is False
    assert prop["power_plant_distance_m"] > 1000  # within 20 km search radius
    assert prop["industrial_match_source"] == "osm"


def test_fire_inside_industrial_zone_fire_type_rule_industrial():
    feats = _run([FIRE_INSIDE])
    assert feats[0]["properties"]["fire_type_rule"] == "industrial"
    assert feats[0]["properties"]["near_industrial"] is True


def test_fire_in_forest_only_is_forest():
    feats = _run([FIRE_IN_FOREST], FOREST_FC)
    prop = feats[0]["properties"]
    assert prop["fire_type_rule"] == "forest"
    assert prop["near_industrial"] is False
    assert prop["near_vegetation"] is True
    assert prop["vegetation_distance_m"] <= 1000


def test_fire_near_everything_stays_industrial():
    feats = _run([FIRE_IN_BOTH], FOREST_FC)
    prop = feats[0]["properties"]
    assert prop["fire_type_rule"] == "industrial"
    assert prop["near_industrial"] is True
    assert prop["near_vegetation"] is True


def test_fire_far_from_all_is_other_natural():
    feats = _run([FIRE_FAR_AWAY], FOREST_FC)
    prop = feats[0]["properties"]
    assert prop["fire_type_rule"] == "other_natural"
    assert prop["near_industrial"] is False
    assert prop["near_vegetation"] is False
