import asyncio
import copy
import json
import unittest
from datetime import datetime, time, timezone
from pathlib import Path

from ingestion.models import MetadataField, apply_metadata_patch
from ingestion.providers.openactive import OpenActiveSource, parse_facility_use
from ingestion.registry import load_registry

ROOT = Path(__file__).resolve().parents[1]
VENUES = {venue.id: venue for venue in load_registry(ROOT / "config/venues.yaml")}
CHECKED_AT = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)


def fixture(name):
    return json.loads((ROOT / "tests/fixtures" / name).read_text())


def parsed(venue, item, source_url=None):
    patch = parse_facility_use(venue, item, source_url or venue.metadata_sources[0], CHECKED_AT)
    return apply_metadata_patch(venue, patch)


class OpenActiveTests(unittest.TestCase):
    def test_gunnersbury_court_metadata_uses_individual_hours(self):
        venue = VENUES["hounslow-gunnersbury-park-sports-hub"]
        source_url = venue.metadata_sources[0]
        metadata = parsed(venue, fixture("better_gunnersbury.json"), source_url)
        self.assertEqual((metadata.venue_id, metadata.name, metadata.source_url), (venue.id, venue.name, source_url))
        self.assertEqual(metadata.booking_url, "https://bookings.better.org.uk/location/gunnersbury-park-sports-hub/tennis-court-outdoor")
        self.assertEqual((metadata.court_count, metadata.floodlit), (8, True))
        self.assertEqual(metadata.opening_hours["monday"], ((time(7), time(22)),))
        self.assertEqual(metadata.opening_hours["saturday"], ((time(8), time(20)),))
        self.assertEqual(len(metadata.opening_hours), 7)
        self.assertEqual(metadata.prices, ())
        self.assertIsNone(metadata.booking_window_days)
        self.assertIsNone(metadata.release_time)

    def test_finsbury_squash_stays_sport_specific_without_inferred_duration(self):
        venue = VENUES["squash-islington-finsbury"]
        metadata = parsed(venue, fixture("better_finsbury_squash.json"))
        self.assertEqual(metadata.court_count, 4)
        self.assertEqual(metadata.opening_hours["monday"], ((time(9, 20), time(22)),))
        self.assertEqual(metadata.opening_hours["sunday"], ((time(7), time(18)),))
        self.assertIsNone(metadata.floodlit)
        self.assertIsNone(metadata.slot_duration_minutes)
        self.assertEqual(metadata.prices, ())
        self.assertEqual(metadata.booking_url, venue.booking_url)

    def test_deleted_or_wrong_identity_is_rejected(self):
        venue = VENUES["hounslow-gunnersbury-park-sports-hub"]
        source_url = venue.metadata_sources[0]
        deleted = fixture("better_gunnersbury.json")
        deleted["state"] = "deleted"
        deleted.pop("data")
        with self.assertRaises(ValueError):
            parse_facility_use(venue, deleted, source_url, CHECKED_AT)
        wrong_id = fixture("better_gunnersbury.json")
        wrong_id["data"]["@id"] = "https://example.org/wrong-record"
        with self.assertRaises(ValueError):
            parse_facility_use(venue, wrong_id, source_url, CHECKED_AT)
        wrong_envelope = fixture("better_gunnersbury.json")
        wrong_envelope["id"] = "activity_recurrence_group:99999"
        with self.assertRaises(ValueError):
            parse_facility_use(venue, wrong_envelope, source_url, CHECKED_AT)

    def test_wrong_sport_or_duplicate_court_ids_is_rejected(self):
        tennis = fixture("better_gunnersbury.json")
        squash_venue = VENUES["squash-islington-finsbury"]
        with self.assertRaises(ValueError):
            parse_facility_use(squash_venue, tennis, tennis["data"]["@id"], CHECKED_AT)
        tennis_venue = VENUES["hounslow-gunnersbury-park-sports-hub"]
        duplicate = fixture("better_gunnersbury.json")
        duplicate["data"]["individualFacilityUse"][1]["@id"] = duplicate["data"]["individualFacilityUse"][0]["@id"]
        with self.assertRaises(ValueError):
            parse_facility_use(tennis_venue, duplicate, tennis_venue.metadata_sources[0], CHECKED_AT)
        mixed_type = fixture("better_gunnersbury.json")
        mixed_type["data"]["facilityType"].append(fixture("better_finsbury_squash.json")["data"]["facilityType"][0])
        with self.assertRaises(ValueError):
            parse_facility_use(tennis_venue, mixed_type, tennis_venue.metadata_sources[0], CHECKED_AT)
        foreign_court = fixture("better_gunnersbury.json")
        foreign_court["data"]["individualFacilityUse"][0]["@id"] = "https://example.org/individual-facility-uses/foreign"
        with self.assertRaises(ValueError):
            parse_facility_use(tennis_venue, foreign_court, tennis_venue.metadata_sources[0], CHECKED_AT)

    def test_mixed_court_hours_leave_venue_hours_unknown(self):
        venue = VENUES["hounslow-gunnersbury-park-sports-hub"]
        item = copy.deepcopy(fixture("better_gunnersbury.json"))
        item["data"]["individualFacilityUse"][0]["hoursAvailable"][0]["closes"] = "21:00:00"
        patch = parse_facility_use(venue, item, venue.metadata_sources[0], CHECKED_AT)
        metadata = apply_metadata_patch(venue, patch)
        self.assertNotIn(MetadataField.OPENING_HOURS, patch.values)
        self.assertIsNone(metadata.opening_hours)
        self.assertEqual(metadata.court_count, 8)

    def test_source_fetches_curated_item_once_and_rejects_missing_mapping(self):
        venue = VENUES["hounslow-gunnersbury-park-sports-hub"]
        calls = []
        source = OpenActiveSource(fetch_json=lambda url: calls.append(url) or fixture("better_gunnersbury.json"))
        patch = asyncio.run(source.fetch_metadata(venue))
        metadata = apply_metadata_patch(venue, patch)
        self.assertEqual(calls, [venue.metadata_sources[0]])
        self.assertEqual(metadata.court_count, 8)
        self.assertIsNotNone(patch.checked_at.tzinfo)
        missing = VENUES["islington-highbury-fields"]
        with self.assertRaises(ValueError):
            asyncio.run(source.fetch_metadata(missing))
        self.assertEqual(calls, [venue.metadata_sources[0]])


if __name__ == "__main__":
    unittest.main()
