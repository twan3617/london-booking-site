import asyncio
import copy
import json
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ingestion.providers.better import BetterAvailabilitySource, parse_slots
from ingestion.registry import load_registry
from scripts.refresh_availability import refresh_availability

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

    def test_unreleased_slot_keeps_its_booking_release_time(self):
        payload = fixture()
        payload["data"][0]["action_to_show"] = {
            "status": None,
            "reason": "You cannot book this activity yet",
        }
        payload["data"][0]["first_bookable_at"]["utc"] = "2026-09-23T21:00:00+00:00"

        slot = parse_slots(VENUE, payload, PLAY_DATE, DETECTED_AT)[0]

        self.assertFalse(slot.available)
        self.assertEqual(slot.booking_opens_at.isoformat(), "2026-09-23T21:00:00+00:00")

    def test_source_fetches_the_curated_date_endpoint(self):
        calls = []
        source = BetterAvailabilitySource(fetch_json=lambda url: calls.append(url) or copy.deepcopy(fixture()))

        slots = asyncio.run(source.fetch_availability(VENUE, PLAY_DATE, PLAY_DATE))

        self.assertEqual(len(slots), 2)
        self.assertEqual(
            calls,
            [f"{VENUE.availability_url}?date=2026-09-26"],
        )

    def test_more_court_venues_use_the_existing_better_slot_parser(self):
        venues = {venue.id: venue for venue in load_registry(ROOT / "config/venues.yaml")}
        for venue_id, venue_slug, activity_slug, fixture_name in (
            ("greenwich-charlton-lido-and-lifestyle-club-hornfair-park", "charlton-lido", "tennis-court-outdoor", "better_charlton_slots.json"),
            ("islington-highbury-fields", "islington-tennis-centre", "highbury-tennis", "better_highbury_slots.json"),
            ("squash-islington-finsbury", "finsbury-leisure-centre", "squash-40min", "better_finsbury_squash_slots.json"),
        ):
            with self.subTest(venue=venue_id):
                venue = venues[venue_id]
                self.assertEqual(venue.booking_url, f"https://bookings.better.org.uk/location/{venue_slug}/{activity_slug}")
                self.assertEqual(venue.availability_url, f"https://better-admin.org.uk/api/activities/venue/{venue_slug}/activity/{activity_slug}/v2/slots")
                payload = json.loads((ROOT / "tests/fixtures" / fixture_name).read_text())
                slots = parse_slots(venue, payload, date(2026, 9, 24), DETECTED_AT)
                self.assertEqual([slot.available for slot in slots], [True, False])
                self.assertTrue(all(slot.venue_id == venue_id for slot in slots))

    def test_refresh_saves_the_official_booking_url_for_dates_without_slots(self):
        with TemporaryDirectory(dir=ROOT) as directory:
            output = Path(directory) / "availability.json"
            with patch("scripts.refresh_availability.BetterAvailabilitySource.fetch_availability", return_value=()):
                asyncio.run(refresh_availability(output))
            snapshot = json.loads(output.read_text())
        self.assertEqual(
            snapshot["booking_urls"][VENUE.id],
            "https://bookings.better.org.uk/location/gunnersbury-park-sports-hub/tennis-court-outdoor",
        )
        self.assertEqual(set(snapshot["venue_ids"]), {
            VENUE.id,
            "greenwich-charlton-lido-and-lifestyle-club-hornfair-park",
            "islington-highbury-fields",
            "squash-islington-finsbury",
        })

    def test_refresh_does_not_request_a_date_beyond_betters_utc_window(self):
        class BeforeUtcMidnight(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 9, 23, 23, 30, tzinfo=timezone.utc).astimezone(tz)

        with TemporaryDirectory(dir=ROOT) as directory:
            output = Path(directory) / "availability.json"
            with patch("scripts.refresh_availability.datetime", BeforeUtcMidnight), patch("scripts.refresh_availability.BetterAvailabilitySource.fetch_availability", return_value=()):
                asyncio.run(refresh_availability(output))
            snapshot = json.loads(output.read_text())
        self.assertEqual((snapshot["coverage_start"], snapshot["coverage_end"]), ("2026-09-24", "2026-09-29"))


if __name__ == "__main__":
    unittest.main()
