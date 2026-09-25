import asyncio
import json
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ingestion.models import Venue
from ingestion.providers.playtomic import PlaytomicAvailabilitySource, parse_slots
from scripts.refresh_availability import refresh_availability


TENANT_ID = "7a6f7a17-5a73-4468-9329-56c901f1ceba"
PLAY_DATE = date(2026, 9, 24)
DETECTED_AT = datetime(2026, 9, 23, 20, tzinfo=timezone.utc)
VENUE = Venue(
    id="padel-barnet-padel-hub-n20",
    name="The Padel Hub N20",
    sport="padel",
    provider="html",
    booking_url=f"https://playtomic.io/tenant/{TENANT_ID}",
    metadata_sources=("https://playtomic.com/clubs/the-padel-hub-n20-north-london",),
    availability_urls=(f"https://playtomic.com/api/clubs/availability?tenant_id={TENANT_ID}&sport_id=PADEL",),
)


def fixture():
    return [{
        "resource_id": "court-1",
        "start_date": "2026-09-24",
        "slots": [
            {"start_time": "11:00:00", "duration": 60, "price": "60 GBP"},
            {"start_time": "11:00:00", "duration": 90, "price": "80 GBP"},
        ],
    }]


class PlaytomicAvailabilityTests(unittest.TestCase):
    def test_available_durations_are_normalized_with_dated_booking_links(self):
        slots = parse_slots(VENUE, fixture(), PLAY_DATE, DETECTED_AT)

        self.assertEqual(len(slots), 2)
        self.assertEqual([slot.end_time.hour for slot in slots], [12, 12])
        self.assertEqual([slot.end_time.minute for slot in slots], [0, 30])
        self.assertEqual([slot.price_pence for slot in slots], [6000, 8000])
        self.assertTrue(all(slot.available and slot.court_id == "court-1" for slot in slots))
        self.assertEqual(slots[0].booking_url, f"https://playtomic.io/tenant/{TENANT_ID}?q=PADEL~2026-09-24~~~")

    def test_invalid_date_price_or_duplicate_slot_is_rejected(self):
        for field, value in (("start_date", "2026-09-25"), ("price", "60 EUR"), ("start_time", "11:00:00+01:00")):
            payload = fixture()
            (payload[0] if field == "start_date" else payload[0]["slots"][0])[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                parse_slots(VENUE, payload, PLAY_DATE, DETECTED_AT)

        payload = fixture()
        payload[0]["slots"].append(payload[0]["slots"][0].copy())
        with self.assertRaisesRegex(ValueError, "Duplicate Playtomic slot"):
            parse_slots(VENUE, payload, PLAY_DATE, DETECTED_AT)

    def test_source_uses_the_public_date_endpoint(self):
        calls = []
        source = PlaytomicAvailabilitySource(fetch_json=lambda url: calls.append(url) or fixture())

        slots = asyncio.run(source.fetch_availability(VENUE, PLAY_DATE, PLAY_DATE))

        self.assertEqual(len(slots), 2)
        self.assertEqual(calls, [f"https://playtomic.com/api/clubs/availability?tenant_id={TENANT_ID}&sport_id=PADEL&date=2026-09-24"])

    def test_source_rejects_a_foreign_tenant_or_host_before_fetching(self):
        calls = []
        source = PlaytomicAvailabilitySource(fetch_json=lambda url: calls.append(url) or fixture())
        for url in (
            "https://playtomic.com/api/clubs/availability?tenant_id=a95b1ddd-ea5a-4516-86a8-cf3825ebe760&sport_id=PADEL",
            f"https://example.org/api/clubs/availability?tenant_id={TENANT_ID}&sport_id=PADEL",
        ):
            venue = Venue(**{**VENUE.__dict__, "availability_urls": (url,)})
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "No Playtomic availability source"):
                asyncio.run(source.fetch_availability(venue, PLAY_DATE, PLAY_DATE))
        self.assertEqual(calls, [])

    def test_refresh_promotes_slot_price_and_duration_to_live_metadata(self):
        payload = fixture()
        payload[0]["slots"] = payload[0]["slots"][:1]
        slots = parse_slots(VENUE, payload, PLAY_DATE, DETECTED_AT)

        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory:
            output = Path(directory) / "availability.json"
            with patch("scripts.refresh_availability.load_registry", return_value=(VENUE,)), patch(
                "scripts.refresh_availability.PlaytomicAvailabilitySource.fetch_availability", return_value=slots
            ):
                asyncio.run(refresh_availability(output, provider="playtomic"))
            metadata = json.loads(output.read_text())["metadata"][VENUE.id]["values"]

        self.assertEqual(metadata["prices"], [{
            "amount_gbp": "60",
            "duration_minutes": 60,
            "customer": None,
            "time_band": None,
            "lights_included": None,
        }])
        self.assertEqual(metadata["slot_duration_minutes"], 60)


if __name__ == "__main__":
    unittest.main()
