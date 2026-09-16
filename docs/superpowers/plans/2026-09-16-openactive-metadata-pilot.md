# OpenActive Metadata Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Normalize two verified Better FacilityUse items into the canonical metadata model without modifying site data.

**Architecture:** Add each direct item URL to the curated registry. One OpenActive source validates the RPDE item and parses the embedded FacilityUse; its fetch and parser are fixture-tested offline.

**Tech Stack:** Python standard-library `json`, `urllib`, `datetime`, `asyncio`, `unittest`; existing PyYAML registry.

**Spec:** `docs/superpowers/specs/2026-09-16-openactive-metadata-pilot.md`

## Global Constraints

- Work only in `metadata-openactive-m4`; no merge, push, availability or site JSON write.
- Unknown values remain unknown; do not infer price or booking duration from labels.
- Use individual-court hours, not parent-place hours.

---

### Task 1: Curated item mapping and parser

**Files:** `config/venues.yaml`, `tests/fixtures/better_*.json`, `tests/test_openactive.py`, `ingestion/providers/openactive.py`.

**Interfaces:** `parse_facility_use(venue: Venue, item: dict, source_url: str, checked_at: datetime) -> VenueMetadata`.

- [x] Save direct current Better item responses for Gunnersbury FacilityUse `activity_recurrence_group:11612` and Finsbury squash FacilityUse `activity_recurrence_group:2914`; add their `@id` URLs to those registry entries.
- [x] Write fixture tests for court counts 8 and 4, sport/identity validation, Gunnersbury floodlights, common per-court weekly hours, observed booking URL, and unknown price/window/duration. Add a deleted-item and mixed-hours test.
- [x] Run `.venv/bin/python -m unittest discover -s tests -p 'test_openactive.py' -v` and observe failure because the adapter is absent.
- [x] Implement the minimum validated JSON normalization that passes those tests, then rerun them.

### Task 2: Source fetch and local preview

**Files:** `ingestion/providers/openactive.py`, `tests/test_openactive.py`, `README.md`.

**Interfaces:** `OpenActiveSource.fetch_metadata(venue: Venue) -> VenueMetadata`; `.venv/bin/python -m ingestion.providers.openactive hounslow-gunnersbury-park-sports-hub`.

- [x] Write a test that the source fetches its curated item URL once and rejects a venue without one before fetching.
- [x] Run the test red, add timeout-limited JSON GET and one-venue preview, then run it green.
- [x] Run the full Python and Node 24 site suites, `git diff --check`, and the live preview. Commit on the worktree branch only; leave it available for review.
