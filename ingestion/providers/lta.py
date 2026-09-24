"""Read LTA Play's public court availability response."""

import asyncio
import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
from uuid import UUID
from zoneinfo import ZoneInfo

from ingestion.models import AvailabilitySlot, Venue


LONDON = ZoneInfo("Europe/London")
BOOKING_PATTERN = re.compile(r"/play/book-a-tennis-court/courts/[^/]+_([0-9a-f-]+)/?$")


def _source(venue: Venue) -> str:
    if venue.sport != "tennis" or len(venue.availability_urls) != 1:
        raise ValueError(f"No LTA availability source: {venue.id}")
    source = urlparse(venue.availability_urls[0])
    booking = urlparse(venue.booking_url)
    query = parse_qs(source.query)
    booking_match = BOOKING_PATTERN.fullmatch(booking.path)
    venue_ids = query.get("venueid", [])
    try:
        venue_id = str(UUID(venue_ids[0])) if len(venue_ids) == 1 else ""
    except ValueError:
        venue_id = ""
    if (source.scheme != "https" or source.netloc != "www.lta.org.uk" or source.path != "/api/courtdetail/availability"
            or source.fragment or set(query) != {"venueid"} or booking.scheme != "https" or booking.netloc != "www.lta.org.uk"
            or booking.query or booking.fragment or booking_match is None or venue_id != venue_ids[0]
            or booking_match.group(1) != venue_id):
        raise ValueError(f"No LTA availability source: {venue.id}")
    return venue.availability_urls[0]


def _price_pence(value: object) -> int:
    try:
        pence = Decimal(str(value)) * 100
    except (InvalidOperation, ValueError):
        raise ValueError("Invalid LTA price") from None
    if not pence.is_finite() or pence < 0 or pence != pence.to_integral_value():
        raise ValueError("Invalid LTA price")
    return int(pence)


def parse_slots(venue: Venue, payload: object, play_date: date, detected_at: datetime) -> tuple[AvailabilitySlot, ...]:
    _source(venue)
    if not isinstance(payload, dict) or not isinstance(payload.get("error"), dict) or payload["error"].get("hasError") is not False:
        raise ValueError("LTA availability error")
    resources, rules = payload.get("venueDetails"), payload.get("rules")
    available_dates = rules.get("availableDates") if isinstance(rules, dict) else None
    if not isinstance(resources, list) or not isinstance(available_dates, list) or play_date.isoformat() not in available_dates:
        raise ValueError("LTA date mismatch")
    slots = []
    seen = set()
    booking_url = f"{venue.booking_url}?{urlencode({'date': play_date.isoformat()})}"
    for resource in resources:
        if not isinstance(resource, dict) or not isinstance(resource.get("id"), str) or not resource["id"] or not isinstance(resource.get("availableSlots"), list):
            raise ValueError("Invalid LTA court")
        for row in resource["availableSlots"]:
            if not isinstance(row, dict):
                raise ValueError("Invalid LTA slot")
            try:
                start = datetime.fromisoformat(row["startTime"])
                end = datetime.fromisoformat(row["endTime"])
            except (KeyError, TypeError, ValueError):
                raise ValueError("Invalid LTA slot time") from None
            if start.tzinfo is not None or end.tzinfo is not None or start.date() != play_date or end <= start:
                raise ValueError("LTA date mismatch")
            start, end = start.replace(tzinfo=LONDON), end.replace(tzinfo=LONDON)
            key = (resource["id"], start, end)
            if key in seen:
                raise ValueError("Duplicate LTA slot")
            seen.add(key)
            slots.append(AvailabilitySlot(
                venue_id=venue.id,
                court_id=resource["id"],
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


class LtaAvailabilitySource:
    def __init__(self, fetch_json=None):
        self.fetch_json = fetch_json or _fetch_json

    async def fetch_availability(self, venue: Venue, start_date: date, end_date: date) -> tuple[AvailabilitySlot, ...]:
        source = _source(venue)
        if end_date < start_date:
            raise ValueError("Availability end date precedes start date")
        detected_at = datetime.now(timezone.utc)
        slots = []
        play_date = start_date
        while play_date <= end_date:
            payload = await asyncio.to_thread(self.fetch_json, f"{source}&{urlencode({'date': play_date.isoformat()})}")
            slots.extend(parse_slots(venue, payload, play_date, detected_at))
            play_date = date.fromordinal(play_date.toordinal() + 1)
        return tuple(slots)
