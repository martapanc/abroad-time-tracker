"""Readers for location exports. Each yields Observations.

An Observation is "I was at (lat, lon) from start to end". Times keep the UTC
offset they were recorded with, so each maps to the *local* calendar day.
Supported inputs (auto-detected by content, not file name):

- Google Maps Timeline on-device export (Android and iOS flavours)
- Google Takeout Location History (Records.json, Semantic Location History)
- osxphotos `query --json` output (photo geotags)
- CSV: timestamp,lat,lon  (e.g. the daily iOS Shortcut log)  or  date,country
"""

import csv
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator


@dataclass
class Observation:
    start: datetime
    end: datetime
    source: str
    lat: float | None = None
    lon: float | None = None
    country: str | None = None  # set directly by date,country CSVs


_LATLNG = re.compile(r"(-?\d+(?:\.\d+)?)°?,\s*(-?\d+(?:\.\d+)?)")


def parse_latlng(value) -> tuple[float, float] | None:
    """Accepts "42.5°, 1.52°", "geo:42.5,1.52", or {"latitudeE7":..., "longitudeE7":...}."""
    if isinstance(value, dict):
        if "latitudeE7" in value:
            return value["latitudeE7"] / 1e7, value["longitudeE7"] / 1e7
        if "latLng" in value:
            return parse_latlng(value["latLng"])
        return None
    if isinstance(value, str):
        m = _LATLNG.search(value)
        if m:
            return float(m.group(1)), float(m.group(2))
    return None


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _obs(start, end, latlng, source) -> Observation | None:
    if latlng is None:
        return None
    return Observation(start, end, source, lat=latlng[0], lon=latlng[1])


# --- Google Maps Timeline (on-device export, 2024+) -------------------------


def _timeline_segments(segments: list, source: str) -> Iterator[Observation]:
    for seg in segments:
        if "startTime" not in seg:
            continue
        start, end = parse_time(seg["startTime"]), parse_time(seg.get("endTime", seg["startTime"]))
        if visit := seg.get("visit"):
            cand = visit.get("topCandidate", {})
            if o := _obs(start, end, parse_latlng(cand.get("placeLocation")), source):
                yield o
        if act := seg.get("activity"):
            for key, t in (("start", start), ("end", end)):
                if o := _obs(t, t, parse_latlng(act.get(key)), source):
                    yield o
        for p in seg.get("timelinePath", []):
            if "time" in p:
                t = parse_time(p["time"])
            else:  # iOS flavour stores an offset from the segment start
                t = start + timedelta(minutes=float(p.get("durationMinutesOffsetFromStartTime", 0)))
            if o := _obs(t, t, parse_latlng(p.get("point")), source):
                yield o


def _raw_signals(signals: list, source: str) -> Iterator[Observation]:
    for s in signals:
        pos = s.get("position")
        if pos and "timestamp" in pos:
            t = parse_time(pos["timestamp"])
            if o := _obs(t, t, parse_latlng(pos.get("LatLng")), source):
                yield o


# --- Google Takeout (legacy, pre-2024) --------------------------------------


def _takeout_records(locations: list, source: str) -> Iterator[Observation]:
    for loc in locations:
        if "timestamp" in loc:
            t = parse_time(loc["timestamp"])
        elif "timestampMs" in loc:
            t = datetime.fromtimestamp(int(loc["timestampMs"]) / 1000).astimezone()
        else:
            continue
        if o := _obs(t, t, parse_latlng(loc), source):
            yield o


def _takeout_semantic(objects: list, source: str) -> Iterator[Observation]:
    for obj in objects:
        if pv := obj.get("placeVisit"):
            d = pv.get("duration", {})
            if "startTimestamp" in d:
                o = _obs(parse_time(d["startTimestamp"]), parse_time(d["endTimestamp"]),
                         parse_latlng(pv.get("location", {})), source)
                if o:
                    yield o
        if seg := obj.get("activitySegment"):
            d = seg.get("duration", {})
            for key, tkey in (("startLocation", "startTimestamp"), ("endLocation", "endTimestamp")):
                if tkey in d:
                    t = parse_time(d[tkey])
                    if o := _obs(t, t, parse_latlng(seg.get(key, {})), source):
                        yield o


# --- Photos (osxphotos query --json) ----------------------------------------


def _photos(items: list, source: str) -> Iterator[Observation]:
    for p in items:
        if p.get("latitude") is None or not p.get("date"):
            continue
        t = parse_time(p["date"])
        yield Observation(t, t, source, lat=float(p["latitude"]), lon=float(p["longitude"]))


# --- CSV --------------------------------------------------------------------


def _csv(path: Path, source: str) -> Iterator[Observation]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.reader(f):
            row = [c.strip() for c in row]
            if len(row) < 2 or not row[0] or row[0].startswith("#") or not row[0][0].isdigit():
                continue  # blank, comment or header
            try:
                t = parse_time(row[0])
            except ValueError:
                continue
            if len(row) >= 3 and row[2]:
                latlng = parse_latlng(f"{row[1]},{row[2]}")
                if o := _obs(t, t, latlng, source):
                    yield o
            elif re.fullmatch(r"[A-Za-z]{2}", row[1]):
                # date,country override: covers the whole local day
                day = t.date() if isinstance(t, datetime) else t
                start = datetime.combine(day, datetime.min.time())
                yield Observation(start, start, source, country=row[1].upper())


# --- dispatch ---------------------------------------------------------------


def read_file(path: Path) -> Iterator[Observation]:
    source = path.name
    if path.suffix.lower() in (".csv", ".txt"):
        yield from _csv(path, source)
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        if "semanticSegments" in data or "rawSignals" in data:
            yield from _timeline_segments(data.get("semanticSegments", []), source)
            yield from _raw_signals(data.get("rawSignals", []), source)
        elif "locations" in data:
            yield from _takeout_records(data["locations"], source)
        elif "timelineObjects" in data:
            yield from _takeout_semantic(data["timelineObjects"], source)
        else:
            raise ValueError(f"{path}: unrecognised JSON layout")
    elif isinstance(data, list):
        if data and isinstance(data[0], dict) and "latitude" in data[0] and "date" in data[0]:
            yield from _photos(data, source)
        else:  # iOS Timeline export is a bare list of segments
            yield from _timeline_segments(data, source)


def read_paths(paths: list[Path]) -> list[Observation]:
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            files += sorted(f for f in p.rglob("*") if f.suffix.lower() in (".json", ".csv", ".txt"))
        else:
            files.append(p)
    out: list[Observation] = []
    for f in files:
        n = len(out)
        out.extend(read_file(f))
        print(f"  {f}: {len(out) - n} observations")
    return out


def local_days(o: Observation) -> list[date]:
    """Every local calendar day an observation touches (a 3-day stay = 3 days)."""
    d, last = o.start.date(), o.end.date()
    days = []
    while d <= last:
        days.append(d)
        d += timedelta(days=1)
    return days
