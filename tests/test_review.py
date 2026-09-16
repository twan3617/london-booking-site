import unittest
from dataclasses import replace
from datetime import datetime, time, timezone
from decimal import Decimal

from ingestion.models import PriceRate, VenueMetadata
from ingestion.review import format_review, review_metadata, validate_metadata


def metadata(**changes):
    base = VenueMetadata(
        venue_id="example-court",
        name="Example Court",
        booking_url="https://example.org/book",
        last_checked=datetime(2026, 9, 16, 12, tzinfo=timezone.utc),
        source_url="https://example.org/source",
        court_count=3,
        floodlit_court_count=2,
        surface=("hard",),
        floodlit=True,
        prices=(PriceRate(Decimal("12.50"), 60),),
        booking_window_days=7,
        release_time=time(7),
        slot_duration_minutes=60,
        opening_hours={"monday": ((time(7), time(22)),)},
        membership_required=False,
    )
    return replace(base, **changes)


class MetadataReviewTests(unittest.TestCase):
    def test_valid_metadata_has_no_issues(self):
        self.assertEqual(validate_metadata(metadata()), ())

    def test_invalid_sanity_limits_are_reported_by_field(self):
        candidate = metadata(
            booking_url="not-a-url",
            last_checked=datetime(2026, 9, 16, 12),
            court_count=0,
            floodlit_court_count=4,
            prices=(PriceRate(Decimal("100"), 0),),
            booking_window_days=61,
            slot_duration_minutes=0,
            opening_hours={"monday": ((time(22), time(7)),)},
        )
        fields = {issue.field for issue in validate_metadata(candidate)}
        self.assertEqual(
            fields,
            {"booking_url", "last_checked", "court_count", "floodlit_court_count", "prices", "booking_window_days", "slot_duration_minutes", "opening_hours"},
        )

    def test_malformed_url_and_price_labels_are_reported(self):
        candidate = metadata(
            booking_url="http://[",
            prices=(PriceRate(Decimal("10"), 60, customer="vip", time_band="late", lights_included="yes"),),
        )
        self.assertEqual({issue.field for issue in validate_metadata(candidate)}, {"booking_url", "prices"})

    def test_ordinary_changes_are_safe_and_last_checked_is_not_noise(self):
        existing = metadata()
        candidate = metadata(court_count=4, last_checked=datetime(2026, 9, 17, 12, tzinfo=timezone.utc))
        review = review_metadata(existing, candidate)
        self.assertTrue(review.safe_to_apply)
        self.assertEqual([(change.field, change.before, change.after) for change in review.changes], [("court_count", 3, 4)])
        self.assertEqual(review.issues, ())

    def test_known_values_disappearing_are_blocked(self):
        existing = metadata()
        candidate = metadata(prices=(), booking_window_days=None, opening_hours=None)
        review = review_metadata(existing, candidate)
        self.assertFalse(review.safe_to_apply)
        self.assertEqual({change.field for change in review.changes if change.blocked}, {"prices", "booking_window_days", "opening_hours"})
        self.assertEqual({issue.field for issue in review.issues if issue.level == "warning"}, {"prices", "booking_window_days", "opening_hours"})

    def test_invalid_candidate_and_venue_mismatch_are_not_safe(self):
        review = review_metadata(metadata(), metadata(venue_id="another-court", court_count=0, floodlit_court_count=None))
        self.assertFalse(review.safe_to_apply)
        self.assertEqual({issue.field for issue in review.issues if issue.level == "error"}, {"venue_id", "court_count"})

    def test_text_report_shows_changed_and_blocked_values(self):
        report = format_review(review_metadata(metadata(), metadata(court_count=4, booking_window_days=None)))
        self.assertIn("Example Court", report)
        self.assertIn("court_count\n  old: 3\n  new: 4", report)
        self.assertIn("booking_window_days\n  old: 7\n  new: unknown\n  status: blocked", report)


if __name__ == "__main__":
    unittest.main()
