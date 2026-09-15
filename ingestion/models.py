"""Provider-independent venue and observed metadata types."""

from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
from typing import Literal

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
