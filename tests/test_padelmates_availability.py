import asyncio
import unittest
from dataclasses import replace
from datetime import date, datetime, timezone

from ingestion.models import Venue
from ingestion.providers.padelmates import PadelMatesAvailabilitySource, parse_slots


CLUB_ID = "f953765495194a299e49f49674d69a41"
PLAY_DATE = date(2026, 9, 29)
DETECTED_AT = datetime(2026, 9, 24, 14, 49, tzinfo=timezone.utc)
VENUE = Venue(
    id="padel-newham-rocket-beckton",
    name="Rocket Padel Beckton",
    sport="padel",
    provider="html",
    booking_url=f"https://padelmates.se/club/{CLUB_ID}",
    metadata_sources=("https://www.rocketpadel.com/club/beckton",),
    availability_urls=(f"https://fastapi-production-fargate.padelmates.io/club/?club_id={CLUB_ID}",),
)


def fixture():
    return {
        "activity_join_messages": {},
        "allowed_activity_join": True,
        "disallowed_cards": [],
        "reservedBookings": [],
        "uniqueStartTimes": [1790667000000],
        "originalCourts": [
            {"_id": "court-1", "name": "Court 1", "sport_type": "PADEL"},
            {"_id": "room-1", "name": "Meeting Room", "sport_type": "OTHER"},
        ],
        "allSlots": [
            {
                "courtName": "Court 1",
                "courtId": "court-1",
                "slotId": "slot-1",
                "duration": 60,
                "price": 52.5,
                "startDatetime": "2026-09-29T07:30:00+00:00",
                "endDatetime": "2026-09-29T08:30:00+00:00",
                "startTimestamp": 1790667000000,
                "endTimestamp": 1790670600000,
                "reservedIntersection": False,
                "ableToBookOpenMatch": True,
            },
            {
                "courtName": "Court 1",
                "courtId": "court-1",
                "slotId": "slot-1",
                "duration": 90,
                "price": 82.5,
                "startDatetime": "2026-09-29T07:00:00+00:00",
                "endDatetime": "2026-09-29T08:30:00+00:00",
                "startTimestamp": 1790665200000,
                "endTimestamp": 1790670600000,
                "reservedIntersection": True,
                "ableToBookOpenMatch": True,
            },
            {
                "courtName": "Meeting Room",
                "courtId": "room-1",
                "slotId": "slot-2",
                "duration": 60,
                "price": 30.0,
                "startDatetime": "2026-09-29T09:00:00+00:00",
                "endDatetime": "2026-09-29T10:00:00+00:00",
                "startTimestamp": 1790672400000,
                "endTimestamp": 1790676000000,
                "reservedIntersection": False,
                "ableToBookOpenMatch": True,
            },
        ],
    }


class PadelMatesAvailabilityTests(unittest.TestCase):
    def test_only_open_padel_slots_are_normalized_to_london_time(self):
        slots = parse_slots(VENUE, fixture(), PLAY_DATE, DETECTED_AT)

        self.assertEqual(len(slots), 1)
        self.assertEqual(slots[0].court_id, "court-1")
        self.assertEqual(slots[0].start_time.isoformat(), "2026-09-29T08:30:00+01:00")
        self.assertEqual(slots[0].end_time.isoformat(), "2026-09-29T09:30:00+01:00")
        self.assertEqual(slots[0].price_pence, 5250)
        self.assertEqual(slots[0].booking_url, VENUE.booking_url)

    def test_source_uses_one_public_request_for_the_selected_day(self):
        calls = []
        source = PadelMatesAvailabilitySource(fetch_json=lambda url: calls.append(url) or fixture())

        slots = asyncio.run(source.fetch_availability(VENUE, PLAY_DATE, PLAY_DATE))

        self.assertEqual(len(slots), 1)
        self.assertEqual(calls, [
            "https://fastapi-production-fargate.padelmates.io/player/player_booking/all_courts_slot_prices_v3"
            "?club_id=f953765495194a299e49f49674d69a41&start_datetime=1790636400000"
            "&end_datetime=1790733600000&lang=en"
        ])

    def test_source_accepts_a_public_firebase_style_club_id(self):
        club_id = "n8T0bz1PtMa1WhVElJ7Eclg0ooj2"
        venue = replace(
            VENUE,
            booking_url=f"https://padelmates.se/club/{club_id}",
            availability_urls=(f"https://fastapi-production-fargate.padelmates.io/club/?club_id={club_id}",),
        )

        slots = asyncio.run(PadelMatesAvailabilitySource(fetch_json=lambda _: fixture()).fetch_availability(venue, PLAY_DATE, PLAY_DATE))

        self.assertEqual(len(slots), 1)


if __name__ == "__main__":
    unittest.main()
