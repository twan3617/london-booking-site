"""Read date-scoped availability from Better's public booking frontend."""

import json
import re
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from ingestion.models import AvailabilitySlot, Venue
from ingestion.sources import RequestPacer

LONDON = ZoneInfo("Europe/London")
SOURCE_PATTERN = re.compile(r"/api/activities/venue/([^/]+)/activity/([^/]+)/v2/slots$")
BOOKING_PATTERN = re.compile(r"/location/([^/]+)/[^/]+$")


def _source_parts(venue: Venue, availability_url: str | None = None) -> tuple[str, str]:
    source = availability_url or (venue.availability_urls[0] if len(venue.availability_urls) == 1 else "")
    source_url = urlparse(source)
    booking_url = urlparse(venue.booking_url)
    match = SOURCE_PATTERN.fullmatch(source_url.path)
    booking_match = BOOKING_PATTERN.fullmatch(booking_url.path)
    if (venue.provider != "better" or source_url.scheme != "https" or source_url.netloc != "better-admin.org.uk"
            or source_url.query or source_url.fragment or match is None
            or booking_url.scheme != "https" or booking_url.netloc != "bookings.better.org.uk"
            or booking_match is None or match.group(1) != booking_match.group(1)):
        raise ValueError(f"No Better availability source: {venue.id}")
    return match.groups()


def _clock(value: object, label: str) -> time:
    try:
        parsed = time.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid Better {label}") from None
    if parsed.tzinfo is not None:
        raise ValueError(f"Invalid Better {label}")
    return parsed


def parse_slots(venue: Venue, payload: dict, play_date: date, detected_at: datetime, availability_url: str | None = None) -> tuple[AvailabilitySlot, ...]:
    venue_slug, activity_slug = _source_parts(venue, availability_url)
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError("Better slots response must contain a data list")
    booking_url = f"https://bookings.better.org.uk/location/{venue_slug}/{activity_slug}/{play_date.isoformat()}/by-time"
    slots = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]:
            raise ValueError("Invalid Better slot ID")
        if row["id"] in seen:
            raise ValueError("Duplicate Better slot ID")
        seen.add(row["id"])
        location, row_date = row.get("location"), row.get("date")
        if not isinstance(location, dict) or location.get("venue_slug") != venue_slug or not isinstance(location.get("id"), str):
            raise ValueError("Better slot venue mismatch")
        if row.get("category_slug") != activity_slug:
            raise ValueError("Better slot activity mismatch")
        if not isinstance(row_date, dict) or row_date.get("raw") != play_date.isoformat() or row_date.get("tz") != "Europe/London":
            raise ValueError("Better slot date mismatch")
        starts, ends = row.get("starts_at"), row.get("ends_at")
        if not isinstance(starts, dict) or not isinstance(ends, dict):
            raise ValueError("Better slot times are required")
        start_time = datetime.combine(play_date, _clock(starts.get("format_24_hour"), "start time"), LONDON)
        end_time = datetime.combine(play_date, _clock(ends.get("format_24_hour"), "end time"), LONDON)
        price = row.get("price")
        price_pence = price.get("raw") if isinstance(price, dict) else None
        release = row.get("first_bookable_at")
        if release is not None and not isinstance(release, dict):
            raise ValueError("Invalid Better booking release")
        raw_release = release.get("utc") if release else None
        try:
            booking_opens_at = datetime.fromisoformat(raw_release) if raw_release else None
        except (TypeError, ValueError):
            raise ValueError("Invalid Better booking release") from None
        slots.append(AvailabilitySlot(
            venue_id=venue.id,
            court_id=location["id"],
            start_time=start_time,
            end_time=end_time,
            available=(row.get("action_to_show") or {}).get("status") == "BOOK",
            price_pence=price_pence,
            booking_url=booking_url,
            detected_at=detected_at,
            booking_opens_at=booking_opens_at,
        ))
    return tuple(slots)


def _fetch_json(url: str):
    request = Request(url, headers={
        "Accept": "application/json",
        "Origin": "https://bookings.better.org.uk",
        "Referer": "https://bookings.better.org.uk/",
        "User-Agent": "LondonCourtAvailability/0.1",
    })
    with urlopen(request, timeout=15) as response:
        return json.load(response)


class BetterAvailabilitySource:
    def __init__(self, fetch_json=None, request_pacer=None):
        self.fetch_json = fetch_json or _fetch_json
        self.request_pacer = request_pacer or RequestPacer()

    async def fetch_availability(self, venue: Venue, start_date: date, end_date: date) -> tuple[AvailabilitySlot, ...]:
        for availability_url in venue.availability_urls:
            _source_parts(venue, availability_url)
        if not venue.availability_urls:
            raise ValueError(f"No Better availability source: {venue.id}")
        if end_date < start_date:
            raise ValueError("Availability end date precedes start date")
        detected_at = datetime.now(timezone.utc)
        slots = []
        seen = set()
        play_date = start_date
        while play_date <= end_date:
            for availability_url in venue.availability_urls:
                url = f"{availability_url}?{urlencode({'date': play_date.isoformat()})}"
                payload = await self.request_pacer.run(self.fetch_json, url)
                for slot in parse_slots(venue, payload, play_date, detected_at, availability_url):
                    key = (slot.court_id, slot.start_time, slot.end_time)
                    if key not in seen:
                        seen.add(key)
                        slots.append(slot)
            play_date += timedelta(days=1)
        return tuple(slots)
