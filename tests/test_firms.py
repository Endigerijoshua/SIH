from fastapi.testclient import TestClient

from app.main import app
from app.services import firms


def test_health():
    client = TestClient(app)
    assert client.get("/api/health").json() == {"status": "ok"}


def test_index_placeholder():
    client = TestClient(app)
    assert client.get("/").status_code == 200


def test_parse_bbox_good():
    result = firms.parse_bbox("68,7,97,37")
    assert result == (68.0, 7.0, 97.0, 37.0)


def test_parse_bbox_bad():
    for bad in ("68,7,97", "100,50,90,40", "a,b,c,d"):
        try:
            firms.parse_bbox(bad)
            raise AssertionError(f"expected ValueError for {bad!r}")
        except ValueError:
            pass


def test_csv_to_geojson():
    csv_text = (
        "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,"
        "instrument,confidence,version,bright_ti5,frp,daynight\n"
        "12.75382,92.88086,332.85,0.44,0.46,2026-09-04,654,N,VIIRS,n,2.0NRT,284.25,2.49,D\n"
    )
    fc = firms.csv_to_geojson(csv_text)
    feat = fc["features"][0]
    assert feat["geometry"]["coordinates"] == [92.88086, 12.75382]
    assert feat["properties"]["confidence"] == "nominal"
    assert feat["properties"]["acq_time"] == "0654"
    assert feat["properties"]["source"] == "nasa_firms"
