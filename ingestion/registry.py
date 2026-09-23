"""Load and validate the curated venue registry."""

from pathlib import Path
from urllib.parse import urlparse

import yaml

from .models import Venue

SPORTS = {"tennis", "squash", "padel"}
PROVIDERS = {"clubspark", "better", "parksports", "html"}


def _web_url(value: object, label: str) -> str:
    if not isinstance(value, str) or urlparse(value).scheme not in {"http", "https"} or not urlparse(value).hostname:
        raise ValueError(f"Invalid {label}: {value!r}")
    return value


def load_registry(path: Path) -> tuple[Venue, ...]:
    document = yaml.safe_load(path.read_text())
    if not isinstance(document, dict) or not isinstance(document.get("venues"), list):
        raise ValueError("Registry must contain a venues list")
    venues = []
    seen = set()
    for row in document["venues"]:
        if not isinstance(row, dict):
            raise ValueError("Each venue must be a mapping")
        venue_id = row.get("id")
        if not isinstance(venue_id, str) or not venue_id.strip():
            raise ValueError(f"Invalid venue ID: {venue_id!r}")
        if venue_id in seen:
            raise ValueError(f"Duplicate venue ID: {venue_id}")
        seen.add(venue_id)
        sport, provider = row.get("sport"), row.get("provider")
        if not isinstance(sport, str) or sport not in SPORTS or not isinstance(provider, str) or provider not in PROVIDERS:
            raise ValueError(f"Invalid sport or provider: {venue_id}")
        name = row.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Invalid venue name: {venue_id}")
        sources = row.get("metadata_sources")
        if not isinstance(sources, list) or not sources:
            raise ValueError(f"Missing metadata sources: {venue_id}")
        venues.append(Venue(
            id=venue_id,
            name=name,
            sport=row["sport"],
            provider=row["provider"],
            booking_url=_web_url(row.get("booking_url"), "booking URL"),
            metadata_sources=tuple(_web_url(source, "metadata URL") for source in sources),
            availability_url=_web_url(row["availability_url"], "availability URL") if row.get("availability_url") is not None else None,
        ))
    return tuple(venues)
