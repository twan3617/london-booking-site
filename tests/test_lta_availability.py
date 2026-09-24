import asyncio
import unittest
from datetime import date, datetime, timezone

from ingestion.models import Venue
from ingestion.providers.lta import LtaAvailabilitySource, parse_slots


VENUE_ID = "14ed8b1d-857d-4ca4-92fd-31629fbdc715"
PLAY_DATE = date(2026, 9, 24)
DETECTED_AT = datetime(2026, 9, 24, 10, tzinfo=timezone.utc)
VENUE = Venue(
    id="bexley-northumberland-heath-recreation-ground",
    name="Northumberland Heath Recreation Ground",
    sport="tennis",
    provider="clubspark",
    booking_url=f"https://www.lta.org.uk/play/book-a-tennis-court/courts/northumberland-heath-recreation-ground_{VENUE_ID}/",
    metadata_sources=("https://clubspark.lta.org.uk/NorthumberlandHeathRecreationGround",),
    availability_urls=(f"https://www.lta.org.uk/api/courtdetail/availability?venueid={VENUE_ID}",),
)


def fixture():
    return {
        "venueDetails": [{
            "name": "Court 1", "order": 1, "id": "court-1", "type": "Outdoor", "surface": "Tarmac",
            "availableSlots": [
                {"slotId": "slot-1", "startTime": "2026-09-24T13:00:00", "endTime": "2026-09-24T14:00:00", "price": 7.0},
                {"slotId": "slot-2", "startTime": "2026-09-24T14:00:00", "endTime": "2026-09-24T15:30:00", "price": 8.5},
            ],
        }],
        "rules": {"minSlots": 1, "maxSlots": 1, "availableDates": ["2026-09-24", "2026-09-25"]},
        "error": {"hasError": False, "errorMessage": ""},
    }


class LtaAvailabilityTests(unittest.TestCase):
    def test_public_slots_are_normalized_with_prices_and_booking_date(self):
        slots = parse_slots(VENUE, fixture(), PLAY_DATE, DETECTED_AT)

        self.assertEqual([slot.court_id for slot in slots], ["court-1", "court-1"])
        self.assertEqual([slot.price_pence for slot in slots], [700, 850])
        self.assertEqual(slots[0].start_time.isoformat(), "2026-09-24T13:00:00+01:00")
        self.assertEqual(slots[1].end_time.isoformat(), "2026-09-24T15:30:00+01:00")
        self.assertEqual(slots[0].booking_url, f"{VENUE.booking_url}?date=2026-09-24")

    def test_errors_wrong_dates_and_duplicate_slots_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "LTA availability error"):
            parse_slots(VENUE, {"error": []}, PLAY_DATE, DETECTED_AT)

        payload = fixture()
        payload["error"]["hasError"] = True
        with self.assertRaisesRegex(ValueError, "LTA availability error"):
            parse_slots(VENUE, payload, PLAY_DATE, DETECTED_AT)

        payload = fixture()
        payload["venueDetails"][0]["availableSlots"][0]["startTime"] = "2026-09-25T13:00:00"
        with self.assertRaisesRegex(ValueError, "date mismatch"):
            parse_slots(VENUE, payload, PLAY_DATE, DETECTED_AT)

        payload = fixture()
        payload["venueDetails"][0]["availableSlots"].append(payload["venueDetails"][0]["availableSlots"][0].copy())
        with self.assertRaisesRegex(ValueError, "Duplicate LTA slot"):
            parse_slots(VENUE, payload, PLAY_DATE, DETECTED_AT)

    def test_source_uses_the_public_date_endpoint(self):
        calls = []
        source = LtaAvailabilitySource(fetch_json=lambda url: calls.append(url) or fixture())

        slots = asyncio.run(source.fetch_availability(VENUE, PLAY_DATE, PLAY_DATE))

        self.assertEqual(len(slots), 2)
        self.assertEqual(calls, [f"https://www.lta.org.uk/api/courtdetail/availability?venueid={VENUE_ID}&date=2026-09-24"])

    def test_source_rejects_a_foreign_or_mismatched_venue_before_fetching(self):
        calls = []
        source = LtaAvailabilitySource(fetch_json=lambda url: calls.append(url) or fixture())
        for url in (
            f"https://example.org/api/courtdetail/availability?venueid={VENUE_ID}",
            "https://www.lta.org.uk/api/courtdetail/availability?venueid=507b8af1-c936-4404-a041-6e28f89cde1f",
        ):
            venue = Venue(**{**VENUE.__dict__, "availability_urls": (url,)})
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "No LTA availability source"):
                asyncio.run(source.fetch_availability(venue, PLAY_DATE, PLAY_DATE))
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
