import asyncio
import copy
import json
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from ingestion.providers.better import BetterAvailabilitySource, parse_slots
from ingestion.registry import load_registry

ROOT = Path(__file__).resolve().parents[1]
VENUE = next(
    venue
    for venue in load_registry(ROOT / "config/venues.yaml")
    if venue.id == "hounslow-gunnersbury-park-sports-hub"
)
PLAY_DATE = date(2026, 9, 26)
DETECTED_AT = datetime(2026, 9, 21, 21, 50, tzinfo=timezone.utc)


def fixture():
    return json.loads((ROOT / "tests/fixtures/better_gunnersbury_slots.json").read_text())


class BetterAvailabilityTests(unittest.TestCase):
    def test_slots_are_normalized_without_provider_fields(self):
        slots = parse_slots(VENUE, fixture(), PLAY_DATE, DETECTED_AT)

        self.assertEqual(len(slots), 2)
        self.assertEqual([slot.available for slot in slots], [False, True])
        self.assertEqual(slots[1].venue_id, VENUE.id)
        self.assertEqual(slots[1].court_id, "482")
        self.assertEqual(slots[1].start_time.isoformat(), "2026-09-26T19:00:00+01:00")
        self.assertEqual(slots[1].end_time.isoformat(), "2026-09-26T20:00:00+01:00")
        self.assertEqual(slots[1].price_pence, 1345)
        self.assertEqual(
            slots[1].booking_url,
            "https://bookings.better.org.uk/location/gunnersbury-park-sports-hub/tennis-court-outdoor/2026-09-26/by-time",
        )
        self.assertEqual(slots[1].detected_at, DETECTED_AT)

    def test_wrong_date_or_duplicate_slot_is_rejected(self):
        wrong_date = fixture()
        wrong_date["data"][0]["date"]["raw"] = "2026-09-27"
        with self.assertRaisesRegex(ValueError, "date mismatch"):
            parse_slots(VENUE, wrong_date, PLAY_DATE, DETECTED_AT)

        duplicate = fixture()
        duplicate["data"][1]["id"] = duplicate["data"][0]["id"]
        with self.assertRaisesRegex(ValueError, "Duplicate Better slot"):
            parse_slots(VENUE, duplicate, PLAY_DATE, DETECTED_AT)

    def test_source_fetches_the_curated_date_endpoint(self):
        calls = []
        source = BetterAvailabilitySource(fetch_json=lambda url: calls.append(url) or copy.deepcopy(fixture()))

        slots = asyncio.run(source.fetch_availability(VENUE, PLAY_DATE, PLAY_DATE))

        self.assertEqual(len(slots), 2)
        self.assertEqual(
            calls,
            [f"{VENUE.availability_url}?date=2026-09-26"],
        )


if __name__ == "__main__":
    unittest.main()
