from fastapi.testclient import TestClient

from app.main import app
from app.services import firms

SAMPLE_CSV = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,"
    "instrument,confidence,version,bright_ti5,frp,daynight\n"
    "12.75382,92.88086,332.85,0.44,0.46,2026-09-04,654,N,VIIRS,n,2.0NRT,284.25,2.49,D\n"
    "24.00891,96.12032,332.91,0.38,0.36,2026-09-04,657,N,VIIRS,n,2.0NRT,294.47,2.33,D\n"
    "29.18748,88.53117,326.49,0.42,0.45,2026-09-04,659,N,VIIRS,l,2.0NRT,296.03,2.61,D\n"
)


def test_health():
    client = TestClient(app)
    assert client.get("/api/health").json() == {"status": "ok"}


def test_index_placeholder():
    client = TestClient(app)
    assert client.get("/").status_code == 200


def test_parse_bbox_good():
    result = firms.parse_bbox("68,6,97,37")
    assert result == (68.0, 6.0, 97.0, 37.0)


def test_parse_bbox_bad():
    for bad in ("68,6,97", "100,50,90,40", "a,b,c,d"):
        try:
            firms.parse_bbox(bad)
            raise AssertionError(f"expected ValueError for {bad!r}")
        except ValueError:
            pass


def test_csv_to_geojson():
    fc = firms.csv_to_geojson(SAMPLE_CSV)
    feat = fc["features"][0]
    assert feat["geometry"]["coordinates"] == [92.88086, 12.75382]
    assert feat["properties"]["confidence"] == "n"
    assert feat["properties"]["bright_ti4"] == 332.85
    assert feat["properties"]["frp"] == 2.49
    assert feat["properties"]["acq_date"] == "2026-09-04"
    assert feat["properties"]["acq_time"] == 654
    assert feat["properties"]["satellite"] == "N"
    assert feat["properties"]["daynight"] == "D"


def test_csv_to_geojson_no_rows_dropped():
    fc = firms.csv_to_geojson(SAMPLE_CSV)
    assert len(fc["features"]) == 3


def test_missing_firms_map_key_returns_400(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "firms_map_key", "")
    client = TestClient(app)
    resp = client.get("/api/flagged-fires")
    assert resp.status_code == 400
    assert "FIRMS_MAP_KEY" in resp.json()["detail"]

