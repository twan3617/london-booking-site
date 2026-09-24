"""Read MATCHi's public padel availability response."""

import json
import re
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from ingestion.models import AvailabilitySlot, Venue
from ingestion.sources import RequestPacer


LONDON = ZoneInfo("Europe/London")
FACILITY_PATTERN = re.compile(r"/facilities/(\d+)$")
# ponytail: this is Game4Padel's public widget key; update it if their widget rotates it.
API_KEY = 'game4padel_0rmJK1N(R\\"+)54t$QH2Z'


def _facility_source(venue: Venue) -> tuple[str, int]:
    if venue.sport != "padel" or len(venue.availability_urls) != 1:
        raise ValueError(f"No MATCHi availability source: {venue.id}")
    source = urlparse(venue.availability_urls[0])
    booking = urlparse(venue.booking_url)
    match = FACILITY_PATTERN.fullmatch(source.path)
    if (source.scheme != "https" or source.netloc != "api.matchi.com" or match is None
            or source.query or source.fragment or booking.scheme != "https"
            or booking.netloc != "www.matchi.se" or not booking.path.startswith("/facilities/")
            or booking.query or booking.fragment):
        raise ValueError(f"No MATCHi availability source: {venue.id}")
    return venue.availability_urls[0], int(match.group(1))


def _price_pence(value: object) -> int:
    if not isinstance(value, dict) or value.get("currency") != "GBP" or not isinstance(value.get("amount"), str):
        raise ValueError("Invalid MATCHi price")
    try:
        pence = Decimal(value["amount"]) * 100
    except InvalidOperation:
        raise ValueError("Invalid MATCHi price") from None
    if not pence.is_finite() or pence < 0 or pence != pence.to_integral_value():
        raise ValueError("Invalid MATCHi price")
    return int(pence)


def parse_slots(
    venue: Venue, payload: object, start_date: date, end_date: date, detected_at: datetime
) -> tuple[AvailabilitySlot, ...]:
    _facility_source(venue)
    if not isinstance(payload, list):
        raise ValueError("MATCHi response must contain slots")
    slots = []
    seen = set()
    for row in payload:
        if not isinstance(row, dict) or type(row.get("resourceId")) is not int:
            raise ValueError("Invalid MATCHi slot")
        try:
            start = datetime.fromisoformat(row.get("startDateTime"))
            end = datetime.fromisoformat(row.get("endDateTime"))
        except (TypeError, ValueError):
            raise ValueError("Invalid MATCHi slot time") from None
        if (start.tzinfo is None or end.tzinfo is None or end <= start
                or not start_date <= start.astimezone(LONDON).date() <= end_date
                or end - start > timedelta(days=1)):
            raise ValueError("Invalid MATCHi slot time")
        key = (row["resourceId"], start, end)
        if key in seen:
            raise ValueError("Duplicate MATCHi slot")
        seen.add(key)
        slots.append(AvailabilitySlot(
            venue_id=venue.id,
            court_id=str(row["resourceId"]),
            start_time=start,
            end_time=end,
            available=True,
            price_pence=_price_pence(row.get("price")),
            booking_url=venue.booking_url,
            detected_at=detected_at,
        ))
    return tuple(slots)


def _fetch_json(url):
    request = Request(url, headers={
        "User-Agent": "LondonCourtAvailability/0.1 (public availability check)",
        "x-api-key": API_KEY,
    })
    with urlopen(request, timeout=20) as response:
        return json.load(response)


class MatchiAvailabilitySource:
    def __init__(self, fetch_json=None, request_pacer=None):
        self.fetch_json = fetch_json or _fetch_json
        self.request_pacer = request_pacer or RequestPacer(interval_seconds=10.0)

    async def fetch_availability(self, venue: Venue, start_date: date, end_date: date) -> tuple[AvailabilitySlot, ...]:
        source, facility_id = _facility_source(venue)
        if end_date < start_date:
            raise ValueError("Availability end date precedes start date")
        facility = await self.request_pacer.run(self.fetch_json, source)
        if (not isinstance(facility, dict) or facility.get("id") != facility_id
                or facility.get("resourceTypes") != ["PADEL"] or facility.get("timeZone") != "Europe/London"
                or not isinstance(facility.get("resources"), list) or not facility["resources"]
                or not all(isinstance(resource, str) and resource.isdigit() for resource in facility["resources"])
                or not isinstance(facility.get("urls"), dict)
                or facility["urls"].get("WEB_URL") != venue.booking_url):
            raise ValueError("Invalid MATCHi facility")

        start = datetime.combine(start_date, time.min, LONDON)
        end = datetime.combine(end_date + timedelta(days=1), time.min, LONDON)
        detected_at = datetime.now(timezone.utc)
        slots = []
        for resource_id in facility["resources"]:
            query = urlencode({"startDateTime": start.isoformat(), "endDateTime": end.isoformat()})
            url = f"{source}/resources/{resource_id}/availabilities?{query}"
            payload = await self.request_pacer.run(self.fetch_json, url)
            resource_slots = parse_slots(venue, payload, start_date, end_date, detected_at)
            if any(slot.court_id != resource_id for slot in resource_slots):
                raise ValueError("Invalid MATCHi resource")
            slots.extend(resource_slots)
        return tuple(slots)
