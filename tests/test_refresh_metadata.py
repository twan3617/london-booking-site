import asyncio
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, time, timezone
from pathlib import Path

from ingestion.models import Venue, VenueMetadata
from scripts.refresh_metadata import load_snapshot, refresh_metadata


VENUE = Venue(
    id="example-court",
    name="Example Court",
    sport="tennis",
    provider="clubspark",
    booking_url="https://example.org/book",
    metadata_sources=("https://example.org/source",),
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


class StaticSource:
    def __init__(self, value):
        self.value = value

    async def fetch_metadata(self, venue):
        return self.value


class RefreshMetadataTests(unittest.TestCase):
    def test_first_refresh_writes_canonical_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "metadata.json"
            reports = asyncio.run(refresh_metadata((VENUE,), {VENUE.id: StaticSource(metadata())}, output))
            saved = load_snapshot(output)[VENUE.id]
            self.assertEqual((saved.court_count, saved.surface, saved.booking_window_days), (3, ("hard",), 7))
            self.assertEqual(reports, ("Example Court\nNew metadata record.",))
            document = json.loads(output.read_text())
            self.assertEqual(document["venues"][0]["last_checked"], "2026-09-16T12:00:00+00:00")

    def test_disappearing_values_are_preserved_and_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "metadata.json"
            asyncio.run(refresh_metadata((VENUE,), {VENUE.id: StaticSource(metadata())}, output))
            later = datetime(2026, 9, 17, 12, tzinfo=timezone.utc)
            reports = asyncio.run(refresh_metadata((VENUE,), {VENUE.id: StaticSource(metadata(surface=(), booking_window_days=None, last_checked=later))}, output))
            saved = load_snapshot(output)[VENUE.id]
            self.assertEqual((saved.surface, saved.booking_window_days), (("hard",), 7))
            self.assertEqual(saved.last_checked, later)
            self.assertIn("surface\n  old: ('hard',)\n  new: unknown\n  status: blocked", reports[0])
            self.assertIn("booking_window_days\n  old: 7\n  new: unknown\n  status: blocked", reports[0])

    def test_partial_collections_are_preserved_and_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "metadata.json"
            hours = {
                "monday": ((time(8), time(20)),),
                "tuesday": ((time(8), time(20)),),
            }
            initial = metadata(surface=("hard", "clay"), opening_hours=hours)
            asyncio.run(refresh_metadata((VENUE,), {VENUE.id: StaticSource(initial)}, output))

            partial = metadata(surface=("hard",), opening_hours={"monday": hours["monday"]})
            reports = asyncio.run(refresh_metadata((VENUE,), {VENUE.id: StaticSource(partial)}, output))

            saved = load_snapshot(output)[VENUE.id]
            self.assertEqual(saved.surface, initial.surface)
            self.assertEqual(saved.opening_hours, initial.opening_hours)
            self.assertIn("surface\n  old: ('hard', 'clay')\n  new: ('hard',)\n  status: blocked", reports[0])
            self.assertIn("opening_hours", reports[0])
            self.assertIn("status: blocked", reports[0])

    def test_invalid_candidate_does_not_replace_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "metadata.json"
            asyncio.run(refresh_metadata((VENUE,), {VENUE.id: StaticSource(metadata())}, output))
            before = output.read_bytes()
            with self.assertRaisesRegex(ValueError, "court_count"):
                asyncio.run(refresh_metadata((VENUE,), {VENUE.id: StaticSource(metadata(court_count=0))}, output))
            self.assertEqual(output.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
