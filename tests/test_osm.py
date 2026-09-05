from app.services import osm

SAMPLE_WAYS = [
    {
        "type": "way",
        "id": 101,
        "tags": {"landuse": "industrial", "name": "Steel Plant"},
        "geometry": [
            {"lat": 23.5, "lon": 86.1},
            {"lat": 23.5, "lon": 86.2},
            {"lat": 23.6, "lon": 86.2},
            {"lat": 23.6, "lon": 86.1},
        ],
    },
    {
        "type": "way",
        "id": 102,
        "tags": {"landuse": "industrial"},
        "geometry": [{"lat": 19.0, "lon": 73.0}, {"lat": 19.0, "lon": 73.1}],
    },
    {"type": "node", "id": 999, "lat": 20.0, "lon": 75.0},
]


def test_build_query_bbox_order():
    query = osm.build_query(72.0, 15.0, 81.0, 22.5, 90)
    assert 'way["landuse"="industrial"]' in query
    assert "(15.0,72.0,22.5,81.0)" in query
    assert "timeout:90" in query


def test_elements_to_featurecollection():
    fc = osm.osm_elements_to_featurecollection(SAMPLE_WAYS)
    assert len(fc["features"]) == 1
    feat = fc["features"][0]
    assert feat["geometry"]["type"] == "Polygon"
    ring = feat["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1]
    assert feat["properties"]["name"] == "Steel Plant"
    assert feat["properties"]["landuse"] == "industrial"
    assert feat["id"] == "osm-way-101"


def test_parse_state_bbox_good():
    assert osm.parse_state_bbox("67.5,20,75,25") == (67.5, 20.0, 75.0, 25.0)


def test_parse_state_bbox_bad():
    for bad in ("67.5,20,75", "80,20,75,25", "a,b,c,d"):
        try:
            osm.parse_state_bbox(bad)
            raise AssertionError(f"expected ValueError for {bad!r}")
        except ValueError:
            pass


def test_tile_bbox_grid():
    tiles = osm.tile_bbox(72.0, 15.0, 81.0, 22.5)
    assert len(tiles) == 4
    assert tiles[0] == (72.0, 15.0, 76.5, 18.75)
    assert tiles[3] == (76.5, 18.75, 81.0, 22.5)
    for tile in tiles:
        assert tile[0] < tile[2] and tile[1] < tile[3]
