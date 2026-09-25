"""Read curated OpenActive FacilityUse items as venue metadata."""

import argparse
import asyncio
import json
from datetime import datetime, time, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from ingestion.models import MetadataField, MetadataPatch, Venue
from ingestion.registry import _web_url, load_registry
from ingestion.sources import RequestPacer

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
FACILITY_TYPES = {
    "tennis": "https://openactive.io/facility-types#becfafc0-c63f-444c-aed5-a3665f2d172d",
    "squash": "https://openactive.io/facility-types#a1f82b7a-1258-4d9a-8dc5-bfc2ae961651",
}


def _weekly_hours(specifications):
    if not isinstance(specifications, list) or not specifications:
        return None
    days = {day: [] for day in WEEKDAYS}
    for specification in specifications:
        if not isinstance(specification, dict) or specification.get("@type") != "OpeningHoursSpecification":
            return None
        try:
            start = time.fromisoformat(specification["opens"])
            end = time.fromisoformat(specification["closes"])
        except (KeyError, TypeError, ValueError):
            return None
        if start.tzinfo or end.tzinfo or start >= end:
            return None
        listed = specification.get("dayOfWeek")
        if not isinstance(listed, list) or not listed:
            return None
        for uri in listed:
            day = uri.rsplit("/", 1)[-1].lower() if isinstance(uri, str) else ""
            if day not in days:
                return None
            days[day].append((start, end))
    return {day: tuple(sorted(periods)) for day, periods in days.items()} if all(days.values()) else None


def parse_facility_use(venue: Venue, item: dict, source_url: str, checked_at: datetime) -> MetadataPatch:
    if not isinstance(item, dict) or item.get("state") != "updated" or item.get("kind") != "FacilityUse":
        raise ValueError("Updated FacilityUse item required")
    if item.get("id") != source_url.rsplit("/", 1)[-1]:
        raise ValueError("RPDE item identity mismatch")
    data = item.get("data")
    if not isinstance(data, dict) or data.get("@type") != "FacilityUse" or data.get("@id") != source_url:
        raise ValueError("FacilityUse source identity mismatch")
    types = data.get("facilityType")
    expected_type = FACILITY_TYPES.get(venue.sport)
    type_ids = [entry.get("@id") for entry in types if isinstance(entry, dict) and entry.get("@type") == "Concept"] if isinstance(types, list) else []
    if expected_type is None or type_ids != [expected_type]:
        raise ValueError("FacilityUse sport mismatch")
    location = data.get("location")
    if not isinstance(location, dict) or not isinstance(location.get("name"), str) or not location["name"].strip():
        raise ValueError("FacilityUse place name required")
    booking_url = _web_url(data.get("url"), "OpenActive booking URL")
    courts = data.get("individualFacilityUse")
    if not isinstance(courts, list) or not courts:
        raise ValueError("Individual courts required")
    court_prefix = f'{data["@id"]}/individual-facility-uses/'
    ids = [court.get("@id") for court in courts if isinstance(court, dict) and court.get("@type") == "IndividualFacilityUse" and court.get("url") == booking_url]
    if len(ids) != len(courts) or any(not isinstance(court_id, str) or not court_id.startswith(court_prefix) or court_id == court_prefix for court_id in ids) or len(set(ids)) != len(ids):
        raise ValueError("Individual court identity mismatch")
    # ponytail: curated homogeneous FacilityUse records; add per-court mappings before using mixed-venue records.
    hours = [_weekly_hours(court.get("hoursAvailable")) for court in courts]
    opening_hours = hours[0] if hours[0] is not None and all(value == hours[0] for value in hours) else None
    observed = {
        MetadataField.NAME: location["name"].strip(),
        MetadataField.BOOKING_URL: booking_url if booking_url == venue.booking_url else None,
        MetadataField.COURT_COUNT: len(courts),
        MetadataField.FLOODLIT: True if data.get("name") == "Tennis Court (Floodlit)" else None,
        MetadataField.OPENING_HOURS: opening_hours,
    }
    return MetadataPatch(
        venue_id=venue.id,
        source_url=source_url,
        checked_at=checked_at,
        values={field: value for field, value in observed.items() if value is not None},
    )


def _fetch_json(url):
    request = Request(url, headers={"User-Agent": "LondonCourtMetadata/0.1 (public metadata check)", "Accept": "application/json"})
    with urlopen(request, timeout=15) as response:
        return json.load(response)


class OpenActiveSource:
    def __init__(self, fetch_json=None, request_pacer=None):
        self.fetch_json = fetch_json or _fetch_json
        self.request_pacer = request_pacer or RequestPacer(10, 2)

    async def fetch_metadata(self, venue: Venue) -> MetadataPatch:
        source_url = next((url for url in venue.metadata_sources if "/api/openactive/" in url and "/facility-uses/" in url), None)
        if source_url is None:
            raise ValueError(f"No curated OpenActive FacilityUse item: {venue.id}")
        item = await self.request_pacer.run(self.fetch_json, source_url)
        return parse_facility_use(venue, item, source_url, datetime.now(timezone.utc))


def main():
    parser = argparse.ArgumentParser(description="Preview one OpenActive FacilityUse venue")
    parser.add_argument("venue_id")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    venue = next((item for item in load_registry(root / "config/venues.yaml") if item.id == args.venue_id), None)
    if venue is None:
        parser.error(f"Unknown venue ID: {args.venue_id}")
    metadata = asyncio.run(OpenActiveSource().fetch_metadata(venue))
    print(json.dumps({
        "venue_id": metadata.venue_id,
        "source_url": metadata.source_url,
        "checked_at": metadata.checked_at,
        "values": {field.value: value for field, value in metadata.values.items()},
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
