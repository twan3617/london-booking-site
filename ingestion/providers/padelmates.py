"""Read Padel Mates' public padel availability response."""

import json
import re
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from ingestion.models import AvailabilitySlot, Venue
from ingestion.sources import RequestPacer


LONDON = ZoneInfo("Europe/London")
CLUB_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{20,64}")
API_ROOT = "https://fastapi-production-fargate.padelmates.io"


def _club_id(venue: Venue) -> str:
    if venue.sport != "padel" or len(venue.availability_urls) != 1:
        raise ValueError(f"No Padel Mates availability source: {venue.id}")
    source = urlparse(venue.availability_urls[0])
    booking = urlparse(venue.booking_url)
    query = parse_qs(source.query)
    club_ids = query.get("club_id", [])
    club_id = club_ids[0] if len(club_ids) == 1 else ""
    if (source.scheme != "https" or source.netloc != "fastapi-production-fargate.padelmates.io"
            or source.path != "/club/" or source.fragment or set(query) != {"club_id"}
            or CLUB_ID_PATTERN.fullmatch(club_id) is None or booking.scheme != "https"
            or booking.netloc != "padelmates.se" or booking.path != f"/club/{club_id}"
            or booking.query or booking.fragment):
        raise ValueError(f"No Padel Mates availability source: {venue.id}")
    return club_id


def _price_pence(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Invalid Padel Mates price")
    try:
        pence = Decimal(str(value)) * 100
    except InvalidOperation:
        raise ValueError("Invalid Padel Mates price") from None
    if not pence.is_finite() or pence < 0 or pence != pence.to_integral_value():
        raise ValueError("Invalid Padel Mates price")
    return int(pence)


def parse_slots(
    venue: Venue, payload: object, play_date: date, detected_at: datetime
) -> tuple[AvailabilitySlot, ...]:
    _club_id(venue)
    if not isinstance(payload, dict) or not isinstance(payload.get("originalCourts"), list) or not isinstance(payload.get("allSlots"), list):
        raise ValueError("Padel Mates response must contain courts and slots")
    courts = {}
    for court in payload["originalCourts"]:
        if (not isinstance(court, dict) or not isinstance(court.get("_id"), str) or not court["_id"]
                or not isinstance(court.get("sport_type"), str) or court["_id"] in courts):
            raise ValueError("Invalid Padel Mates court")
        courts[court["_id"]] = court["sport_type"]

    slots = []
    seen = set()
    for row in payload["allSlots"]:
        if (not isinstance(row, dict) or not isinstance(row.get("courtId"), str)
                or row["courtId"] not in courts or type(row.get("duration")) is not int
                or not 0 < row["duration"] <= 1440 or type(row.get("reservedIntersection")) is not bool):
            raise ValueError("Invalid Padel Mates slot")
        try:
            start = datetime.fromisoformat(row.get("startDatetime"))
            end = datetime.fromisoformat(row.get("endDatetime"))
        except (TypeError, ValueError):
            raise ValueError("Invalid Padel Mates slot time") from None
        if (start.tzinfo is None or end.tzinfo is None or end <= start
                or end - start != timedelta(minutes=row["duration"])
                or start.astimezone(LONDON).date() != play_date):
            raise ValueError("Invalid Padel Mates slot time")
        price_pence = _price_pence(row.get("price"))
        if courts[row["courtId"]] != "PADEL" or row["reservedIntersection"]:
            continue
        start, end = start.astimezone(LONDON), end.astimezone(LONDON)
        key = (row["courtId"], start, end)
        if key in seen:
            raise ValueError("Duplicate Padel Mates slot")
        seen.add(key)
        slots.append(AvailabilitySlot(
            venue_id=venue.id,
            court_id=row["courtId"],
            start_time=start,
            end_time=end,
            available=True,
            price_pence=price_pence,
            booking_url=venue.booking_url,
            detected_at=detected_at,
        ))
    return tuple(slots)


def _fetch_json(url):
    request = Request(url, headers={"User-Agent": "LondonCourtAvailability/0.1 (public availability check)"})
    with urlopen(request, timeout=20) as response:
        return json.load(response)


class PadelMatesAvailabilitySource:
    def __init__(self, fetch_json=None, request_pacer=None):
        self.fetch_json = fetch_json or _fetch_json
        self.request_pacer = request_pacer or RequestPacer(interval_seconds=10.0)

    async def fetch_availability(self, venue: Venue, start_date: date, end_date: date) -> tuple[AvailabilitySlot, ...]:
        club_id = _club_id(venue)
        if end_date < start_date:
            raise ValueError("Availability end date precedes start date")
        detected_at = datetime.now(timezone.utc)
        slots = []
        play_date = start_date
        while play_date <= end_date:
            start = datetime.combine(play_date, time.min, LONDON)
            end = start + timedelta(days=1, hours=3)
            query = urlencode({
                "club_id": club_id,
                "start_datetime": int(start.timestamp() * 1000),
                "end_datetime": int(end.timestamp() * 1000),
                "lang": "en",
            })
            payload = await self.request_pacer.run(
                self.fetch_json,
                f"{API_ROOT}/player/player_booking/all_courts_slot_prices_v3?{query}",
            )
            slots.extend(parse_slots(venue, payload, play_date, detected_at))
            play_date += timedelta(days=1)
        return tuple(slots)
