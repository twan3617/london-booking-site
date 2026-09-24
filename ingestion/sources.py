"""Capabilities implemented by venue data providers."""

import asyncio
from datetime import date
from time import monotonic
from typing import Protocol

from .models import AvailabilitySlot, MetadataPatch, Venue


class RequestPacer:
    """Limit request starts for one provider."""

    def __init__(self, interval_seconds: float = 1.0):
        self.interval_seconds = interval_seconds
        self._next_request_at = 0.0
        self._lock = asyncio.Lock()

    async def run(self, function, *args):
        async with self._lock:
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
