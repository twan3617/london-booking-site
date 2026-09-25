import asyncio
import unittest
from datetime import datetime, time, timezone
from pathlib import Path

from ingestion.models import MetadataField, apply_metadata_patch
from ingestion.providers.clubspark import ClubSparkSource, parse_clubspark
from ingestion.registry import load_registry
from ingestion.sources import RequestPacer

ROOT = Path(__file__).resolve().parents[1]
VENUES = {venue.id: venue for venue in load_registry(ROOT / "config/venues.yaml")}
CHECKED_AT = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def fixture(name):
    return (ROOT / "tests/fixtures" / name).read_text()


def parsed(venue, html):
    return apply_metadata_patch(venue, parse_clubspark(venue, html, CHECKED_AT, venue.metadata_sources[0]))


class ClubSparkTests(unittest.TestCase):
    def test_brook_green_public_rules(self):
        venue = VENUES["hammersmith-and-fulham-brook-green-tennis"]
        metadata = parsed(venue, fixture("clubspark_brook_green.html"))
        self.assertEqual((metadata.booking_window_days, metadata.release_time), (14, time(10, 15)))
        self.assertEqual((metadata.court_count, metadata.floodlit_court_count, metadata.floodlit), (3, 3, True))
        self.assertEqual(metadata.opening_hours["monday"], ((time(7), time(21)),))
        self.assertEqual(len(metadata.opening_hours), 7)
        self.assertEqual(metadata.source_url, venue.metadata_sources[0])

    def test_finsbury_park_does_not_invent_total_count_or_price_unit(self):
        venue = VENUES["haringey-finsbury-park"]
        metadata = parsed(venue, fixture("clubspark_finsbury_park.html"))
        self.assertEqual((metadata.booking_window_days, metadata.release_time), (7, time(0)))
        self.assertEqual(metadata.name, venue.name)
        self.assertIsNone(metadata.court_count)
        self.assertEqual((metadata.floodlit_court_count, metadata.floodlit), (6, True))
        self.assertEqual(metadata.opening_hours["sunday"], ((time(7), time(22)),))
        self.assertEqual(metadata.prices, ())

    def test_cottenham_park_free_next_day_rule(self):
        venue = VENUES["merton-cottenham-park"]
        metadata = parsed(venue, fixture("clubspark_cottenham_park.html"))
        self.assertEqual((metadata.booking_window_days, metadata.release_time), (1, time(22)))
        self.assertEqual((metadata.court_count, metadata.surface), (6, ("hard",)))
        self.assertIsNone(metadata.floodlit)
        self.assertIsNone(metadata.opening_hours)
        self.assertIsNone(metadata.slot_duration_minutes)

    def test_missing_rules_stay_unknown(self):
        venue = VENUES["merton-cottenham-park"]
        patch = parse_clubspark(venue, "<html><body><h1>Court booking</h1><p>Book a court with ClubSpark.</p></body></html>", CHECKED_AT, venue.metadata_sources[0])
        metadata = apply_metadata_patch(venue, patch)
        self.assertEqual(dict(patch.values), {})
        self.assertEqual(metadata.name, venue.name)
        self.assertIsNone(metadata.booking_window_days)
        self.assertIsNone(metadata.release_time)
        self.assertIsNone(metadata.court_count)
        self.assertEqual(metadata.prices, ())

    def test_hidden_page_sections_do_not_supply_rules(self):
        venue = VENUES["merton-cottenham-park"]
        html = "<head><title>Bookings can be made 9 days ahead</title></head><body><template><p>Bookings can be made 14 days ahead</p></template><p>Book a court.</p></body>"
        metadata = parsed(venue, html)
        self.assertIsNone(metadata.booking_window_days)

    def test_conflicting_visible_rules_stay_unknown(self):
        venue = VENUES["merton-cottenham-park"]
        html = "<p>Bookings can be made 7 days ahead. Courts are released at 7am.</p><p>Bookings can be made 14 days ahead. Courts are released at 10am.</p>"
        metadata = parsed(venue, html)
        self.assertIsNone(metadata.booking_window_days)
        self.assertIsNone(metadata.release_time)

    def test_conflicting_rules_in_one_paragraph_stay_unknown(self):
        venue = VENUES["merton-cottenham-park"]
        html = "<p>You can book up to 7 days ahead. You can book up to 14 days ahead. Courts are released at 7am. Courts are released at 10am.</p>"
        metadata = parsed(venue, html)
        self.assertIsNone(metadata.booking_window_days)
        self.assertIsNone(metadata.release_time)

    def test_bare_release_hour_stays_unknown(self):
        venue = VENUES["merton-cottenham-park"]
        metadata = parsed(venue, "<p>Courts are released at 9.</p>")
        self.assertIsNone(metadata.release_time)

    def test_source_fetches_the_registered_clubspark_page_for_any_provider(self):
        venue = VENUES["hammersmith-and-fulham-brook-green-tennis"]
        calls = []
        source = ClubSparkSource(
            fetch_html=lambda url: calls.append(url) or fixture("clubspark_brook_green.html"),
            request_pacer=RequestPacer(0),
        )
        patch = asyncio.run(source.fetch_metadata(venue))
        metadata = apply_metadata_patch(venue, patch)
        self.assertEqual(calls, [venue.metadata_sources[0]])
        self.assertEqual(metadata.booking_window_days, 14)
        self.assertIn(MetadataField.BOOKING_WINDOW_DAYS, patch.values)
        self.assertIsNotNone(patch.checked_at.tzinfo)

        gunnersbury = VENUES["hounslow-gunnersbury-park-sports-hub"]
        patch = asyncio.run(source.fetch_metadata(gunnersbury))
        self.assertEqual(calls[-1], "https://clubspark.lta.org.uk/Gunnersburypark")
        self.assertEqual(patch.source_url, calls[-1])

        with self.assertRaisesRegex(ValueError, "No ClubSpark metadata source"):
            asyncio.run(source.fetch_metadata(VENUES["islington-highbury-fields"]))


if __name__ == "__main__":
    unittest.main()
