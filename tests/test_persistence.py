"""Tests for SQLite fire_history accumulation and persistence detection."""

import datetime as dt

import pytest

from app import db
from app.services import persistence


@pytest.fixture()
def temp_db(monkeypatch, tmp_path):
    db_file = tmp_path / "test_history.db"
    monkeypatch.setattr(db, "db_path", lambda: str(db_file))
    return db_file


def _feature(lat, lon, acq_date, satellite="T"):
    return {
        "type": "Feature",
        "id": 0,
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "acq_date": acq_date,
            "acq_time": 1234,
            "satellite": satellite,
            "confidence": "n",
        },
    }


def _record(fc):
    return db.record_featurecollection({"type": "FeatureCollection", "features": fc})


def _days_ago(*offsets):
    return [(db.today() - dt.timedelta(days=d)).isoformat() for d in offsets]


def test_haversine_known_distance():
    meters = db._haversine_meters(22.0, 72.0, 23.0, 72.0)
    assert 110_000 < meters < 112_000


def test_records_accumulate_across_calls_and_dedupe(temp_db):
    day = db.today().isoformat()
    first = _record([_feature(22.5, 72.5, day)])
    second = _record([_feature(22.5, 72.5, day)])
    assert first == 1
    assert second == 0
    with db.get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM fire_history").fetchone()[0]
    assert count == 1


def test_two_days_within_300m_reads_as_2_occurrences(temp_db):
    lat, lon = 22.5, 72.5
    _record([_feature(lat + 0.002, lon, d) for d in _days_ago(1, 5)])
    count = persistence.occurrence_count(lat, lon)
    assert count == 2
    assert persistence.is_persistent(count) is True


def test_annotate_sets_persistence_fields_for_recurring_source(temp_db):
    lat, lon = 20.0, 76.0
    _record([_feature(lat + 0.001, lon, d) for d in _days_ago(1, 8)])
    fc = {
        "type": "FeatureCollection",
        "features": [_feature(lat, lon, db.today().isoformat())],
    }
    persistence.annotate_persistence(fc)
    props = fc["features"][0]["properties"]
    assert props["persistent_thermal_source"] is True
    assert props["occurrence_count"] == 2


def test_single_day_or_too_far_is_not_persistent(temp_db):
    lat, lon = 21.0, 77.0
    today = db.today().isoformat()
    _record([_feature(lat, lon, today)])
    _record([_feature(lat + 0.005, lon, today)])
    fc = {
        "type": "FeatureCollection",
        "features": [_feature(lat, lon, today)],
    }
    persistence.annotate_persistence(fc)
    props = fc["features"][0]["properties"]
    assert props["persistent_thermal_source"] is False
    assert props["occurrence_count"] == 1


def test_occurrences_outside_14day_window_not_counted(temp_db):
    lat, lon = 23.0, 78.0
    _record([_feature(lat + 0.001, lon, d) for d in _days_ago(15, 16)])
    count = persistence.occurrence_count(lat, lon)
    assert count == 0
