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

Refresh the next seven days of configured Better availability locally with:

```bash
.venv/bin/python scripts/refresh_availability.py
```

The Better pilot reads public date-scoped booking JSON for Charlton Lido, Gunnersbury Park, Highbury Fields and Finsbury Leisure Centre, then atomically writes provider-independent slots to the ignored local file `data/availability.json`. The site's **Find a time** view fetches the latest published snapshot from `/.netlify/functions/availability` when opened, every five minutes while visible, and when the tab becomes visible again. It shows checked days as columns and start times as rows; selecting a cell lists locations with free courts at that exact start time and duration, along with booking links. Tennis uses 60-minute slots and Finsbury squash uses 40-minute slots. The view shows the snapshot's check time and coverage; after two hours it hides stale slot counts. Other venues remain visibly unverified.

On the deployed Netlify site, the read-only function serves the `latest` key in the site-wide `court-availability` Blob store. The hourly GitHub Actions workflow runs the existing Python scraper and `scripts/publish_availability.mjs`; a failed or empty refresh does not replace the previous snapshot. Set GitHub Actions repository secrets `NETLIFY_SITE_ID` (Netlify project ID) and `NETLIFY_AUTH_TOKEN` (a Netlify personal access token with access to that project), then run **Refresh court availability** once with **Run workflow** to publish the first snapshot. The workflow must be on the repository's default branch to run on schedule. New snapshots do not commit data or rebuild the site; only changes to the site code or function require a Netlify deploy.

### Activate snapshot refresh on Netlify

1. Deploy this code to your existing Netlify project once, including `netlify/functions/availability.mjs`.
2. In Netlify, copy **Project configuration → General → Project information → Project ID**. This is the value for `NETLIFY_SITE_ID`; the ID in `.openai/hosting.json` belongs to a different hosting service.
3. Create a Netlify personal access token under **User settings → Applications → Personal access tokens**.
4. In the GitHub repository, open **Settings → Secrets and variables → Actions** and create repository secrets named `NETLIFY_SITE_ID` and `NETLIFY_AUTH_TOKEN` with those values. Keep the token in secrets, never in source code or browser configuration.
5. Once the workflow is on the default branch, open **Actions → Refresh court availability → Run workflow**. Its first successful upload creates the store and snapshot automatically.
6. Open `https://YOUR-NETLIFY-DOMAIN/.netlify/functions/availability`. It should return JSON with a recent `generated_at`. Then open **Find a time** on the site.

After setup, the workflow refreshes hourly and the open time view polls every five minutes. GitHub scheduled runs can be delayed. If refresh fails, the previous snapshot remains stored; the page hides counts once they are over two hours old.

`npm run dev` runs the frontend only and does not serve the Netlify function. Local scraping still writes the ignored JSON for inspection; it does not publish it. Use the local integration preview below to test storage-to-browser behaviour without deploying. Cloud credentials and the scheduled job still need a separate check when deployment is enabled.

### Local integration preview (synthetic data)

The intended hosted flow (deployment and scheduled refreshes are currently inactive):

```mermaid
flowchart TD
  APIs[Booking provider APIs] -->|Availability responses| Scraper[Python scraper running in GitHub Actions]
  Scraper -->|Validate and upload JSON| Blobs[Netlify Blobs: latest snapshot]
  Blobs -->|Read stored JSON| Function[Read-only Netlify function]
  Function -->|JSON on each browser fetch| Grid[Availability grid in the browser]
  Catalogue[Catalogue JSON shipped with the website] -->|Names, locations and other metadata| Grid
  Grid -->|User follows booking link| Booking[Provider booking website]
```

The local preview replaces the provider calls and scheduled scraper with manual sample updates, and Netlify Blobs with its local emulator. The function and browser use the production code. Fetches happen when the time view opens, every five minutes while visible, and when the browser tab becomes visible again. Receiving new JSON updates the grid without rebuilding or reloading the website. Failed fetches retain the previous snapshot with a warning; counts older than two hours are hidden.

With Node 24, run from this directory:

```sh
npx next build
node scripts/preview_availability.mjs
```

Open `http://127.0.0.1:3100` and choose **Find a time**. The preview uses the installed Netlify SDK's local Blob server, temporary storage, our actual availability function, and the built website. It first asserts that the function returns 503 for missing data and reads updated snapshots without caching. No Netlify credentials, provider calls, uploads, deployments, or GitHub jobs are used. The displayed courts and prices are synthetic test data.

Type a scenario in the terminal:

| Command | Expected behaviour after the next browser fetch |
| --- | --- |
| `fresh` | One location with two sample courts |
| `changed` | Same location with one sample court |
| `missing` | Function returns 503; a previously loaded snapshot remains with a refresh warning |
| `invalid` | Malformed data is rejected; the previous snapshot remains with a warning |
| `stale` | Three-hour-old snapshot hides counts and displays an expiry message |
| `quit` | Stops the preview and removes its temporary Blob storage |

The open, visible time view polls every five minutes. Switching away to another browser tab and returning also fetches the latest snapshot without reloading the page. For a first-load failure check, use `missing` and then reload the browser: the time view should show availability unavailable.

References: [Netlify Blobs setup and project ID](https://docs.netlify.com/build/data-and-storage/netlify-blobs/), [GitHub Actions secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets).

The ClubSpark adapter is a local pilot: `ingestion/providers/clubspark_availability.py` expands `Category: 0` booking-sheet ranges into individual slots. It has no live fetcher configured and is not included in the refresh script or published snapshot. ClubSpark slots, if later published, link to the selected booking date and tell visitors they need a ClubSpark account to book.
