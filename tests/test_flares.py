from app.services import flares

SAMPLE_KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Placemark>
<Style><IconStyle><scale>0.5</scale></IconStyle></Style>
<name>IND_UNKNOWN_2024_72.6394E_21.1073N_v0.2</name>
<Point><coordinates>72.6394,21.1073,0</coordinates></Point>
</Placemark>
<Placemark>
<name>USA_UPS_2024_150.9261W_70.3428N_v0.2</name>
<Point><coordinates>-150.926137,70.34276,0</coordinates></Point>
</Placemark>
<Placemark>
<name>bad_coords</name>
<Point><coordinates>not-a-number,21,0</coordinates></Point>
</Placemark>
<Placemark>
<name>no_geometry</name>
</Placemark>
</Document></kml>
"""


def test_kml_to_geojson_filters_india_bbox():
    fc = flares.kml_to_geojson(SAMPLE_KML)
    features = fc["features"]
    assert len(features) == 1
    feature = features[0]
    assert feature["geometry"]["type"] == "Point"
    assert feature["geometry"]["coordinates"] == [72.6394, 21.1073]
    assert feature["properties"]["name"].startswith("IND_")
    assert feature["properties"]["country"] == "IND"
    assert feature["properties"]["year"] == flares.CATALOG_YEAR
    assert feature["properties"]["source"] == "viirs_nightfire"


def test_kml_to_geojson_handles_garbage():
    assert flares.kml_to_geojson("not xml <at all")["features"] == []


def test_cache_settings_present():
    assert flares.settings.flares_cache_file.endswith(".json")
    assert flares.settings.flares_cache_max_age_hours >= 720
