"""Turn located observations into one record per calendar day."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from .sources import Observation, local_days

DAY_END = 24 * 3600


@dataclass
class Day:
    date: date
    countries: set[str] = field(default_factory=set)  # every country seen that day
    first: str | None = None  # country of the earliest observation
    last: str | None = None  # country of the latest observation (~ where you slept)
    sources: set[str] = field(default_factory=set)
    inferred: bool = False  # filled in from neighbouring days, not observed
    override: bool = False  # set by a date,country CSV row

    def counted(self, rule: str) -> set[str]:
        """Countries this day counts towards. 'presence': any time there; 'night': where the day ended."""
        if rule == "night" and self.last:
            return {self.last}
        return set(self.countries)


def _secs(t) -> int:
    return t.hour * 3600 + t.minute * 60 + t.second


def build_days(observations: list[Observation], countries: list[str | None]) -> dict[date, Day]:
    # (earliest, latest) time-of-day per day and country
    spans: dict[date, dict[str, list[int]]] = defaultdict(dict)
    sources: dict[date, set[str]] = defaultdict(set)
    overrides: dict[date, set[str]] = defaultdict(set)

    for o, code in zip(observations, countries):
        if o.country:
            overrides[o.start.date()].add(o.country)
            continue
        if not code:
            continue
        for d in local_days(o):
            lo = _secs(o.start) if d == o.start.date() else 0
            hi = _secs(o.end) if d == o.end.date() else DAY_END
            span = spans[d].setdefault(code, [lo, hi])
            span[0], span[1] = min(span[0], lo), max(span[1], hi)
            sources[d].add(o.source)

    days: dict[date, Day] = {}
    for d, by_country in spans.items():
        days[d] = Day(
            d,
            countries=set(by_country),
            first=min(by_country, key=lambda c: by_country[c][0]),
            last=max(by_country, key=lambda c: by_country[c][1]),
            sources=sources[d],
        )
    for d, codes in overrides.items():
        only = sorted(codes)[0] if len(codes) == 1 else None
        days[d] = Day(d, countries=codes, first=only, last=only, sources={"override"}, override=True)
    return days


def fill_gaps(days: dict[date, Day], max_gap: int) -> None:
    """Fill runs of up to max_gap missing days when you ended in the same country you
    were next seen in (e.g. a weekend at home with no photos)."""
    if max_gap <= 0 or not days:
        return
    known = sorted(days)
    for prev, nxt in zip(known, known[1:]):
        gap = (nxt - prev).days - 1
        if 0 < gap <= max_gap and days[prev].last and days[prev].last == days[nxt].first:
            code = days[prev].last
            for i in range(1, gap + 1):
                d = prev + timedelta(days=i)
                days[d] = Day(d, countries={code}, first=code, last=code, inferred=True)


def max_window(days: dict[date, Day], code: str, rule: str, window: int, until: date) -> tuple[int, date | None, int]:
    """(most days in `code` in any `window`-day span ending on that date, end of that span,
    days in `code` in the span ending on `until`)."""
    hits = sorted(d for d, day in days.items() if code in day.counted(rule) and d <= until)
    best, best_end, lo = 0, None, 0
    for hi, d in enumerate(hits):
        while hits[lo] <= d - timedelta(days=window):
            lo += 1
        if hi - lo + 1 > best:
            best, best_end = hi - lo + 1, d
    current = sum(1 for d in hits if d > until - timedelta(days=window))
    return best, best_end, current
