"""Read ClubSpark's public booking-sheet response."""

import asyncio
import json
import re
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from ingestion.models import AvailabilitySlot, Venue


LONDON = ZoneInfo("Europe/London")
SOURCE_PATTERN = re.compile(r"/v0/VenueBooking/([^/]+)/GetVenueSessions$")


def _venue_slug(venue: Venue) -> str:
    booking = urlparse(venue.booking_url)
    parts = booking.path.strip("/").split("/")
    if (venue.provider != "clubspark" or booking.scheme != "https" or booking.hostname != "clubspark.lta.org.uk"
            or not parts[0] or parts[1:] not in ([], ["Booking", "BookByDate"])):
        raise ValueError(f"No ClubSpark booking sheet: {venue.id}")
    return parts[0]


def _availability_source(venue: Venue) -> str:
    if len(venue.availability_urls) != 1:
        raise ValueError(f"No ClubSpark availability source: {venue.id}")
    source = urlparse(venue.availability_urls[0])
    match = SOURCE_PATTERN.fullmatch(source.path)
    if (source.scheme != "https" or source.netloc != "clubspark.lta.org.uk" or source.query or source.fragment
            or match is None or match.group(1) != _venue_slug(venue)):
        raise ValueError(f"No ClubSpark availability source: {venue.id}")
    return venue.availability_urls[0]


def _price_pence(value: object) -> int | None:
    if value is None:
        return None
    try:
        pence = Decimal(str(value)) * 100
    except (InvalidOperation, ValueError):
        raise ValueError("Invalid ClubSpark cost") from None
    if not pence.is_finite() or pence < 0 or pence != pence.to_integral_value():
        raise ValueError("Invalid ClubSpark cost")
    return int(pence)


def parse_sessions(venue: Venue, payload: dict, start_date: date, end_date: date, detected_at: datetime) -> tuple[AvailabilitySlot, ...]:
    slug = _venue_slug(venue)
    if end_date < start_date:
        raise ValueError("Availability end date precedes start date")
    if not isinstance(payload, dict) or payload.get("TimeZone") != "Europe/London":
        raise ValueError("Invalid ClubSpark timezone")
    resources = payload.get("Resources")
    if not isinstance(resources, list):
        raise ValueError("ClubSpark response must contain resources")
    expected_dates = {start_date + timedelta(days=offset) for offset in range((end_date - start_date).days + 1)}
    if not resources:
        raise ValueError("ClubSpark date coverage mismatch")
    slots = []
    seen = set()
    for resource in resources:
        if not isinstance(resource, dict) or not isinstance(resource.get("ID"), str) or not resource["ID"] or not isinstance(resource.get("Days"), list):
            raise ValueError("Invalid ClubSpark court")
        resource_dates = set()
        for day in resource["Days"]:
            raw_date = day.get("Date") if isinstance(day, dict) else None
            try:
                play_date = date.fromisoformat(raw_date.removesuffix("T00:00:00"))
            except (AttributeError, ValueError):
                raise ValueError("ClubSpark date mismatch") from None
            if not start_date <= play_date <= end_date or raw_date != f"{play_date.isoformat()}T00:00:00" or not isinstance(day.get("Sessions"), list):
                raise ValueError("ClubSpark date mismatch")
            resource_dates.add(play_date)
            booking_url = f"https://clubspark.lta.org.uk/{slug}/Booking/BookByDate#?date={play_date.isoformat()}"
            midnight = datetime.combine(play_date, time.min, LONDON)
            for session in day["Sessions"]:
                if not isinstance(session, dict):
                    raise ValueError("Invalid ClubSpark session")
                if session.get("Category") != 0:
                    continue
                start, end, interval = (session.get(key) for key in ("StartTime", "EndTime", "Interval"))
                if any(type(value) is not int for value in (start, end, interval)) or not 0 <= start < end <= 1440 or interval <= 0:
                    raise ValueError("Invalid ClubSpark open interval")
                price_pence = _price_pence(session.get("Cost"))
                for minute in range(start, end - interval + 1, interval):
                    key = (resource["ID"], play_date, minute)
                    if key in seen:
                        raise ValueError("Duplicate ClubSpark open slot")
                    seen.add(key)
                    slots.append(AvailabilitySlot(
                        venue_id=venue.id,
                        court_id=resource["ID"],
                        start_time=midnight + timedelta(minutes=minute),
                        end_time=midnight + timedelta(minutes=minute + interval),
                        available=True,
                        price_pence=price_pence,
                        booking_url=booking_url,
                        detected_at=detected_at,
                    ))
        if resource_dates != expected_dates:
            raise ValueError("ClubSpark date coverage mismatch")
    return tuple(slots)


def _fetch_json(url):
    request = Request(url, headers={"User-Agent": "LondonCourtAvailability/0.1 (public availability check)"})
    with urlopen(request, timeout=20) as response:
        return json.load(response)


class ClubSparkAvailabilitySource:
    def __init__(self, fetch_json=None):
        self.fetch_json = fetch_json or _fetch_json
        self.next_request_at = 0.0

    async def fetch_availability(self, venue: Venue, start_date: date, end_date: date) -> tuple[AvailabilitySlot, ...]:
        source = _availability_source(venue)
        if end_date < start_date:
            raise ValueError("Availability end date precedes start date")
        detected_at = datetime.now(timezone.utc)
        url = f"{source}?{urlencode({'resourceID': '', 'startDate': start_date.isoformat(), 'endDate': end_date.isoformat(), 'roleId': ''})}"
        loop = asyncio.get_running_loop()
        if loop.time() < self.next_request_at:
            await asyncio.sleep(self.next_request_at - loop.time())
        payload = await asyncio.to_thread(self.fetch_json, url)
        self.next_request_at = loop.time() + 1
        return parse_sessions(venue, payload, start_date, end_date, detected_at)
