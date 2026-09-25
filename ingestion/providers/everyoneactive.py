"""Read squash metadata from Everyone Active's public timetable API."""

import json
import re
from datetime import datetime, time, timezone
from decimal import Decimal, InvalidOperation
from urllib.request import Request, urlopen

from ingestion.models import MetadataField, MetadataPatch, PriceRate, Venue
from ingestion.sources import RequestPacer

SOURCE_PATTERN = re.compile(r"https://api\.everyoneactive\.com/v1\.0/centres/([^/]+)/timetable")


def _clock(value):
    try:
        parsed = time.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError("Invalid Everyone Active squash hours") from None
    if parsed.tzinfo is not None:
        raise ValueError("Invalid Everyone Active squash hours")
    return parsed


def parse_timetable(venue: Venue, payload: dict, source_url: str, checked_at: datetime) -> MetadataPatch:
    match = SOURCE_PATTERN.fullmatch(source_url)
    items = payload.get("items") if isinstance(payload, dict) else None
    squash = [
        item for item in items or ()
        if isinstance(item, dict)
        and item.get("what") == "Squash"
        and isinstance(item.get("description"), str)
        and re.fullmatch(r"Squash - \d+ Minutes", item["description"])
    ]
    if venue.sport != "squash" or match is None or len(squash) != 1 or squash[0].get("site_id") != match.group(1):
        raise ValueError("One matching Everyone Active squash timetable is required")
    item = squash[0]
    raw_duration = item.get("duration")
    duration_match = re.fullmatch(r"(\d+) Minute Sessions", raw_duration) if isinstance(raw_duration, str) else None
    duration = int(duration_match.group(1)) if duration_match else 0
    if duration <= 0:
        raise ValueError("Invalid Everyone Active squash duration")

    raw_prices = item.get("prices")
    adult = raw_prices.get("adult") if isinstance(raw_prices, dict) else None
    if not isinstance(adult, dict):
        raise ValueError("Everyone Active adult squash prices are required")
    try:
        peak, off_peak = Decimal(adult["peak"]), Decimal(adult["off_peak"])
    except (KeyError, TypeError, InvalidOperation):
        raise ValueError("Invalid Everyone Active squash prices") from None
    if peak <= 0 or off_peak <= 0:
        raise ValueError("Invalid Everyone Active squash prices")
    prices = (
        (PriceRate(peak, duration, "adult_standard", "anytime"),)
        if peak == off_peak
        else (
            PriceRate(peak, duration, "adult_standard", "peak"),
            PriceRate(off_peak, duration, "adult_standard", "off_peak"),
        )
    )

    raw_hours = item.get("times")
    if not isinstance(raw_hours, dict) or not raw_hours:
        raise ValueError("Everyone Active squash hours are required")
    hours = {}
    for day, periods in raw_hours.items():
        if not isinstance(day, str) or not isinstance(periods, list) or not periods:
            raise ValueError("Invalid Everyone Active squash hours")
        parsed = tuple(sorted((_clock(period.get("start")), _clock(period.get("end"))) for period in periods if isinstance(period, dict)))
        if len(parsed) != len(periods) or any(start >= end for start, end in parsed):
            raise ValueError("Invalid Everyone Active squash hours")
        hours[day.lower()] = parsed

    return MetadataPatch(venue.id, source_url, checked_at, {
        MetadataField.PRICES: prices,
        MetadataField.SLOT_DURATION_MINUTES: duration,
        MetadataField.OPENING_HOURS: hours,
    })


def _fetch_json(url):
    request = Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "LondonCourtMetadata/0.1 (public metadata check)",
    })
    with urlopen(request, timeout=15) as response:
        return json.load(response)


class EveryoneActiveMetadataSource:
    def __init__(self, fetch_json=None, request_pacer=None):
        self.fetch_json = fetch_json or _fetch_json
        self.request_pacer = request_pacer or RequestPacer(10, 4)

    async def fetch_metadata(self, venue: Venue) -> MetadataPatch:
        source_url = next((url for url in venue.metadata_sources if SOURCE_PATTERN.fullmatch(url)), None)
        if source_url is None:
            raise ValueError(f"No Everyone Active timetable source: {venue.id}")
        payload = await self.request_pacer.run(self.fetch_json, source_url)
        return parse_timetable(venue, payload, source_url, datetime.now(timezone.utc))
