"""Capabilities implemented by venue data providers."""

import asyncio
from datetime import date
from decimal import Decimal
from time import monotonic
from typing import Protocol
from zoneinfo import ZoneInfo

from .models import AvailabilitySlot, MetadataField, MetadataPatch, PriceRate, Venue

LONDON = ZoneInfo("Europe/London")


def metadata_patch_from_slots(venue: Venue, slots: tuple[AvailabilitySlot, ...]) -> MetadataPatch | None:
    if not slots:
        return None
    durations = {int((slot.end_time - slot.start_time).total_seconds() // 60) for slot in slots}
    prices = tuple(PriceRate(Decimal(price) / 100, duration) for price, duration in sorted({
        (slot.price_pence, int((slot.end_time - slot.start_time).total_seconds() // 60))
        for slot in slots if slot.price_pence
    }))
    releases = {
        ((slot.start_time.astimezone(LONDON).date() - slot.booking_opens_at.astimezone(LONDON).date()).days,
         slot.booking_opens_at.astimezone(LONDON).time().replace(tzinfo=None))
        for slot in slots if slot.booking_opens_at
    }
    values = {MetadataField.PRICES: prices} if prices else {}
    if len(durations) == 1:
        values[MetadataField.SLOT_DURATION_MINUTES] = durations.pop()
    if len(releases) == 1:
        window, release_time = releases.pop()
        if window > 0:
            values[MetadataField.BOOKING_WINDOW_DAYS] = window
            values[MetadataField.RELEASE_TIME] = release_time
    return MetadataPatch(venue.id, venue.availability_urls[0], max(slot.detected_at for slot in slots), values)


class RequestPacer:
    """Limit request starts for one provider."""

    def __init__(self, interval_seconds: float = 1.0, max_requests: int | None = None):
        self.interval_seconds = interval_seconds
        self.max_requests = max_requests
        self._requests = 0
        self._next_request_at = 0.0
        self._lock = asyncio.Lock()

    async def run(self, function, *args):
        async with self._lock:
            if self.max_requests is not None and self._requests >= self.max_requests:
                raise RuntimeError(f"Provider request limit of {self.max_requests} reached")
            self._requests += 1
            delay = self._next_request_at - monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            self._next_request_at = monotonic() + self.interval_seconds
        return await asyncio.to_thread(function, *args)


class MetadataSource(Protocol):
    async def fetch_metadata(self, venue: Venue) -> MetadataPatch: ...


class AvailabilitySource(Protocol):
    async def fetch_availability(
        self, venue: Venue, start_date: date, end_date: date
    ) -> tuple[AvailabilitySlot, ...]: ...
