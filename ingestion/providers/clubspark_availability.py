"""Normalize a supplied ClubSpark booking-sheet response; no live fetching is configured."""

import asyncio
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode, urlparse
from zoneinfo import ZoneInfo

from ingestion.models import AvailabilitySlot, Venue


LONDON = ZoneInfo("Europe/London")


def _venue_slug(venue: Venue) -> str:
    booking = urlparse(venue.booking_url)
    parts = booking.path.strip("/").split("/")
    if (venue.provider != "clubspark" or booking.scheme != "https" or booking.hostname != "clubspark.lta.org.uk"
            or not parts[0] or parts[1:] not in ([], ["Booking", "BookByDate"])):
        raise ValueError(f"No ClubSpark booking sheet: {venue.id}")
    return parts[0]


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


def parse_sessions(venue: Venue, payload: dict, play_date: date, detected_at: datetime) -> tuple[AvailabilitySlot, ...]:
    slug = _venue_slug(venue)
    if not isinstance(payload, dict) or payload.get("TimeZone") != "Europe/London":
        raise ValueError("Invalid ClubSpark timezone")
    resources = payload.get("Resources")
    if not isinstance(resources, list):
        raise ValueError("ClubSpark response must contain resources")
    booking_url = f"https://clubspark.lta.org.uk/{slug}/Booking/BookByDate#?date={play_date.isoformat()}"
    midnight = datetime.combine(play_date, time.min, LONDON)
    slots = []
    seen = set()
    for resource in resources:
        if not isinstance(resource, dict) or not isinstance(resource.get("ID"), str) or not resource["ID"] or not isinstance(resource.get("Days"), list):
            raise ValueError("Invalid ClubSpark court")
        for day in resource["Days"]:
            if not isinstance(day, dict) or day.get("Date") != f"{play_date.isoformat()}T00:00:00" or not isinstance(day.get("Sessions"), list):
                raise ValueError("ClubSpark date mismatch")
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
                    key = (resource["ID"], minute)
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
    return tuple(slots)


class ClubSparkAvailabilitySource:
    def __init__(self, fetch_json):
        self.fetch_json = fetch_json

    async def fetch_availability(self, venue: Venue, start_date: date, end_date: date) -> tuple[AvailabilitySlot, ...]:
        slug = _venue_slug(venue)
        if end_date < start_date:
            raise ValueError("Availability end date precedes start date")
        detected_at = datetime.now(timezone.utc)
        slots = []
        play_date = start_date
        while play_date <= end_date:
            url = f"https://clubspark.lta.org.uk/v0/VenueBooking/{slug}/GetVenueSessions?{urlencode({'resourceID': '', 'startDate': play_date.isoformat(), 'endDate': play_date.isoformat(), 'roleId': ''})}"
            payload = await asyncio.to_thread(self.fetch_json, url)
            slots.extend(parse_sessions(venue, payload, play_date, detected_at))
            play_date += timedelta(days=1)
        return tuple(slots)
