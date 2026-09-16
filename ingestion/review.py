"""Validate and review normalized venue metadata without writing it."""

from dataclasses import dataclass, fields
from datetime import datetime, time
from decimal import Decimal
from typing import Literal
from urllib.parse import urlparse

from .models import PriceRate, VenueMetadata

WEEKDAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
DIFF_FIELDS = tuple(field.name for field in fields(VenueMetadata) if field.name not in {"venue_id", "last_checked"})


@dataclass(frozen=True)
class ReviewIssue:
    level: Literal["error", "warning"]
    field: str
    message: str


@dataclass(frozen=True)
class FieldChange:
    field: str
    before: object
    after: object
    blocked: bool = False


@dataclass(frozen=True)
class MetadataReview:
    venue_id: str
    name: str
    changes: tuple[FieldChange, ...]
    issues: tuple[ReviewIssue, ...]

    @property
    def safe_to_apply(self):
        return not any(issue.level == "error" for issue in self.issues) and not any(change.blocked for change in self.changes)


def _valid_url(value):
    try:
        parsed = urlparse(value) if isinstance(value, str) else None
        return bool(parsed and parsed.scheme in {"http", "https"} and parsed.hostname)
    except ValueError:
        return False


def _positive_int(value, maximum=None):
    return type(value) is int and value > 0 and (maximum is None or value <= maximum)


def _valid_price(rate):
    return (
        isinstance(rate, PriceRate)
        and isinstance(rate.amount_gbp, Decimal)
        and rate.amount_gbp.is_finite()
        and Decimal("0") < rate.amount_gbp < Decimal("100")
        and _positive_int(rate.duration_minutes, 1440)
        and rate.customer in {None, "nonmember", "member", "adult_standard"}
        and rate.time_band in {None, "peak", "off_peak", "anytime"}
        and (rate.lights_included is None or type(rate.lights_included) is bool)
    )


def _valid_hours(hours):
    if not isinstance(hours, dict) or not hours or not set(hours) <= WEEKDAYS:
        return False
    for periods in hours.values():
        if not isinstance(periods, tuple) or not periods:
            return False
        for period in periods:
            if not isinstance(period, tuple) or len(period) != 2:
                return False
            start, end = period
            if not isinstance(start, time) or not isinstance(end, time) or start.tzinfo or end.tzinfo or start >= end:
                return False
    return True


def validate_metadata(metadata: VenueMetadata) -> tuple[ReviewIssue, ...]:
    issues = []

    def error(field, message):
        issues.append(ReviewIssue("error", field, message))

    if not isinstance(metadata.venue_id, str) or not metadata.venue_id.strip():
        error("venue_id", "Venue ID is required")
    if not isinstance(metadata.name, str) or not metadata.name.strip():
        error("name", "Venue name is required")
    for field in ("booking_url", "source_url"):
        if not _valid_url(getattr(metadata, field)):
            error(field, "HTTP or HTTPS URL required")
    if not isinstance(metadata.last_checked, datetime) or metadata.last_checked.tzinfo is None or metadata.last_checked.utcoffset() is None:
        error("last_checked", "Timezone-aware datetime required")
    if metadata.court_count is not None and not _positive_int(metadata.court_count):
        error("court_count", "Court count must be greater than zero")
    if metadata.floodlit_court_count is not None:
        if not _positive_int(metadata.floodlit_court_count) or metadata.court_count is not None and metadata.floodlit_court_count > metadata.court_count:
            error("floodlit_court_count", "Floodlit court count must be positive and no greater than court count")
    if not isinstance(metadata.surface, tuple) or any(not isinstance(value, str) or not value.strip() for value in metadata.surface):
        error("surface", "Surface values must be non-empty strings")
    for field in ("floodlit", "membership_required"):
        if getattr(metadata, field) is not None and type(getattr(metadata, field)) is not bool:
            error(field, "Boolean or unknown required")
    if not isinstance(metadata.prices, tuple) or any(not _valid_price(rate) for rate in metadata.prices):
        error("prices", "Prices must be between £0 and £100 with a positive duration")
    for field in ("booking_window_days", "member_booking_window_days"):
        value = getattr(metadata, field)
        if value is not None and not _positive_int(value, 60):
            error(field, "Booking window must be between 1 and 60 days")
    if metadata.release_time is not None and not isinstance(metadata.release_time, time):
        error("release_time", "Release time must be a time or unknown")
    if metadata.slot_duration_minutes is not None and not _positive_int(metadata.slot_duration_minutes, 1440):
        error("slot_duration_minutes", "Slot duration must be between 1 and 1440 minutes")
    if metadata.opening_hours is not None and not _valid_hours(metadata.opening_hours):
        error("opening_hours", "Opening hours must contain valid local-time periods")
    return tuple(issues)


def _missing(value):
    return value is None or isinstance(value, (str, tuple, list, dict, set)) and not value


def _collection_shrank(before, after):
    if isinstance(before, dict) and isinstance(after, dict):
        return not before.keys() <= after.keys() or any(
            key in after and _collection_shrank(before[key], after[key]) for key in before
        )
    if isinstance(before, (tuple, list, set)) and isinstance(after, type(before)):
        return len(after) < len(before)
    return False


def review_metadata(existing: VenueMetadata, candidate: VenueMetadata) -> MetadataReview:
    issues = list(validate_metadata(candidate))
    if existing.venue_id != candidate.venue_id:
        issues.append(ReviewIssue("error", "venue_id", "Existing and candidate venue IDs differ"))
    changes = []
    for field in DIFF_FIELDS:
        before, after = getattr(existing, field), getattr(candidate, field)
        if before == after:
            continue
        blocked = not _missing(before) and (_missing(after) or _collection_shrank(before, after))
        changes.append(FieldChange(field, before, after, blocked))
        if blocked:
            issues.append(ReviewIssue("warning", field, "Previously known value disappeared"))
    return MetadataReview(candidate.venue_id, candidate.name, tuple(changes), tuple(issues))


def _display(value):
    return "unknown" if _missing(value) else str(value)


def format_review(review: MetadataReview) -> str:
    lines = [review.name]
    if not review.changes:
        lines.append("No metadata changes.")
    for change in review.changes:
        lines.extend((change.field, f"  old: {_display(change.before)}", f"  new: {_display(change.after)}"))
        if change.blocked:
            lines.append("  status: blocked")
    if review.issues:
        lines.append("Issues:")
        lines.extend(f"  {issue.level}: {issue.field}: {issue.message}" for issue in review.issues)
    return "\n".join(lines)
