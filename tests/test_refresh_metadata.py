import asyncio
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from datetime import datetime, time, timezone
from pathlib import Path
from unittest.mock import patch as mock_patch

from ingestion.models import MetadataField, MetadataPatch, Venue, VenueMetadata, apply_metadata_patch
from scripts.refresh_metadata import load_snapshot, main, refresh_metadata


API_SOURCE = "https://api.example.org/source"
AVAILABILITY_SOURCE = "https://api.example.org/availability"
VENUE = Venue(
    id="example-court",
    name="Example Court",
    sport="tennis",
    provider="clubspark",
    booking_url="https://example.org/book",
    metadata_sources=("https://example.org/source", API_SOURCE),
    availability_urls=(AVAILABILITY_SOURCE,),
)


def metadata(**changes):
    value = VenueMetadata(
        venue_id=VENUE.id,
        name=VENUE.name,
        booking_url=VENUE.booking_url,
        last_checked=datetime(2026, 9, 16, 12, tzinfo=timezone.utc),
        source_url=VENUE.metadata_sources[0],
        court_count=3,
        surface=("hard",),
        booking_window_days=7,
    )
    return replace(value, **changes)


def patch(checked_at=None, source_url=None, **values):
    return MetadataPatch(
        venue_id=VENUE.id,
        source_url=source_url or VENUE.metadata_sources[0],
        checked_at=checked_at or datetime(2026, 9, 16, 12, tzinfo=timezone.utc),
        values={MetadataField(field): value for field, value in values.items()},
    )


class StaticSource:
    def __init__(self, value):
        self.value = value

    async def fetch_metadata(self, venue):
        return self.value


class FailingSource:
    async def fetch_metadata(self, venue):
        raise RuntimeError("provider unavailable")


