# Public Courts Across London

A local planner for public tennis, squash and padel courts in London. It shows researched booking rules, indicative prices, evening suitability, maps and distance sorting. It does not show live court availability or make bookings.

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
