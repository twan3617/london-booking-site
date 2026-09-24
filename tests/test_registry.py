import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ingestion.registry import load_registry


ROOT = Path(__file__).resolve().parents[1]


class RegistryTests(unittest.TestCase):
    def test_multiple_availability_urls_are_loaded(self):
        document = """venues:
  - id: multi
    name: Multiple products
    sport: tennis
    provider: better
    booking_url: https://bookings.better.org.uk/location/example/tennis-one
    metadata_sources: [https://example.org/venue]
    availability_urls:
      - https://better-admin.org.uk/api/activities/venue/example/activity/tennis-one/v2/slots
      - https://better-admin.org.uk/api/activities/venue/example/activity/tennis-two/v2/slots
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "venues.yaml"
            path.write_text(document)
            venue = load_registry(path)[0]

        self.assertEqual(getattr(venue, "availability_urls", None), (
            "https://better-admin.org.uk/api/activities/venue/example/activity/tennis-one/v2/slots",
            "https://better-admin.org.uk/api/activities/venue/example/activity/tennis-two/v2/slots",
        ))

    def test_registry_matches_current_venue_ids(self):
        venues = load_registry(ROOT / "config/venues.yaml")
        existing = json.loads((ROOT / "data/venues.json").read_text())["venues"]
        self.assertEqual({venue.id for venue in venues}, {venue["id"] for venue in existing})
        self.assertEqual(len(venues), len(existing))
        self.assertTrue(all(venue.booking_url and venue.metadata_sources for venue in venues))

        better = [venue for venue in venues if venue.provider == "better"]
        self.assertEqual(len(better), 30)
        self.assertEqual(sum(bool(venue.availability_urls) for venue in better), 21)
        self.assertEqual(sum(len(venue.availability_urls) for venue in better), 24)

        clubspark = [venue for venue in venues if venue.provider == "clubspark"]
        self.assertEqual(len(clubspark), 232)
        self.assertEqual(sum(bool(venue.availability_urls) for venue in clubspark), 206)
        self.assertTrue(all(not venue.availability_urls or venue.availability_urls[0].startswith("https://www.lta.org.uk/") for venue in clubspark))
        lta_urls = [venue.availability_urls[0] for venue in clubspark if venue.availability_urls]
        self.assertEqual(len(lta_urls), len(set(lta_urls)))
        for venue in clubspark:
            if venue.availability_urls:
                venue_id = parse_qs(urlparse(venue.availability_urls[0]).query)["venueid"][0]
                self.assertIn(f"_{venue_id}/", venue.booking_url)

        playtomic = [venue for venue in venues if venue.availability_urls and venue.availability_urls[0].startswith("https://playtomic.com/")]
        self.assertEqual(len(playtomic), 8)
        self.assertTrue(all(venue.sport == "padel" and len(venue.availability_urls) == 1 for venue in playtomic))

        matchi = [venue for venue in venues if venue.availability_urls and venue.availability_urls[0].startswith("https://api.matchi.com/")]
        self.assertEqual(len(matchi), 3)
        self.assertTrue(all(venue.sport == "padel" and len(venue.availability_urls) == 1 for venue in matchi))

        padelmates = [venue for venue in venues if venue.availability_urls and venue.availability_urls[0].startswith("https://fastapi-production-fargate.padelmates.io/")]
        self.assertEqual(len(padelmates), 3)
        self.assertTrue(all(venue.sport == "padel" and len(venue.availability_urls) == 1 for venue in padelmates))

        configured = [venue for venue in venues if venue.availability_urls]
        self.assertEqual(len(configured), 243)
        self.assertEqual(sum(len(venue.availability_urls) for venue in configured), 246)

    def test_duplicate_ids_are_rejected(self):
        document = """venues:
  - id: same
    name: One
    sport: tennis
    provider: clubspark
    booking_url: https://example.org/one
    metadata_sources: [https://example.org/one]
  - id: same
    name: Two
    sport: tennis
    provider: html
    booking_url: https://example.org/two
    metadata_sources: [https://example.org/two]
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "venues.yaml"
            path.write_text(document)
            with self.assertRaisesRegex(ValueError, "Duplicate venue ID: same"):
                load_registry(path)

    def test_invalid_source_url_is_rejected(self):
        document = """venues:
  - id: bad-source
    name: Bad source
    sport: tennis
    provider: html
    booking_url: https://example.org/book
    metadata_sources: [not-a-url]
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "venues.yaml"
            path.write_text(document)
            with self.assertRaisesRegex(ValueError, "Invalid metadata URL"):
                load_registry(path)

    def test_malformed_provider_is_rejected(self):
        document = """venues:
  - id: bad-provider
    name: Bad provider
    sport: tennis
    provider: [clubspark]
    booking_url: https://example.org/book
    metadata_sources: [https://example.org/book]
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "venues.yaml"
            path.write_text(document)
            with self.assertRaisesRegex(ValueError, "Invalid sport or provider"):
                load_registry(path)


if __name__ == "__main__":
    unittest.main()
