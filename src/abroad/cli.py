import argparse
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

from .days import build_days, fill_gaps
from .geo import OSM_RELATIONS, CountryLookup
from .report import print_summary, write_html
from .sources import read_paths


def cmd_report(args) -> None:
    print("Reading:")
    observations = read_paths(args.paths)
    if not observations:
        sys.exit("No observations found.")

    print(f"Locating {len(observations)} observations ...")
    focus_borders = dict(OSM_RELATIONS)
    for item in args.hires:
        code, _, relation = item.partition("=")
        focus_borders[code.upper()] = int(relation)
    lookup = CountryLookup(focus=focus_borders)
    located = [o for o in observations if o.lat is not None]
    codes = iter(lookup.lookup_many([(o.lat, o.lon) for o in located]))
    countries = [next(codes) if o.lat is not None else None for o in observations]

    days = build_days(observations, countries)
    fill_gaps(days, args.fill_gaps)
    until = date.fromisoformat(args.until) if args.until else date.today()
    days = {d: v for d, v in days.items() if d <= until and (not args.year or d.year in args.year)}

    focus = args.country.upper() if args.country else None
    print_summary(days, args.rule, lookup.name, focus, args.window, until)
    if args.html:
        write_html(args.html, days, args.rule, lookup.name, focus, until)
        print(f"Calendar written to {args.html}")


def cmd_export_photos(args) -> None:
    """Dump geotagged photo metadata from the macOS Photos library via osxphotos."""
    runner = ["osxphotos"] if shutil.which("osxphotos") else ["uvx", "osxphotos"]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    print(f"Running {' '.join(runner)} query --location --json (can take a few minutes) ...")
    with args.out.open("w") as f:
        subprocess.run([*runner, "query", "--location", "--json"], stdout=f, check=True)
    print(f"Wrote {args.out}")


def main() -> None:
    p = argparse.ArgumentParser(prog="abroad", description="Count days per year in each country from location exports.")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("report", help="summarise days per country")
    r.add_argument("paths", nargs="*", type=Path, default=[Path("data")], help="files or folders (default: data/)")
    r.add_argument("--country", default="AD", help="country to highlight, ISO alpha-2 (default: AD)")
    r.add_argument("--rule", choices=["presence", "night"], default="presence",
                   help="presence: any time in a country counts that day (default); night: only where the day ended")
    r.add_argument("--fill-gaps", type=int, default=3, metavar="N",
                   help="infer up to N missing days between days that agree (default 3, 0 = off)")
    r.add_argument("--window", type=int, metavar="DAYS", help="also report a rolling window, e.g. 180")
    r.add_argument("--year", type=int, action="append", help="only these years (repeatable)")
    r.add_argument("--until", help="ignore data after this date (YYYY-MM-DD, default today)")
    r.add_argument("--html", type=Path, help="write a calendar view to this HTML file")
    r.add_argument("--hires", nargs="*", default=[], metavar="CODE=OSM_RELATION",
                   help="extra countries to use precise OpenStreetMap borders for, as CODE=RELATION_ID (AD is built in)")
    r.set_defaults(func=cmd_report)

    e = sub.add_parser("export-photos", help="export photo geotags from the macOS Photos library")
    e.add_argument("--out", type=Path, default=Path("data/photos.json"))
    e.set_defaults(func=cmd_export_photos)

    args = p.parse_args()
    args.func(args)
