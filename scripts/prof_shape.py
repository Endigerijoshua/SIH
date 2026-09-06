import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shapely.geometry import shape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_fc(name):
    with open(os.path.join(ROOT, f"{name}_zones_cache.json"), encoding="utf-8") as f:
        return json.load(f).get("feature_collection")


ind = load_fc("industrial")
veg = load_fc("vegetation")
with open(os.path.join(ROOT, "power_plants_cache.json"), encoding="utf-8") as f:
    pp = json.load(f).get("feature_collection")

for name, fc in (("industrial", ind), ("vegetation", veg), ("powerplants", pp)):
    t = time.perf_counter()
    polys = [shape(f["geometry"]) for f in fc["features"]]
    print(f"shape() {name}: {len(polys)} features in {time.perf_counter() - t:.3f}s")
