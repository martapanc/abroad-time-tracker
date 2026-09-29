# abroad

Counts how many days per year you spent in each country — built for keeping an eye on
Andorra residency/visa day counts — from location data you already have. No manual trip entry.

Everything runs locally. Your location files live in `data/`, which is git-ignored.

## Quick start

```sh
uv sync
# put exports into data/ (see below), then:
uv run abroad report --window 180 --html calendar.html
open calendar.html
```

The report prints days per country per year (Andorra highlighted), how many days have no
data, and optionally a rolling window. `calendar.html` shows each day coloured by country.

## Getting your data

Drop any of these into `data/`. Formats are detected automatically, and sources are combined.

**1. Google Maps Timeline** (best source for the past, if you had Timeline on)
- iPhone: Google Maps → your profile → Settings → Personal content → *Export Timeline data*
- Android: phone Settings → Location → Location services → Timeline → *Export Timeline data*
- Old Google Takeout exports (`Records.json`, `Semantic Location History/*.json`) work too.

**2. Photo geotags** (fills gaps; any day you took a photo)
```sh
uv run abroad export-photos      # writes data/photos.json via osxphotos
```
macOS may ask to give your terminal access to Photos (or Full Disk Access).

**3. Daily iPhone Shortcut** (going forward: one reliable point every day)

In the Shortcuts app → Automation → **+** → *Time of Day*, 23:30, Daily, *Run Immediately*:
1. **Get Current Location**
2. **Format Date** — Current Date, format *ISO 8601*, include time ✓
3. **Text**: `Formatted Date,Latitude,Longitude` (insert Latitude/Longitude as variables from
   the Current Location — tap the variable and pick the detail)
4. **Append to Text File** — the Text, file `Shortcuts/abroad-log.csv`, *Make New Line* ✓

Then copy/symlink `iCloud Drive/Shortcuts/abroad-log.csv` into `data/` (on a Mac it's under
`~/Library/Mobile Documents/iCloud~is~workflow~my~workflows/Documents/`).

**4. Manual overrides** (optional, for days you know but have no data for)

A CSV of `date,country` rows, e.g. `2025-02-14,AD`. An override replaces whatever else was seen that day.

## How days are counted

- `--rule presence` (default): a day counts for every country you were in, even briefly.
  A day driving from Andorra to Barcelona counts for both.
- `--rule night`: a day counts only for the country where it ended (roughly, where you slept).
- `--fill-gaps N` (default 3): up to N days with no data are filled in when you were in the
  same country on both sides (e.g. a quiet weekend at home). Shown separately as *inferred*.
  Use `--fill-gaps 0` to count only observed days.
- `--window 180`: days in the focus country in the last 180 days, and the highest ever.

Which rule applies to you depends on which Andorran requirement you're checking (e.g.
residency vs. tax residency) — confirm the exact definition with your gestor or the
immigration office.

Country borders: Natural Earth (1:10m) worldwide, plus the precise OpenStreetMap outline
for Andorra so border spots like Pas de la Casa are placed correctly. Border files are
downloaded once into `~/.cache/abroad/`.

## Tests

```sh
uv run pytest
```
