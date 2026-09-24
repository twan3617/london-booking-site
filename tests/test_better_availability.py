import asyncio
import copy
import json
import unittest
from dataclasses import replace
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
            [f"{VENUE.availability_urls[0]}?date=2026-09-26"],
        )

    def test_source_combines_multiple_products_without_duplicate_courts(self):
        indoor_url = "https://better-admin.org.uk/api/activities/venue/gunnersbury-park-sports-hub/activity/tennis-court-indoor/v2/slots"
        venue = replace(VENUE, availability_urls=(VENUE.availability_urls[0], indoor_url))
        calls = []

        def fetch_json(url):
            calls.append(url)
            payload = copy.deepcopy(fixture())
            if "tennis-court-indoor" in url:
                for index, row in enumerate(payload["data"]):
                    row["id"] = f"indoor-{index}"
                    row["category_slug"] = "tennis-court-indoor"
                payload["data"][1]["location"]["id"] = "483"
            return payload

        slots = asyncio.run(BetterAvailabilitySource(fetch_json=fetch_json).fetch_availability(venue, PLAY_DATE, PLAY_DATE))

        self.assertEqual([slot.court_id for slot in slots], ["481", "482", "483"])
        self.assertEqual(slots[-1].booking_url, "https://bookings.better.org.uk/location/gunnersbury-park-sports-hub/tennis-court-indoor/2026-09-26/by-time")
        self.assertEqual(calls, [
            f"{VENUE.availability_urls[0]}?date=2026-09-26",
            f"{indoor_url}?date=2026-09-26",
        ])

    def test_source_rejects_foreign_venue_or_host(self):
        for url in (
            "https://better-admin.org.uk/api/activities/venue/lee-valley-hockey-and-tennis-centre/activity/tennis-court-indoor/v2/slots",
            "https://example.org/api/activities/venue/gunnersbury-park-sports-hub/activity/tennis-court-indoor/v2/slots",
        ):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "No Better availability source"):
                asyncio.run(BetterAvailabilitySource(fetch_json=lambda _: fixture()).fetch_availability(replace(VENUE, availability_urls=(url,)), PLAY_DATE, PLAY_DATE))

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
                self.assertEqual(venue.availability_urls, (f"https://better-admin.org.uk/api/activities/venue/{venue_slug}/activity/{activity_slug}/v2/slots",))
                payload = json.loads((ROOT / "tests/fixtures" / fixture_name).read_text())
                slots = parse_slots(venue, payload, date(2026, 9, 24), DETECTED_AT)
                self.assertEqual([slot.available for slot in slots], [True, False])
                self.assertTrue(all(slot.venue_id == venue_id for slot in slots))

    def test_refresh_saves_the_official_booking_url_for_dates_without_slots(self):
        with TemporaryDirectory(dir=ROOT) as directory:
            output = Path(directory) / "availability.json"
            with patch("scripts.refresh_availability.BetterAvailabilitySource.fetch_availability", return_value=()), patch("scripts.refresh_availability.LtaAvailabilitySource.fetch_availability", return_value=()), patch("scripts.refresh_availability.PlaytomicAvailabilitySource.fetch_availability", return_value=()), patch("scripts.refresh_availability.MatchiAvailabilitySource.fetch_availability", return_value=()), patch("scripts.refresh_availability.PadelMatesAvailabilitySource.fetch_availability", return_value=()):
                asyncio.run(refresh_availability(output))
            snapshot = json.loads(output.read_text())
        self.assertEqual(
            snapshot["booking_urls"][VENUE.id],
            "https://bookings.better.org.uk/location/gunnersbury-park-sports-hub/tennis-court-outdoor",
        )
        self.assertIn("https://www.lta.org.uk/play/book-a-tennis-court/courts/barking-park_", snapshot["booking_urls"]["barking-and-dagenham-barking-park"])
        self.assertEqual(snapshot["booking_urls"]["padel-barnet-padel-hub-n20"], "https://playtomic.io/tenant/7a6f7a17-5a73-4468-9329-56c901f1ceba")
        self.assertEqual(snapshot["booking_urls"]["padel-newham-rocket-beckton"], "https://padelmates.se/club/f953765495194a299e49f49674d69a41")

    def test_refresh_includes_the_padelmates_provider_batch(self):
        with TemporaryDirectory(dir=ROOT) as directory:
            output = Path(directory) / "availability.json"
            with patch("scripts.refresh_availability.BetterAvailabilitySource.fetch_availability", return_value=()), patch("scripts.refresh_availability.LtaAvailabilitySource.fetch_availability", return_value=()), patch("scripts.refresh_availability.PlaytomicAvailabilitySource.fetch_availability", return_value=()), patch("scripts.refresh_availability.MatchiAvailabilitySource.fetch_availability", return_value=()), patch("scripts.refresh_availability.PadelMatesAvailabilitySource.fetch_availability", return_value=()):
                asyncio.run(refresh_availability(output))
            snapshot = json.loads(output.read_text())

        provider = snapshot["providers"]["fastapi-production-fargate.padelmates.io"]
        self.assertEqual(provider["venue_ids"], [
            "padel-newham-rocket-beckton",
            "padel-redbridge-rocket-ilford",
            "padel-wandsworth-rocket-battersea",
        ])
        self.assertEqual(provider["booking_urls"]["padel-newham-rocket-beckton"], "https://padelmates.se/club/f953765495194a299e49f49674d69a41")

    def test_refresh_keeps_successful_provider_batches_when_one_provider_fails(self):
        with TemporaryDirectory(dir=ROOT) as directory:
            output = Path(directory) / "availability.json"
            with patch("scripts.refresh_availability.BetterAvailabilitySource.fetch_availability", return_value=()), patch("scripts.refresh_availability.LtaAvailabilitySource.fetch_availability", side_effect=RuntimeError("blocked")), patch("scripts.refresh_availability.PlaytomicAvailabilitySource.fetch_availability", return_value=()), patch("scripts.refresh_availability.MatchiAvailabilitySource.fetch_availability", return_value=()), patch("scripts.refresh_availability.PadelMatesAvailabilitySource.fetch_availability", return_value=()):
                asyncio.run(refresh_availability(output))
            snapshot = json.loads(output.read_text())

        self.assertEqual(set(snapshot["providers"]), {"better-admin.org.uk", "playtomic.com", "api.matchi.com", "fastapi-production-fargate.padelmates.io"})
        self.assertEqual(snapshot["failed_providers"], ["www.lta.org.uk"])

    def test_refresh_does_not_replace_the_snapshot_when_every_provider_fails(self):
        with TemporaryDirectory(dir=ROOT) as directory:
            output = Path(directory) / "availability.json"
            output.write_text("previous snapshot")
            with patch("scripts.refresh_availability.BetterAvailabilitySource.fetch_availability", side_effect=RuntimeError("blocked")), patch("scripts.refresh_availability.LtaAvailabilitySource.fetch_availability", side_effect=RuntimeError("blocked")), patch("scripts.refresh_availability.PlaytomicAvailabilitySource.fetch_availability", side_effect=RuntimeError("blocked")), patch("scripts.refresh_availability.MatchiAvailabilitySource.fetch_availability", side_effect=RuntimeError("blocked")), patch("scripts.refresh_availability.PadelMatesAvailabilitySource.fetch_availability", side_effect=RuntimeError("blocked")):
                with self.assertRaisesRegex(RuntimeError, "All availability providers failed"):
                    asyncio.run(refresh_availability(output))
            self.assertEqual(output.read_text(), "previous snapshot")

    def test_refresh_does_not_request_a_date_beyond_betters_utc_window(self):
        class BeforeUtcMidnight(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 9, 23, 23, 30, tzinfo=timezone.utc).astimezone(tz)

        with TemporaryDirectory(dir=ROOT) as directory:
            output = Path(directory) / "availability.json"
            with patch("scripts.refresh_availability.datetime", BeforeUtcMidnight), patch("scripts.refresh_availability.BetterAvailabilitySource.fetch_availability", return_value=()), patch("scripts.refresh_availability.LtaAvailabilitySource.fetch_availability", return_value=()), patch("scripts.refresh_availability.PlaytomicAvailabilitySource.fetch_availability", return_value=()), patch("scripts.refresh_availability.MatchiAvailabilitySource.fetch_availability", return_value=()), patch("scripts.refresh_availability.PadelMatesAvailabilitySource.fetch_availability", return_value=()):
                asyncio.run(refresh_availability(output))
            snapshot = json.loads(output.read_text())
        self.assertEqual((snapshot["coverage_start"], snapshot["coverage_end"]), ("2026-09-24", "2026-09-29"))

    def test_refresh_uses_betters_current_six_date_window(self):
        class DuringLondonDay(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 9, 24, 10, tzinfo=timezone.utc).astimezone(tz)

        with TemporaryDirectory(dir=ROOT) as directory:
            output = Path(directory) / "availability.json"
            with patch("scripts.refresh_availability.datetime", DuringLondonDay), patch("scripts.refresh_availability.BetterAvailabilitySource.fetch_availability", return_value=()), patch("scripts.refresh_availability.LtaAvailabilitySource.fetch_availability", return_value=()), patch("scripts.refresh_availability.PlaytomicAvailabilitySource.fetch_availability", return_value=()), patch("scripts.refresh_availability.MatchiAvailabilitySource.fetch_availability", return_value=()), patch("scripts.refresh_availability.PadelMatesAvailabilitySource.fetch_availability", return_value=()):
                asyncio.run(refresh_availability(output))
            snapshot = json.loads(output.read_text())

        self.assertEqual((snapshot["coverage_start"], snapshot["coverage_end"]), ("2026-09-24", "2026-09-29"))


if __name__ == "__main__":
    unittest.main()
