import asyncio
import copy
import unittest
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from ingestion.providers.clubspark_availability import ClubSparkAvailabilitySource, parse_sessions
from ingestion.registry import load_registry


ROOT = Path(__file__).resolve().parents[1]
VENUES = {venue.id: venue for venue in load_registry(ROOT / "config/venues.yaml")}
PLAY_DATE = date(2026, 9, 24)
DETECTED_AT = datetime(2026, 9, 23, 20, tzinfo=timezone.utc)


def booking_sheet():
    return {
        "TimeZone": "Europe/London",
        "EarliestStartTime": 420,
        "LatestEndTime": 720,
        "MinimumInterval": 60,
        "HideResourceProperties": False,
        "ResourceGroups": [{"ID": "group-1", "Name": "default", "SortOrder": 0, "HideResourceProperties": False}],
        "Resources": [{
            "ID": "court-1", "ResourceGroupID": "group-1", "Name": "Court 1", "Number": 0,
            "Location": 0, "Lighting": 1, "Surface": 6, "Size": 0, "Category": 1,
            "Days": [{"Date": "2026-09-24T00:00:00", "Sessions": [
                {"ID": "open-1", "Category": 0, "SubCategory": 0, "Name": "Available", "StartTime": 420,
                 "EndTime": 600, "Interval": 60, "Capacity": 1, "Cost": 4.0, "CostFrom": 4.0,
                 "CourtCost": 4.0, "LightingCost": 0.0, "MemberPrice": 0.0, "GuestPrice": 0.0},
                {"ID": "booked-1", "Category": 1000, "SubCategory": 0, "Name": "Booking", "StartTime": 600,
                 "EndTime": 660, "Interval": 60, "Capacity": 0, "CostFrom": 0.0,
                 "CourtCost": 4.0, "LightingCost": 0.0, "MemberPrice": 0.0, "GuestPrice": 0.0},
                {"ID": "closed-1", "Category": 8000, "SubCategory": 0, "Name": "Closed", "StartTime": 660,
                 "EndTime": 720, "Interval": 60, "Capacity": 0, "CostFrom": 0.0,
                 "CourtCost": 0.0, "LightingCost": 0.0, "MemberPrice": 0.0, "GuestPrice": 0.0},
            ]}],
        }],
    }


class ClubSparkAvailabilityTests(unittest.TestCase):
    def test_open_range_expands_to_court_slots_and_excludes_booked_and_closed_time(self):
        venue = VENUES["barking-and-dagenham-barking-park"]
        slots = parse_sessions(venue, booking_sheet(), PLAY_DATE, PLAY_DATE, DETECTED_AT)

        self.assertEqual([slot.start_time.isoformat() for slot in slots], [
            "2026-09-24T07:00:00+01:00", "2026-09-24T08:00:00+01:00", "2026-09-24T09:00:00+01:00",
        ])
        self.assertEqual([slot.end_time.hour for slot in slots], [8, 9, 10])
        self.assertTrue(all(slot.available and slot.court_id == "court-1" and slot.price_pence == 400 for slot in slots))
        self.assertEqual(slots[0].booking_url, "https://clubspark.lta.org.uk/BarkingPark/Booking/BookByDate#?date=2026-09-24")
        self.assertEqual(slots[0].detected_at, DETECTED_AT)

    def test_invalid_date_timezone_or_interval_cannot_be_reported_as_open(self):
        venue = VENUES["barking-and-dagenham-barking-park"]
        for field, value in (("Date", "2026-09-25T00:00:00"), ("Interval", 0)):
            payload = booking_sheet()
            target = payload["Resources"][0]["Days"][0]
            (target if field == "Date" else target["Sessions"][0])[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                parse_sessions(venue, payload, PLAY_DATE, PLAY_DATE, DETECTED_AT)
        payload = booking_sheet()
        payload["TimeZone"] = "UTC"
        with self.assertRaisesRegex(ValueError, "timezone"):
            parse_sessions(venue, payload, PLAY_DATE, PLAY_DATE, DETECTED_AT)

    def test_source_fetches_the_date_range_once(self):
        base = VENUES["hammersmith-and-fulham-ravenscourt-park"]
        endpoint = "https://clubspark.lta.org.uk/v0/VenueBooking/RavenscourtPark/GetVenueSessions"
        venue = replace(base, availability_urls=(endpoint,))
        payload = booking_sheet()
        next_day = copy.deepcopy(payload["Resources"][0]["Days"][0])
        next_day["Date"] = "2026-09-25T00:00:00"
        payload["Resources"][0]["Days"].append(next_day)
        calls = []
        source = ClubSparkAvailabilitySource(fetch_json=lambda url: calls.append(url) or payload)

        slots = asyncio.run(source.fetch_availability(venue, PLAY_DATE, date(2026, 9, 25)))

        self.assertEqual(len(slots), 6)
        self.assertEqual({slot.start_time.date() for slot in slots}, {PLAY_DATE, date(2026, 9, 25)})
        self.assertEqual(calls, [
            f"{endpoint}?resourceID=&startDate=2026-09-24&endDate=2026-09-25&roleId=",
        ])

    def test_date_range_must_cover_every_requested_day(self):
        venue = VENUES["barking-and-dagenham-barking-park"]
        with self.assertRaisesRegex(ValueError, "date coverage"):
            parse_sessions(venue, booking_sheet(), PLAY_DATE, date(2026, 9, 25), DETECTED_AT)

        payload = booking_sheet()
        second_day = copy.deepcopy(payload["Resources"][0]["Days"][0])
        second_day["Date"] = "2026-09-25T00:00:00"
        payload["Resources"][0]["Days"].append(second_day)
        second_court = copy.deepcopy(payload["Resources"][0])
        second_court["ID"] = "court-2"
        second_court["Days"] = second_court["Days"][:1]
        payload["Resources"].append(second_court)
        with self.assertRaisesRegex(ValueError, "date coverage"):
            parse_sessions(venue, payload, PLAY_DATE, date(2026, 9, 25), DETECTED_AT)

    def test_source_spaces_successive_venue_requests(self):
        source = ClubSparkAvailabilitySource(fetch_json=lambda _: booking_sheet())

        async def fetch_twice():
            await source.fetch_availability(VENUES["barking-and-dagenham-barking-park"], PLAY_DATE, PLAY_DATE)
            await source.fetch_availability(VENUES["barking-and-dagenham-central-park-dagenham"], PLAY_DATE, PLAY_DATE)

        with patch("ingestion.providers.clubspark_availability.asyncio.sleep", new_callable=AsyncMock) as sleep:
            asyncio.run(fetch_twice())
        sleep.assert_awaited_once()
        self.assertGreater(sleep.await_args.args[0], 0)

    def test_source_rejects_a_foreign_venue_or_host_before_fetching(self):
        base = VENUES["hammersmith-and-fulham-ravenscourt-park"]
        calls = []
        source = ClubSparkAvailabilitySource(fetch_json=lambda url: calls.append(url) or booking_sheet())
        for endpoint in (
            "https://clubspark.lta.org.uk/v0/VenueBooking/BarkingPark/GetVenueSessions",
            "https://example.org/v0/VenueBooking/RavenscourtPark/GetVenueSessions",
        ):
            with self.subTest(endpoint=endpoint), self.assertRaisesRegex(ValueError, "No ClubSpark availability source"):
                asyncio.run(source.fetch_availability(replace(base, availability_urls=(endpoint,)), PLAY_DATE, PLAY_DATE))
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
