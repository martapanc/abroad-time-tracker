"""Offline point -> ISO country code lookup.

World borders come from Natural Earth 1:10m. That is too coarse for tiny
countries (Andorra is ~30 km across, and Pas de la Casa sits right on the
border), so "focus" countries are overlaid with high-resolution OpenStreetMap
outlines that take priority.
"""

import json
import os
import urllib.request
from pathlib import Path

import shapely
from shapely.geometry import shape
from shapely.strtree import STRtree

WORLD_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_0_countries.geojson"
OSM_POLYGON_URL = "https://polygons.openstreetmap.fr/get_geojson.py?id={relation}&params=0"
# ISO alpha-2 -> OpenStreetMap boundary relation id. Add others as CODE=ID on the CLI.
OSM_RELATIONS = {"AD": 9407}
CACHE_DIR = Path(os.environ.get("ABROAD_CACHE", Path.home() / ".cache" / "abroad"))

# Points in the sea or just off a coastline still resolve to the nearest
# country within this distance (degrees, ~10 km).
NEAREST_MAX_DEG = 0.1


def _download(url: str, dest: Path) -> Path:
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"Downloading {url} ...")
        tmp = dest.with_suffix(".part")
        urllib.request.urlretrieve(url, tmp)
        tmp.rename(dest)
    return dest


def _focus_geom(code: str, relation: int):
    path = _download(OSM_POLYGON_URL.format(relation=relation), CACHE_DIR / f"osm-{code}-{relation}.geojson")
    return shape(json.loads(path.read_text()))


class CountryLookup:
    def __init__(self, focus: dict[str, int] = OSM_RELATIONS):
        world = json.loads(_download(WORLD_URL, CACHE_DIR / "ne_10m_admin_0_countries.geojson").read_text())
        self.codes: list[str] = []
        self.names: dict[str, str] = {}
        geoms = []
        for f in world["features"]:
            p = f["properties"]
            code = p.get("ISO_A2_EH") or p.get("ISO_A2")
            if not code or code == "-99":
                code = p["ADM0_A3"]
            self.codes.append(code)
            self.names.setdefault(code, p["NAME"])
            geoms.append(shape(f["geometry"]))
        self.tree = STRtree(geoms)

        self.focus: list[tuple[str, object]] = []
        for code, relation in focus.items():
            poly = _focus_geom(code, relation)
            shapely.prepare(poly)
            self.focus.append((code, poly))
        self._cache: dict[tuple[float, float], str | None] = {}

    def name(self, code: str) -> str:
        return self.names.get(code, code)

    def lookup_many(self, coords: list[tuple[float, float]]) -> list[str | None]:
        """Map (lat, lon) pairs to ISO alpha-2 codes (None if nowhere near land)."""
        keys = [(round(lat, 4), round(lon, 4)) for lat, lon in coords]
        todo = list({k for k in keys if k not in self._cache})
        if todo:
            pts = shapely.points([(lon, lat) for lat, lon in todo])
            result: list[str | None] = [None] * len(todo)

            # High-resolution focus countries win outright.
            focus_codes = {code for code, _ in self.focus}
            for code, poly in self.focus:
                for i in range(len(todo)):
                    if result[i] is None and poly.contains(pts[i]):
                        result[i] = code

            # Everything else: Natural Earth, ignoring its coarse focus outlines
            # (a point inside NE-Andorra but outside real Andorra is a neighbour).
            rest = [i for i, r in enumerate(result) if r is None]
            if rest:
                hit_pt, hit_geom = self.tree.query(pts[rest], predicate="intersects")
                for p, g in zip(hit_pt, hit_geom):
                    i = rest[p]
                    if result[i] is None and self.codes[g] not in focus_codes:
                        result[i] = self.codes[g]
                for i in rest:
                    if result[i] is None:
                        near = [
                            g
                            for g in self.tree.query(pts[i], predicate="dwithin", distance=NEAREST_MAX_DEG)
                            if self.codes[g] not in focus_codes
                        ]
                        if near:
                            best = min(near, key=lambda g: self.tree.geometries[g].distance(pts[i]))
                            result[i] = self.codes[best]

            self._cache.update(zip(todo, result))
        return [self._cache[k] for k in keys]
