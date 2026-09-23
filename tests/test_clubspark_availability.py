import asyncio
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

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
        slots = parse_sessions(venue, booking_sheet(), PLAY_DATE, DETECTED_AT)

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
                parse_sessions(venue, payload, PLAY_DATE, DETECTED_AT)
        payload = booking_sheet()
        payload["TimeZone"] = "UTC"
        with self.assertRaisesRegex(ValueError, "timezone"):
            parse_sessions(venue, payload, PLAY_DATE, DETECTED_AT)

    def test_source_uses_same_date_scoped_request_for_another_venue(self):
        venue = VENUES["hammersmith-and-fulham-ravenscourt-park"]
        calls = []
        source = ClubSparkAvailabilitySource(fetch_json=lambda url: calls.append(url) or booking_sheet())

        slots = asyncio.run(source.fetch_availability(venue, PLAY_DATE, PLAY_DATE))

        self.assertEqual(len(slots), 3)
        self.assertEqual(calls, [
            "https://clubspark.lta.org.uk/v0/VenueBooking/RavenscourtPark/GetVenueSessions?resourceID=&startDate=2026-09-24&endDate=2026-09-24&roleId=",
        ])


if __name__ == "__main__":
    unittest.main()
