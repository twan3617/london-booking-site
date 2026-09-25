"""Read squash metadata from Places Leisure's embedded timetable."""

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.request import Request, urlopen

from ingestion.models import MetadataField, MetadataPatch, Venue
from ingestion.sources import LONDON, RequestPacer

SOURCE_PREFIX = "https://www.placesleisure.org/centres/"
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


class _TimetableDataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.value = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "input" and attributes.get("id") == "timetable-data":
            self.value = attributes.get("value")


def _timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise ValueError("Invalid Places Leisure squash session time") from None
    if parsed.tzinfo is None:
        raise ValueError("Invalid Places Leisure squash session time")
    return parsed


def parse_timetable(venue: Venue, page: str, source_url: str, checked_at: datetime) -> MetadataPatch:
    parser = _TimetableDataParser()
    parser.feed(page)
    try:
        payload = json.loads(parser.value)
        timetables = payload["timetables"]
    except (KeyError, TypeError, json.JSONDecodeError):
        raise ValueError("Places Leisure timetable data is required") from None

    activity_ids = {
        activity["id"]
        for timetable in timetables if isinstance(timetable, dict)
        for activity in timetable.get("activities", ()) if isinstance(activity, dict)
        if activity.get("name") == "Squash" and activity.get("webBookable") is True and isinstance(activity.get("id"), str)
    }
    if venue.sport != "squash" or not source_url.startswith(SOURCE_PREFIX) or len(activity_ids) != 1:
        raise ValueError("One web-bookable Places Leisure squash activity is required")

    sessions = [
        session
        for timetable in timetables if isinstance(timetable, dict)
        for session in timetable.get("sessions", ()) if isinstance(session, dict)
        if session.get("aId") in activity_ids and session.get("ag") == "SQUASH"
    ]
    if not sessions:
        raise ValueError("Places Leisure squash sessions are required")

    intervals = []
    durations = set()
    for session in sessions:
        start = _timestamp(session.get("s"))
        end = _timestamp(session.get("e")) + timedelta(seconds=1)
        seconds = (end - start).total_seconds()
        if seconds <= 0 or seconds % 60:
            raise ValueError("Invalid Places Leisure squash session duration")
        durations.add(int(seconds // 60))
        intervals.append((start.astimezone(LONDON), end.astimezone(LONDON)))
    if len(durations) != 1:
        raise ValueError("Places Leisure squash sessions must have one duration")

    by_date = defaultdict(list)
    for start, end in intervals:
        if start.date() != end.date():
            raise ValueError("Places Leisure squash session crosses a local date")
        by_date[start.date()].append((start, end))
    weekly = {day: set() for day in WEEKDAYS}
    for date, periods in by_date.items():
        periods.sort()
        if any(previous[1] != current[0] for previous, current in zip(periods, periods[1:])):
            continue
        weekly[WEEKDAYS[date.weekday()]].add((periods[0][0].time().replace(tzinfo=None), periods[-1][1].time().replace(tzinfo=None)))
    hours = {
        day: (next(iter(windows)),)
        for day, windows in weekly.items()
        if len(windows) == 1
    }
    values = {MetadataField.SLOT_DURATION_MINUTES: durations.pop()}
    if len(hours) == 7:
        values[MetadataField.OPENING_HOURS] = hours
    return MetadataPatch(venue.id, source_url, checked_at, values)


def _fetch_html(url):
    request = Request(url, headers={"User-Agent": "LondonCourtMetadata/0.1 (public metadata check)"})
    with urlopen(request, timeout=15) as response:
        return response.read().decode(response.headers.get_content_charset() or "utf-8")


class PlacesLeisureMetadataSource:
    def __init__(self, fetch_html=None, request_pacer=None):
        self.fetch_html = fetch_html or _fetch_html
        self.request_pacer = request_pacer or RequestPacer(10, 3)

    async def fetch_metadata(self, venue: Venue) -> MetadataPatch:
        source_url = next((url for url in venue.metadata_sources if url.startswith(SOURCE_PREFIX)), None)
        if source_url is None:
            raise ValueError(f"No Places Leisure timetable source: {venue.id}")
        page = await self.request_pacer.run(self.fetch_html, source_url)
        return parse_timetable(venue, page, source_url, datetime.now(timezone.utc))
