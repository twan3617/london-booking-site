# ClubSpark Metadata Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Fetch and normalize explicit public metadata for three real ClubSpark tennis venues without writing site data.

**Architecture:** One ClubSpark source implements the existing metadata capability. Its HTML-to-text parser feeds narrow field extractors and returns the canonical model. Raw page fixtures make parsing testable offline.

**Tech Stack:** Python 3.11+, standard-library `urllib`, `html.parser`, `asyncio`, `unittest`; existing PyYAML registry.

**Spec:** `docs/superpowers/specs/2026-09-15-clubspark-metadata-pilot.md`

## Global Constraints

- No availability or booking automation.
- No site JSON updates or remote Git operations.
- Unknown fields remain unknown; no inferred price unit or release clock.

---

### Task 1: Fixture-driven parser

**Files:** Create `tests/fixtures/clubspark_*.html`, `tests/test_clubspark.py`, `ingestion/providers/clubspark.py`; modify `ingestion/models.py` for `floodlit_court_count`.

**Interfaces:** `parse_clubspark(venue: Venue, html: str, checked_at: datetime) -> VenueMetadata`.

- [x] Save the three current public HTML pages as fixtures.
- [x] Write tests asserting Brook Green 14 days/10:15/three floodlit courts, Finsbury Park seven days/midnight/six floodlit courts, and Cottenham Park one day/22:00/six hard courts. Assert unspecified values stay `None` or empty.
- [x] Run `.venv/bin/python -m unittest discover -s tests -p 'test_clubspark.py' -v` and observe failure because `parse_clubspark` is missing.
- [x] Add the minimum HTML text extraction and anchored patterns that pass those tests.
- [x] Rerun the fixture tests.

### Task 2: Public-page fetch and preview

**Files:** Modify `ingestion/providers/clubspark.py`, `tests/test_clubspark.py`, `README.md`.

**Interfaces:** `ClubSparkSource.fetch_metadata(venue: Venue) -> VenueMetadata`; run `python -m ingestion.providers.clubspark VENUE_ID` for a local preview.

- [x] Write a test that non-ClubSpark venues are rejected before an HTTP request and a test that a provided fixture fetch returns normalized metadata.
- [x] Run the test and observe failure.
- [x] Implement a timeout-limited public GET with the standard library and a preview that prints one normalized record.
- [x] Run the full Python and site tests, then run the preview for one pilot venue.

### Task 3: Review and local integration

**Files:** All above.

- [x] Check fixture dates and source URLs, `git diff --check`, and that site JSON did not change.
- [x] Commit on the local feature branch and fast-forward `main` locally after tests pass.
