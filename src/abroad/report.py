"""Terminal summary and a self-contained HTML calendar."""

import calendar
import colorsys
import html
from collections import Counter, defaultdict
from datetime import date, timedelta

from .days import Day, max_window


def yearly(days: dict[date, Day], rule: str) -> dict[int, dict[str, Counter]]:
    """year -> {"observed": Counter(country), "inferred": Counter(country)}"""
    out: dict[int, dict[str, Counter]] = defaultdict(lambda: {"observed": Counter(), "inferred": Counter()})
    for d, day in days.items():
        kind = "inferred" if day.inferred else "observed"
        for c in day.counted(rule):
            out[d.year][kind][c] += 1
    return out


def missing_days(days: dict[date, Day], year: int, until: date) -> int:
    start, end = date(year, 1, 1), min(date(year, 12, 31), until)
    return sum(1 for i in range((end - start).days + 1) if start + timedelta(days=i) not in days)


def print_summary(days, rule, name, focus: str | None, window: int | None, until: date) -> None:
    by_year = yearly(days, rule)
    print(f"\nDays per country (rule: {rule}; 'inferred' = gap filled from neighbouring days)\n")
    for year in sorted(by_year):
        obs, inf = by_year[year]["observed"], by_year[year]["inferred"]
        total = obs + inf
        print(f"{year}  (days with no data: {missing_days(days, year, until)})")
        for code, n in total.most_common():
            mark = "  <--" if code == focus else ""
            extra = f"  ({obs[code]} observed + {inf[code]} inferred)" if inf[code] else ""
            print(f"   {code}  {name(code):<24} {n:>4}{extra}{mark}")
        print()

    if focus and window:
        best, best_end, current = max_window(days, focus, rule, window, until)
        print(f"{name(focus)}, rolling {window}-day window:")
        print(f"   last {window} days up to {until}: {current} days")
        if best_end:
            print(f"   highest ever: {best} days (window ending {best_end})")
        print()


def _palette(codes: list[str], focus: str | None) -> dict[str, str]:
    colors = {}
    others = [c for c in codes if c != focus]
    for i, c in enumerate(others):
        r, g, b = colorsys.hls_to_rgb((0.55 + i * 0.618) % 1, 0.62, 0.45)
        colors[c] = f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"
    if focus:
        colors[focus] = "#d6452c"
    return colors


def write_html(path, days, rule, name, focus: str | None, until: date) -> None:
    by_year = yearly(days, rule)
    codes = [c for c, _ in sum((v["observed"] + v["inferred"] for v in by_year.values()), Counter()).most_common()]
    colors = _palette(codes, focus)
    e = html.escape

    parts = []
    for year in sorted(by_year, reverse=True):
        total = by_year[year]["observed"] + by_year[year]["inferred"]
        chips = "".join(
            f'<span class="chip"><i style="background:{colors[c]}"></i>{e(name(c))} <b>{n}</b></span>'
            for c, n in total.most_common()
        )
        chips += f'<span class="chip"><i class="none"></i>No data <b>{missing_days(days, year, until)}</b></span>'
        months = []
        for m in range(1, 13):
            cells = ['<span class="pad"></span>'] * calendar.monthrange(year, m)[0]
            for dnum in range(1, calendar.monthrange(year, m)[1] + 1):
                d = date(year, m, dnum)
                day = days.get(d)
                if d > until:
                    cells.append('<span class="future"></span>')
                elif not day:
                    cells.append(f'<span class="none" title="{d}: no data"></span>')
                else:
                    cs = sorted(day.counted(rule), key=codes.index)
                    stops = ", ".join(
                        f"{colors[c]} {i * 100 / len(cs):.0f}% {(i + 1) * 100 / len(cs):.0f}%" for i, c in enumerate(cs)
                    )
                    label = " + ".join(name(c) for c in cs)
                    how = "inferred" if day.inferred else ("override" if day.override else ", ".join(sorted(day.sources)))
                    cls = ' class="inf"' if day.inferred else ""
                    cells.append(
                        f'<span{cls} style="background:linear-gradient(135deg,{stops})" title="{d}: {e(label)} ({e(how)})"></span>'
                    )
            months.append(f'<div class="month"><h4>{calendar.month_abbr[m]}</h4><div class="grid">{"".join(cells)}</div></div>')
        parts.append(f'<section><h2>{year}</h2><div class="chips">{chips}</div><div class="months">{"".join(months)}</div></section>')

    path.write_text(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Days Per Country</title>
<style>
:root {{ --bg:#fbfaf8; --fg:#1d1d1f; --muted:#6e6e73; --none:#e7e5e1; --card:#fff; --line:#e5e3df; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#161618; --fg:#f2f2f2; --muted:#9a9aa0; --none:#2c2c30; --card:#1f1f22; --line:#303034; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; padding:24px 16px 48px; background:var(--bg); color:var(--fg); font:15px/1.45 -apple-system,system-ui,sans-serif; }}
main {{ max-width:1080px; margin:0 auto; }}
h1 {{ font-size:24px; margin:0 0 4px; }} .sub {{ color:var(--muted); margin:0 0 24px; }}
section {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:18px; margin-bottom:18px; }}
h2 {{ margin:0 0 10px; font-size:20px; }}
.chips {{ display:flex; flex-wrap:wrap; gap:8px 16px; margin-bottom:14px; }}
.chip {{ display:inline-flex; align-items:center; gap:6px; }} .chip b {{ font-variant-numeric:tabular-nums; }}
.chip i {{ width:12px; height:12px; border-radius:3px; display:inline-block; }}
.months {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:14px; }}
.month h4 {{ margin:0 0 4px; font-size:12px; color:var(--muted); font-weight:600; }}
.grid {{ display:grid; grid-template-columns:repeat(7,1fr); gap:2px; }}
.grid span {{ aspect-ratio:1; border-radius:3px; }}
.none {{ background:var(--none); }} .future, .pad {{ background:transparent; }}
.inf {{ opacity:.45; }}
</style></head><body><main>
<h1>Days per country</h1>
<p class="sub">Rule: <b>{e(rule)}</b>. Faded squares are inferred from the days either side; grey means no data. Hover a day for details.</p>
{"".join(parts)}
</main></body></html>
""")
