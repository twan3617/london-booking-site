"""Capabilities implemented by venue data providers."""

from datetime import date
from typing import Protocol

from .models import AvailabilitySlot, MetadataPatch, Venue


class MetadataSource(Protocol):
    async def fetch_metadata(self, venue: Venue) -> MetadataPatch: ...


class AvailabilitySource(Protocol):
    async def fetch_availability(
        self, venue: Venue, start_date: date, end_date: date
    ) -> tuple[AvailabilitySlot, ...]: ...
