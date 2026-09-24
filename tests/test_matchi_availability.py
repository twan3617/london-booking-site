import asyncio
import unittest
from datetime import date, datetime, timezone

from ingestion.models import Venue
from ingestion.providers.matchi import MatchiAvailabilitySource, parse_slots
from ingestion.sources import RequestPacer


PLAY_DATE = date(2026, 9, 30)
DETECTED_AT = datetime(2026, 9, 24, 10, tzinfo=timezone.utc)
VENUE = Venue(
    id="padel-bromley-crystal-palace",
    name="Crystal Palace National Sports Centre",
    sport="padel",
    provider="html",
    booking_url="https://www.matchi.se/facilities/game4padelcrystalpalace",
    metadata_sources=("https://www.game4padel.com/crystal-palace",),
    availability_urls=("https://api.matchi.com/facilities/2368",),
)


def fixture():
    return [{
        "resourceId": 15556,
        "startDateTime": "2026-09-30T07:00:00+01:00",
        "endDateTime": "2026-09-30T08:00:00+01:00",
        "price": {"amount": "32.00", "currency": "GBP", "vat": "5.33"},
    }]


class MatchiAvailabilityTests(unittest.TestCase):
    def test_public_availability_is_normalized(self):
        slots = parse_slots(VENUE, fixture(), PLAY_DATE, PLAY_DATE, DETECTED_AT)

        self.assertEqual(len(slots), 1)
        self.assertEqual(slots[0].court_id, "15556")
        self.assertEqual(slots[0].price_pence, 3200)
        self.assertEqual(slots[0].start_time.isoformat(), "2026-09-30T07:00:00+01:00")
        self.assertEqual(slots[0].booking_url, VENUE.booking_url)

    def test_source_fetches_each_bookable_resource_once_for_the_date_range(self):
        calls = []

        def fetch_json(url):
            calls.append(url)
            if url == VENUE.availability_urls[0]:
                return {
                    "id": 2368,
                    "resourceTypes": ["PADEL"],
                    "resources": ["15556", "15557"],
                    "timeZone": "Europe/London",
                    "urls": {"WEB_URL": VENUE.booking_url},
                }
            resource_id = int(url.split("/resources/", 1)[1].split("/", 1)[0])
            return [{**fixture()[0], "resourceId": resource_id}]

        slots = asyncio.run(MatchiAvailabilitySource(
            fetch_json=fetch_json, request_pacer=RequestPacer(interval_seconds=0)
        ).fetch_availability(
            VENUE, PLAY_DATE, PLAY_DATE
        ))

        self.assertEqual(len(slots), 2)
        self.assertEqual(calls[0], VENUE.availability_urls[0])
        self.assertEqual(len(calls), 3)
        self.assertTrue(all("startDateTime=" in url and "endDateTime=" in url for url in calls[1:]))

    def test_rejects_a_mismatched_facility(self):
        source = MatchiAvailabilitySource(fetch_json=lambda _: {
            "id": 9999,
            "resourceTypes": ["PADEL"],
            "resources": ["15556"],
            "timeZone": "Europe/London",
            "urls": {"WEB_URL": VENUE.booking_url},
        }, request_pacer=RequestPacer(interval_seconds=0))

        with self.assertRaisesRegex(ValueError, "Invalid MATCHi facility"):
            asyncio.run(source.fetch_availability(VENUE, PLAY_DATE, PLAY_DATE))


if __name__ == "__main__":
    unittest.main()
