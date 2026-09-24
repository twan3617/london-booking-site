"""Read Playtomic's public padel availability response."""

import asyncio
import json
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
from uuid import UUID
from zoneinfo import ZoneInfo

from ingestion.models import AvailabilitySlot, Venue


LONDON = ZoneInfo("Europe/London")
BOOKING_PATTERN = re.compile(r"/tenant/([0-9a-f-]+)$")


def _tenant_id(venue: Venue) -> tuple[str, str]:
    if venue.sport != "padel" or len(venue.availability_urls) != 1:
        raise ValueError(f"No Playtomic availability source: {venue.id}")
    source = urlparse(venue.availability_urls[0])
    booking = urlparse(venue.booking_url)
    query = parse_qs(source.query)
    booking_match = BOOKING_PATTERN.fullmatch(booking.path)
    tenant_ids = query.get("tenant_id", [])
    try:
        tenant_id = str(UUID(tenant_ids[0])) if len(tenant_ids) == 1 else ""
    except ValueError:
        tenant_id = ""
    if (source.scheme != "https" or source.netloc != "playtomic.com" or source.path != "/api/clubs/availability"
            or source.fragment or set(query) != {"tenant_id", "sport_id"} or query.get("sport_id") != ["PADEL"]
            or booking.scheme != "https" or booking.netloc != "playtomic.io" or booking_match is None
            or tenant_id != tenant_ids[0] or booking_match.group(1) != tenant_id):
        raise ValueError(f"No Playtomic availability source: {venue.id}")
    return venue.availability_urls[0], tenant_id


def _price_pence(value: object) -> int:
    match = re.fullmatch(r"(\d+(?:\.\d{1,2})?) GBP", value) if isinstance(value, str) else None
    try:
        pence = Decimal(match.group(1)) * 100 if match else None
    except InvalidOperation:
        pence = None
    if pence is None or pence != pence.to_integral_value():
        raise ValueError("Invalid Playtomic price")
    return int(pence)


def parse_slots(venue: Venue, payload: object, play_date: date, detected_at: datetime) -> tuple[AvailabilitySlot, ...]:
    _, tenant_id = _tenant_id(venue)
    if not isinstance(payload, list):
        raise ValueError("Playtomic response must contain resources")
    booking_url = f"https://playtomic.io/tenant/{tenant_id}?q=PADEL~{play_date.isoformat()}~~~"
    slots = []
    seen = set()
    for resource in payload:
        if (not isinstance(resource, dict) or not isinstance(resource.get("resource_id"), str) or not resource["resource_id"]
                or resource.get("start_date") != play_date.isoformat() or not isinstance(resource.get("slots"), list)):
            raise ValueError("Invalid Playtomic resource")
        for row in resource["slots"]:
            if not isinstance(row, dict) or type(row.get("duration")) is not int or not 0 < row["duration"] <= 1440:
                raise ValueError("Invalid Playtomic slot")
            try:
                start = datetime.fromisoformat(f"{play_date.isoformat()}T{row.get('start_time')}")
            except (TypeError, ValueError):
                raise ValueError("Invalid Playtomic start time") from None
            if start.tzinfo is not None:
                raise ValueError("Invalid Playtomic start time")
            start = start.replace(tzinfo=LONDON)
            end = start + timedelta(minutes=row["duration"])
            key = (resource["resource_id"], start, end)
            if key in seen:
                raise ValueError("Duplicate Playtomic slot")
            seen.add(key)
            slots.append(AvailabilitySlot(
                venue_id=venue.id,
                court_id=resource["resource_id"],
                start_time=start,
                end_time=end,
                available=True,
                price_pence=_price_pence(row.get("price")),
                booking_url=booking_url,
                detected_at=detected_at,
            ))
    return tuple(slots)


def _fetch_json(url):
    request = Request(url, headers={"User-Agent": "LondonCourtAvailability/0.1 (public availability check)"})
    with urlopen(request, timeout=20) as response:
        return json.load(response)


class PlaytomicAvailabilitySource:
    def __init__(self, fetch_json=None):
        self.fetch_json = fetch_json or _fetch_json

    async def fetch_availability(self, venue: Venue, start_date: date, end_date: date) -> tuple[AvailabilitySlot, ...]:
        source, _ = _tenant_id(venue)
        if end_date < start_date:
            raise ValueError("Availability end date precedes start date")
        detected_at = datetime.now(timezone.utc)
        slots = []
        play_date = start_date
        while play_date <= end_date:
            payload = await asyncio.to_thread(self.fetch_json, f"{source}&{urlencode({'date': play_date.isoformat()})}")
            slots.extend(parse_slots(venue, payload, play_date, detected_at))
            play_date += timedelta(days=1)
        return tuple(slots)
