"""Capability required of a metadata provider."""

from typing import Protocol

from .models import Venue, VenueMetadata


class MetadataSource(Protocol):
    async def fetch_metadata(self, venue: Venue) -> VenueMetadata: ...
