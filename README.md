# Public Courts Across London

A local planner for public tennis, squash and padel courts in London. It shows researched booking rules, indicative prices, evening suitability, maps and distance sorting. Its time-first view shows the most recently saved availability snapshot for supported venues; it does not book courts.

## Run locally

Use Node 24, then from this directory:

```sh
npm install
npm run dev
```

If `nodenv` has not put Node 24 on your path, run the dev command with:

```sh
PATH="/Users/wang_to/.nodenv/versions/24.18.1/bin:$PATH" npm run dev
```

`npm test` checks booking logic and the static-data joins. `npm run build` checks the production build.

## Static data

`data/venues.json` is the central venue directory. Each venue has a stable `id`, name, borough, area, sport, booking link and source references. `data/prices.json` and `data/coordinates.json` join to it by that ID. `app/booking.ts` parses the three files into complete venue objects and creates the card labels from structured fields.

Every venue ID must have an entry in both joined files. A `null` price entry means no **structured tariff** has been recorded; older venue notes may still contain price text. A `null` coordinate entry means a map pin has not been verified. The parser rejects duplicate IDs, stray price or coordinate IDs, and missing entries.

Published prices are individual rates with `amount_gbp`, `duration_minutes`, applicable `modes`, and, where standardized, `customer` and `time_band`. The card's indicative range uses applicable rates of the same duration; it does not estimate an unpublished price.

The collected source records live one directory up in `data/research/`. After editing them, rebuild and copy the app snapshot:

```sh
cd ..
python3 scripts/build_directory.py
cp data/london-racquet-venues.json site/data/venues.json
```

When adding a venue, add its ID to both `site/data/prices.json` (use `null` if no structured price is known) and `site/data/coordinates.json` (use `null` if no reliable pin is known), then run `npm test` from `site/`.

Run `.venv/bin/python scripts/provider_inventory.py` to rebuild the [metadata-refresh coverage report](docs/provider-coverage.md) and [per-venue source inventory](docs/provider-inventory.json). The report keeps the configured metadata source family separate from the booking-link hostname.

## Metadata ingestion foundation

`config/venues.yaml` is the curated registry of venue IDs, sports, source adapters, booking links and metadata-source links. It was initially seeded from the existing site data; `provider: html` means the underlying booking system has not been confirmed. Observed facts belong in the provider-independent types in `ingestion/models.py`, not in the registry.

The Python setup is local:

```sh
uv sync
.venv/bin/python -m unittest discover -s tests -v
```

The ClubSpark pilot fetches public HTML and previews a normalized metadata patch for one registry venue:

```sh
.venv/bin/python -m ingestion.providers.clubspark hammersmith-and-fulham-brook-green-tennis
```

Its parser is fixture-tested against Brook Green Tennis, Finsbury Park and Cottenham Park. The source pages are saved in `tests/fixtures/` (with form tokens redacted). Unclear price duration and conflicting booking windows or release clocks remain unknown. The preview does not change the app's JSON; validation and diffing are the next ingestion milestone.

The OpenActive pilot reads a curated Better `FacilityUse` item for Gunnersbury tennis or Finsbury squash and emits the same patch shape:

```sh
.venv/bin/python -m ingestion.providers.openactive hounslow-gunnersbury-park-sports-hub
```

It records individual-court count and common court hours from the public JSON. It does not infer price, booking window or slot duration. The saved Better fixtures are CC-BY 4.0; display use requires attribution to Better.

`ingestion.review.review_metadata(existing, candidate)` validates a refreshed record and returns field-level changes. Invalid values and disappearance of previously known values make `safe_to_apply` false; `format_review(...)` produces a local text report. This layer does not write or accept changes.

## Refresh metadata

Run the supported pilot venues with the Python interpreter:

```sh
.venv/bin/python scripts/refresh_metadata.py
```

The script fetches the three tested ClubSpark venues and two mapped Better OpenActive venues, applies only the fields present in each patch, prints the change report, and atomically writes `data/ingestion-metadata.json`. Invalid responses abort the run. Omitted fields retain their saved values; explicit collection shrinkage is blocked. The frontend JSON is not changed.

## Availability pilot

Refresh the next seven days of configured Better availability with:

```bash
.venv/bin/python scripts/refresh_availability.py
```

The first pilot reads Gunnersbury's public date-scoped booking JSON and atomically writes provider-independent slots to `data/availability.json`. The site's **Find a time** view matches the selected date, exact start time and duration, shows the snapshot's check time, and links to Better for the actual booking. Only Gunnersbury is checked; other venues remain visibly unverified. Run the refresh again and rebuild/redeploy the site to publish newer slots. The script is not scheduled, so saved slots can become stale.
