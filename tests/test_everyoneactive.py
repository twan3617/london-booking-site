import asyncio
import unittest
from datetime import time
from decimal import Decimal

from ingestion.models import MetadataField, PriceRate, Venue
from ingestion.providers.everyoneactive import EveryoneActiveMetadataSource


SOURCE_URL = "https://api.everyoneactive.com/v1.0/centres/0153/timetable"
VENUE = Venue(
    id="squash-westminster-porchester",
    name="Porchester Centre",
    sport="squash",
    provider="html",
    booking_url="https://www.everyoneactive.com/centre/porchester-centre/",
    metadata_sources=("https://www.everyoneactive.com/centre/porchester-centre/", SOURCE_URL),
)


class EveryoneActiveMetadataTests(unittest.TestCase):
    def test_public_timetable_normalizes_squash_metadata(self):
        requested = []
        payload = {
            "items": [{
                "site_id": "0153",
                "what": "Squash",
                "description": "Squash - 45 Minutes",
                "duration": "45 Minute Sessions",
                "prices": {"adult": {"peak": "15.45", "off_peak": "15.45"}},
                "times": {
                    "Monday": [{"start": "06:30", "end": "22:00"}],
                    "Tuesday": [{"start": "06:30", "end": "22:00"}],
                    "Wednesday": [{"start": "06:30", "end": "22:00"}],
                    "Thursday": [{"start": "06:30", "end": "22:00"}],
                    "Friday": [{"start": "06:30", "end": "22:00"}],
                    "Saturday": [{"start": "08:00", "end": "20:00"}],
                    "Sunday": [{"start": "08:00", "end": "20:00"}],
                },
            }, {
                "site_id": "0153",
                "what": "Squash",
                "description": "Squash Coaching - 45 Minutes",
                "duration": "45 Minute Sessions",
                "prices": {"adult": {"peak": "9.75", "off_peak": "9.75"}},
                "times": {"Monday": [{"start": "06:30", "end": "22:00"}]},
            }],
        }
        source = EveryoneActiveMetadataSource(fetch_json=lambda url: requested.append(url) or payload)

        patch = asyncio.run(source.fetch_metadata(VENUE))

        self.assertEqual(requested, [SOURCE_URL])
        self.assertEqual(patch.source_url, SOURCE_URL)
        self.assertEqual(patch.values[MetadataField.SLOT_DURATION_MINUTES], 45)
        self.assertEqual(
            patch.values[MetadataField.PRICES],
            (PriceRate(Decimal("15.45"), 45, "adult_standard", "anytime"),),
        )
        self.assertEqual(patch.values[MetadataField.OPENING_HOURS]["monday"], ((time(6, 30), time(22)),))
        self.assertEqual(patch.values[MetadataField.OPENING_HOURS]["sunday"], ((time(8), time(20)),))

    def test_malformed_provider_prices_are_rejected(self):
        payload = {"items": [{
            "site_id": "0153",
            "what": "Squash",
            "description": "Squash - 45 Minutes",
            "duration": "45 Minute Sessions",
            "prices": None,
        }]}

        with self.assertRaisesRegex(ValueError, "prices"):
            asyncio.run(EveryoneActiveMetadataSource(fetch_json=lambda _: payload).fetch_metadata(VENUE))


if __name__ == "__main__":
    unittest.main()
