"""Read explicitly published ClubSpark tennis metadata from public HTML."""

import argparse
import asyncio
import json
import re
from datetime import datetime, time, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

from ingestion.models import MetadataField, MetadataPatch, Venue
from ingestion.registry import load_registry

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


class _VisibleParagraphs(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.paragraphs = []
        self.current = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"head", "template", "script", "style", "noscript", "svg"}:
            self.hidden += 1
        if tag == "br" and not self.hidden:
            self.current.append(" ")

    def handle_endtag(self, tag):
        if tag in {"head", "template", "script", "style", "noscript", "svg"} and self.hidden:
            self.hidden -= 1
        if tag in {"p", "li", "h1", "h2", "h3"} and not self.hidden:
            self._flush()

    def handle_data(self, data):
        if self.hidden:
            return
        self.current.append(data)

    def _flush(self):
        paragraph = " ".join(" ".join(self.current).split())
        if paragraph:
            self.paragraphs.append(paragraph)
        self.current = []


def _number(raw):
    return int(raw) if raw.isdigit() else NUMBER_WORDS.get(raw.lower())


def _clock(raw):
    if raw.lower() == "midnight":
        return time(0)
    match = re.fullmatch(r"(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?", raw, re.I)
    if not match or (match[2] is None and match[3] is None):
        return None
    hour, minute, meridiem = int(match[1]), int(match[2] or 0), match[3]
    if minute > 59 or (meridiem and not 1 <= hour <= 12) or (not meridiem and hour > 23):
        return None
    if meridiem:
        hour = hour % 12 + (12 if meridiem.lower() == "pm" else 0)
    return time(hour, minute)


def parse_clubspark(venue: Venue, html: str, checked_at: datetime, source_url: str) -> MetadataPatch:
    page = _VisibleParagraphs()
    page.feed(html)
    page._flush()
    windows, releases = set(), set()
    court_count = floodlit_count = None
    surface = ()
    floodlit = None
    hours = None
    for paragraph in page.paragraphs:
        text = paragraph.lower()
        for days in re.finditer(r"(?:book(?:ed|ings)?\s+(?:can be made\s+|up\s?to\s+)?|bookings? can be made\s+)(\d+)\s+days?\s+(?:ahead|in advance)", text):
            windows.add(int(days[1]))
        if re.search(r"(?:free )?bookings? can be made 24 hours in advance", text):
            windows.add(1)

        if "released" in text or "booking for the whole day" in text or "slots for" in text:
            for clock in re.finditer(r"(?:open(?:s)?|released) at\s+(midnight|\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm)?)\b", paragraph, re.I):
                parsed = _clock(clock[1])
                if parsed is not None:
                    releases.add(parsed)

        standard = re.search(r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:tarmac macadam\s+|hard\s+|clay\s+|grass\s+)?tennis courts\b", text)
        if standard:
            court_count = _number(standard[1])
        lit_and_mini = re.search(r"(\d+)\s+floodlit courts?\s+and\s+\d+\s+mini tennis courts?", text)
        if lit_and_mini:
            court_count = int(lit_and_mini[1])
        lit = re.search(r"(\d+)\s+floodlit courts?", text)
        if lit:
            floodlit_count = int(lit[1])
        lit_subset = re.search(r"flood\s*lights? for (\d+) of our courts", text)
        if lit_subset:
            floodlit_count = int(lit_subset[1])
        if floodlit_count is not None:
            floodlit = True
        elif re.search(r"\bno flood\s*lights?\b", text):
            floodlit = False

        if "tarmac macadam tennis courts" in text or re.search(r"\bhard tennis courts\b", text):
            surface = ("hard",)
        elif re.search(r"\bclay tennis courts\b", text):
            surface = ("clay",)
        elif re.search(r"\bgrass tennis courts\b", text):
            surface = ("grass",)

        daily = re.search(r"available from\s+(\d{1,2}:\d{2})\s+to\s+(\d{1,2}:\d{2})\s+seven days a week", text)
        mon_sun = re.search(r"monday to sunday\s+(\d{1,2}(?:am|pm))\s*[-–]\s*(\d{1,2}(?:am|pm))", text)
        match = daily or mon_sun
        if match:
            start, end = _clock(match[1]), _clock(match[2])
            if start and end:
                hours = {day: ((start, end),) for day in WEEKDAYS}

    observed = {
        MetadataField.COURT_COUNT: court_count,
        MetadataField.FLOODLIT_COURT_COUNT: floodlit_count,
        MetadataField.SURFACE: surface,
        MetadataField.FLOODLIT: floodlit,
        MetadataField.BOOKING_WINDOW_DAYS: next(iter(windows)) if len(windows) == 1 else None,
        MetadataField.RELEASE_TIME: next(iter(releases)) if len(releases) == 1 else None,
        MetadataField.OPENING_HOURS: hours,
    }
    return MetadataPatch(
        venue_id=venue.id,
        source_url=source_url,
        checked_at=checked_at,
        values={field: value for field, value in observed.items() if value is not None and value != ()},
    )


def _fetch_html(url):
    request = Request(url, headers={"User-Agent": "LondonCourtMetadata/0.1 (public metadata check)"})
    with urlopen(request, timeout=15) as response:
        return response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")


class ClubSparkSource:
    def __init__(self, fetch_html=None):
        self.fetch_html = fetch_html or _fetch_html

    async def fetch_metadata(self, venue: Venue) -> MetadataPatch:
        source_url = next((url for url in venue.metadata_sources if url.startswith("https://clubspark.lta.org.uk/")), None)
        if source_url is None:
            raise ValueError(f"No ClubSpark metadata source: {venue.id}")
        html = await asyncio.to_thread(self.fetch_html, source_url)
        return parse_clubspark(venue, html, datetime.now(timezone.utc), source_url)


def main():
    parser = argparse.ArgumentParser(description="Preview one ClubSpark venue's public metadata")
    parser.add_argument("venue_id")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    venue = next((item for item in load_registry(root / "config/venues.yaml") if item.id == args.venue_id), None)
    if venue is None:
        parser.error(f"Unknown venue ID: {args.venue_id}")
    metadata = asyncio.run(ClubSparkSource().fetch_metadata(venue))
    print(json.dumps({
        "venue_id": metadata.venue_id,
        "source_url": metadata.source_url,
        "checked_at": metadata.checked_at,
        "values": {field.value: value for field, value in metadata.values.items()},
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
