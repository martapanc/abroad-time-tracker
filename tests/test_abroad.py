import json
from datetime import date

import pytest

from abroad.days import build_days, fill_gaps, max_window
from abroad.geo import CountryLookup
from abroad.sources import read_file


@pytest.fixture(scope="module")
def lookup():
    return CountryLookup()


@pytest.mark.parametrize("lat,lon,code", [
    (42.5063, 1.5218, "AD"),   # Andorra la Vella
    (42.5423, 1.7334, "AD"),   # Pas de la Casa, right on the French border
    (42.4435, 1.4906, "AD"),   # Sant Julià de Lòria, near the Spanish border
    (42.3580, 1.4560, "ES"),   # La Seu d'Urgell
    (42.5889, 1.8003, "FR"),   # L'Hospitalet-près-l'Andorre
    (41.3874, 2.1686, "ES"),   # Barcelona
    (41.3600, 2.2200, "ES"),   # just off the Barcelona coast
    (48.8566, 2.3522, "FR"),   # Paris
    (0.0, -30.0, None),        # mid-Atlantic
])
def test_lookup(lookup, lat, lon, code):
    assert lookup.lookup_many([(lat, lon)]) == [code]


def locate(lookup, obs):
    return [lookup.lookup_many([(o.lat, o.lon)])[0] if o.lat is not None else None for o in obs]


def test_android_timeline_multiday_visit(tmp_path, lookup):
    f = tmp_path / "Timeline.json"
    f.write_text(json.dumps({"semanticSegments": [
        {"startTime": "2025-03-01T18:00:00.000+01:00", "endTime": "2025-03-04T09:00:00.000+01:00",
         "visit": {"topCandidate": {"placeLocation": {"latLng": "42.5063°, 1.5218°"}}}},
        {"startTime": "2025-03-04T09:00:00.000+01:00", "endTime": "2025-03-04T12:00:00.000+01:00",
         "timelinePath": [{"point": "41.3874°, 2.1686°", "time": "2025-03-04T11:30:00.000+01:00"}]},
    ]}))
    obs = list(read_file(f))
    days = build_days(obs, locate(lookup, obs))
    assert sorted(days) == [date(2025, 3, d) for d in (1, 2, 3, 4)]
    assert days[date(2025, 3, 4)].counted("presence") == {"AD", "ES"}
    assert days[date(2025, 3, 4)].counted("night") == {"ES"}


def test_ios_timeline(tmp_path, lookup):
    f = tmp_path / "location-history.json"
    f.write_text(json.dumps([
        {"startTime": "2025-06-01T10:00:00.000+02:00", "endTime": "2025-06-01T20:00:00.000+02:00",
         "visit": {"topCandidate": {"placeLocation": "geo:42.542300,1.733400"}}},
        {"startTime": "2025-06-02T08:00:00.000+02:00", "endTime": "2025-06-02T10:00:00.000+02:00",
         "activity": {"start": "geo:42.542300,1.733400", "end": "geo:48.856600,2.352200"}},
    ]))
    obs = list(read_file(f))
    days = build_days(obs, locate(lookup, obs))
    assert days[date(2025, 6, 1)].countries == {"AD"}
    assert days[date(2025, 6, 2)].last == "FR"


def test_takeout_records_and_photos_and_csv(tmp_path, lookup):
    rec = tmp_path / "Records.json"
    rec.write_text(json.dumps({"locations": [
        {"latitudeE7": 425063000, "longitudeE7": 15218000, "timestamp": "2022-01-05T10:00:00Z"}]}))
    photos = tmp_path / "photos.json"
    photos.write_text(json.dumps([
        {"date": "2023-08-15T13:00:00+02:00", "latitude": 42.5063, "longitude": 1.5218},
        {"date": "2023-08-16T13:00:00+02:00", "latitude": None, "longitude": None}]))
    log = tmp_path / "log.csv"
    log.write_text("timestamp,lat,lon\n2026-09-28T23:30:00+02:00,42.5063,1.5218\n2026-09-29,ES\n")
    obs = [*read_file(rec), *read_file(photos), *read_file(log)]
    days = build_days(obs, locate(lookup, obs))
    assert days[date(2022, 1, 5)].countries == {"AD"}
    assert days[date(2023, 8, 15)].countries == {"AD"}
    assert date(2023, 8, 16) not in days
    assert days[date(2026, 9, 28)].countries == {"AD"}
    assert days[date(2026, 9, 29)].override and days[date(2026, 9, 29)].countries == {"ES"}


def test_fill_gaps_and_window(tmp_path, lookup):
    log = tmp_path / "log.csv"
    log.write_text("2025-01-01,AD\n2025-01-04,AD\n2025-01-05,ES\n2025-01-20,AD\n")
    obs = list(read_file(log))
    days = build_days(obs, [None] * len(obs))
    fill_gaps(days, 3)
    assert days[date(2025, 1, 2)].inferred and days[date(2025, 1, 3)].countries == {"AD"}
    assert date(2025, 1, 10) not in days  # gap too long / countries differ
    best, _, current = max_window(days, "AD", "presence", 180, date(2025, 1, 31))
    assert best == current == 5