class RefreshMetadataTests(unittest.TestCase):
    def test_patch_updates_only_observed_fields(self):
        existing = metadata(court_count=3, surface=("hard",))
        patch = MetadataPatch(
            venue_id=VENUE.id,
            source_url=VENUE.metadata_sources[0],
            checked_at=datetime(2026, 9, 17, 12, tzinfo=timezone.utc),
            values={MetadataField.COURT_COUNT: 4},
        )

        updated = apply_metadata_patch(VENUE, patch, existing)

        self.assertEqual(updated.court_count, 4)
        self.assertEqual(updated.surface, ("hard",))
        self.assertEqual(updated.source_url, patch.source_url)
        self.assertEqual(updated.last_checked, patch.checked_at)

    def test_patch_inherits_latest_registry_identity(self):
        existing = metadata(name="Old name", booking_url="https://example.org/old-booking")
        renamed = replace(VENUE, name="Renamed Court", booking_url="https://example.org/new-booking")

        updated = apply_metadata_patch(renamed, patch(court_count=4), existing)

        self.assertEqual(updated.name, renamed.name)
        self.assertEqual(updated.booking_url, renamed.booking_url)

    def test_patch_rejects_unstandardized_field_names(self):
        with self.assertRaisesRegex(ValueError, "MetadataField"):
            MetadataPatch(
                venue_id=VENUE.id,
                source_url=VENUE.metadata_sources[0],
                checked_at=datetime(2026, 9, 17, 12, tzinfo=timezone.utc),
                values={"court_count": 4},
            )

    def test_patch_rejects_mismatched_venue_or_unregistered_source(self):
        with self.assertRaisesRegex(ValueError, "venue ID mismatch"):
            apply_metadata_patch(VENUE, MetadataPatch(
                venue_id="different-court",
                source_url=VENUE.metadata_sources[0],
                checked_at=datetime(2026, 9, 17, 12, tzinfo=timezone.utc),
                values={},
            ))
        with self.assertRaisesRegex(ValueError, "not registered"):
            apply_metadata_patch(VENUE, MetadataPatch(
                venue_id=VENUE.id,
                source_url="https://unregistered.example/source",
                checked_at=datetime(2026, 9, 17, 12, tzinfo=timezone.utc),
                values={},
            ))

    def test_first_refresh_writes_canonical_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "metadata.json"
            initial = patch(court_count=3, surface=("hard",), booking_window_days=7)
            reports, failures = asyncio.run(refresh_metadata((VENUE,), {VENUE.id: StaticSource(initial)}, output))
            saved = load_snapshot(output)[VENUE.id]
            self.assertEqual((saved.court_count, saved.surface, saved.booking_window_days), (3, ("hard",), 7))
            self.assertEqual(reports, ("Example Court\nNew metadata record.",))
            self.assertEqual(failures, ())
            document = json.loads(output.read_text())
            self.assertEqual(document["venues"][0]["last_checked"], "2026-09-16T12:00:00+00:00")

    def test_failed_venue_keeps_its_snapshot_while_another_refreshes(self):
        other = replace(VENUE, id="other-court", name="Other Court")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "metadata.json"
            asyncio.run(refresh_metadata((VENUE,), {VENUE.id: StaticSource(patch(court_count=3))}, output))
            other_patch = MetadataPatch(
                other.id,
                other.metadata_sources[0],
                datetime(2026, 9, 17, 12, tzinfo=timezone.utc),
                {MetadataField.COURT_COUNT: 2},
            )

            reports, failures = asyncio.run(refresh_metadata(
                (VENUE, other),
                {VENUE.id: FailingSource(), other.id: StaticSource(other_patch)},
                output,
            ))

            saved = load_snapshot(output)
            self.assertEqual(saved[VENUE.id].court_count, 3)
            self.assertEqual(saved[other.id].court_count, 2)
            self.assertEqual(len(reports), 1)
            self.assertEqual(failures, (f"{VENUE.id}: provider unavailable",))

    def test_all_failures_do_not_create_an_empty_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "metadata.json"

            reports, failures = asyncio.run(refresh_metadata(
                (VENUE,), {VENUE.id: FailingSource()}, output
            ))

            self.assertEqual(reports, ())
            self.assertEqual(failures, (f"{VENUE.id}: provider unavailable",))
            self.assertFalse(output.exists())

    def test_cli_lists_providers_and_plans_without_fetching(self):
        listed = io.StringIO()
        with redirect_stdout(listed):
            main(["--list"])
        self.assertEqual(listed.getvalue().splitlines(), ["clubspark", "everyoneactive", "openactive", "placesleisure"])

        planned = io.StringIO()
        with redirect_stdout(planned):
            main(["--provider", "everyoneactive", "--plan"])
        self.assertIn("everyoneactive: 4 venues, 10s pacing, request limit 4", planned.getvalue())

    def test_cli_skips_clubspark_when_lta_is_disabled(self):
        planned = io.StringIO()
        with redirect_stdout(planned):
            main(["--all", "--plan"])
        self.assertNotIn("clubspark", planned.getvalue())
        with mock_patch("scripts.refresh_metadata.CLUBSPARK.fetch_metadata", side_effect=AssertionError("LTA request made")) as lta:
            with self.assertRaisesRegex(ValueError, "LTA metadata is disabled"):
                main(["--provider", "clubspark"])
            lta.assert_not_called()

    def test_cli_can_include_clubspark_when_lta_is_enabled(self):
        with tempfile.TemporaryDirectory() as directory:
            setting = Path(directory) / "availability.json"
            setting.write_text('{"lta_enabled": true}')
            planned = io.StringIO()
            with mock_patch("scripts.refresh_metadata.SETTINGS_PATH", setting), redirect_stdout(planned):
                main(["--all", "--plan"])
            self.assertIn("clubspark: 4 venues", planned.getvalue())

    def test_multiple_sources_fill_gaps_and_later_api_values_win(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "metadata.json"
            html = StaticSource(patch(court_count=3, surface=("hard",), booking_window_days=7))
            api = StaticSource(patch(source_url=API_SOURCE, court_count=4))

            asyncio.run(refresh_metadata((VENUE,), {VENUE.id: (html, api)}, output))

            saved = load_snapshot(output)[VENUE.id]
            self.assertEqual((saved.court_count, saved.surface, saved.booking_window_days), (4, ("hard",), 7))
            self.assertEqual(saved.source_url, API_SOURCE)

    def test_registered_availability_api_can_supply_metadata(self):
        observed = apply_metadata_patch(VENUE, patch(source_url=AVAILABILITY_SOURCE, slot_duration_minutes=60))

        self.assertEqual(observed.slot_duration_minutes, 60)
        self.assertEqual(observed.source_url, AVAILABILITY_SOURCE)

    def test_omitted_values_are_preserved_without_becoming_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "metadata.json"
            initial = patch(court_count=3, surface=("hard",), booking_window_days=7)
            asyncio.run(refresh_metadata((VENUE,), {VENUE.id: StaticSource(initial)}, output))
            later = datetime(2026, 9, 17, 12, tzinfo=timezone.utc)
            reports, failures = asyncio.run(refresh_metadata((VENUE,), {VENUE.id: StaticSource(patch(later, court_count=3))}, output))
            saved = load_snapshot(output)[VENUE.id]
            self.assertEqual((saved.surface, saved.booking_window_days), (("hard",), 7))
            self.assertEqual(saved.last_checked, later)
            self.assertEqual(reports, ("Example Court\nNo metadata changes.",))
            self.assertEqual(failures, ())

    def test_partial_collections_are_preserved_and_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "metadata.json"
            hours = {
                "monday": ((time(8), time(20)),),
                "tuesday": ((time(8), time(20)),),
            }
            initial = patch(surface=("hard", "clay"), opening_hours=hours)
            asyncio.run(refresh_metadata((VENUE,), {VENUE.id: StaticSource(initial)}, output))

            partial = patch(surface=("hard",), opening_hours={"monday": hours["monday"]})
            reports, failures = asyncio.run(refresh_metadata((VENUE,), {VENUE.id: StaticSource(partial)}, output))

            saved = load_snapshot(output)[VENUE.id]
            self.assertEqual(saved.surface, initial.values[MetadataField.SURFACE])
            self.assertEqual(saved.opening_hours, initial.values[MetadataField.OPENING_HOURS])
            self.assertIn("surface\n  old: ('hard', 'clay')\n  new: ('hard',)\n  status: blocked", reports[0])
            self.assertIn("opening_hours", reports[0])
            self.assertIn("status: blocked", reports[0])
            self.assertEqual(failures, ())

    def test_invalid_candidate_does_not_replace_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "metadata.json"
            initial = patch(court_count=3, surface=("hard",), booking_window_days=7)
            asyncio.run(refresh_metadata((VENUE,), {VENUE.id: StaticSource(initial)}, output))
            before = output.read_bytes()
            with self.assertRaisesRegex(ValueError, "court_count"):
                asyncio.run(refresh_metadata((VENUE,), {VENUE.id: StaticSource(patch(court_count=0))}, output))
            self.assertEqual(output.read_bytes(), before)

    def test_older_patch_does_not_replace_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "metadata.json"
            current = patch(datetime(2026, 9, 21, 12, tzinfo=timezone.utc), court_count=3)
            asyncio.run(refresh_metadata((VENUE,), {VENUE.id: StaticSource(current)}, output))
            before = output.read_bytes()

            older = patch(datetime(2026, 9, 20, 12, tzinfo=timezone.utc), court_count=4)
            with self.assertRaisesRegex(ValueError, "older than saved metadata"):
                asyncio.run(refresh_metadata((VENUE,), {VENUE.id: StaticSource(older)}, output))

            self.assertEqual(output.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
