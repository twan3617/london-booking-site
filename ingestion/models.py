"""Provider-independent venue and observed metadata types."""

from dataclasses import dataclass, replace
from datetime import datetime, time
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Literal, Mapping
from urllib.parse import urlparse

Sport = Literal["tennis", "squash", "padel"]
Provider = Literal["clubspark", "better", "parksports", "html"]


@dataclass(frozen=True)
class Venue:
    id: str
    name: str
    sport: Sport
    provider: Provider
    booking_url: str
    metadata_sources: tuple[str, ...]


@dataclass(frozen=True)
class PriceRate:
    amount_gbp: Decimal
    duration_minutes: int
    customer: Literal["nonmember", "member", "adult_standard"] | None = None
    time_band: Literal["peak", "off_peak", "anytime"] | None = None
    lights_included: bool | None = None


@dataclass(frozen=True)
class VenueMetadata:
    venue_id: str
    name: str
    booking_url: str
    last_checked: datetime
    source_url: str
    court_count: int | None = None
    floodlit_court_count: int | None = None
    surface: tuple[str, ...] = ()
    floodlit: bool | None = None
    prices: tuple[PriceRate, ...] = ()
    booking_window_days: int | None = None
    member_booking_window_days: int | None = None
    release_time: time | None = None
    slot_duration_minutes: int | None = None
    opening_hours: dict[str, tuple[tuple[time, time], ...]] | None = None
    membership_required: bool | None = None


class MetadataField(StrEnum):
    NAME = "name"
    BOOKING_URL = "booking_url"
    COURT_COUNT = "court_count"
    FLOODLIT_COURT_COUNT = "floodlit_court_count"
    SURFACE = "surface"
    FLOODLIT = "floodlit"
    PRICES = "prices"
    BOOKING_WINDOW_DAYS = "booking_window_days"
    MEMBER_BOOKING_WINDOW_DAYS = "member_booking_window_days"
    RELEASE_TIME = "release_time"
    SLOT_DURATION_MINUTES = "slot_duration_minutes"
    OPENING_HOURS = "opening_hours"
    MEMBERSHIP_REQUIRED = "membership_required"


@dataclass(frozen=True)
class MetadataPatch:
    venue_id: str
    source_url: str
    checked_at: datetime
    values: Mapping[MetadataField, object]

    def __post_init__(self):
        parsed = urlparse(self.source_url) if isinstance(self.source_url, str) else None
        if not isinstance(self.venue_id, str) or not self.venue_id.strip():
            raise ValueError("Metadata patch venue ID is required")
        if not parsed or parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Metadata patch source must be an HTTP or HTTPS URL")
        if not isinstance(self.checked_at, datetime) or self.checked_at.tzinfo is None or self.checked_at.utcoffset() is None:
            raise ValueError("Metadata patch checked time must include a timezone")
        values = dict(self.values)
        if any(not isinstance(field, MetadataField) for field in values):
            raise ValueError("Metadata patch keys must be MetadataField values")
        object.__setattr__(self, "values", MappingProxyType(values))


def apply_metadata_patch(venue: Venue, patch: MetadataPatch, existing: VenueMetadata | None = None) -> VenueMetadata:
    if patch.venue_id != venue.id or existing is not None and existing.venue_id != venue.id:
        raise ValueError("Metadata patch venue ID mismatch")
    if patch.source_url not in venue.metadata_sources and patch.source_url != venue.booking_url:
        raise ValueError("Metadata patch source is not registered for venue")
    if existing is not None and patch.checked_at < existing.last_checked:
        raise ValueError("Metadata patch is older than saved metadata")
    base = (
        replace(existing, name=venue.name, booking_url=venue.booking_url)
        if existing is not None
        else VenueMetadata(
            venue_id=venue.id,
            name=venue.name,
            booking_url=venue.booking_url,
            last_checked=patch.checked_at,
            source_url=patch.source_url,
        )
    )
    return replace(
        base,
        last_checked=patch.checked_at,
        source_url=patch.source_url,
        **{field.value: value for field, value in patch.values.items()},
    )
