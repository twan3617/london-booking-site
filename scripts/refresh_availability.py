"""Refresh the small set of configured live availability sources."""

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingestion.providers.better import BetterAvailabilitySource
from ingestion.providers.clubspark_availability import ClubSparkAvailabilitySource
from ingestion.providers.playtomic import PlaytomicAvailabilitySource
from ingestion.registry import load_registry

OUTPUT = ROOT / "data/availability.json"
LONDON = ZoneInfo("Europe/London")
DAYS_AHEAD = 5


def _slot_json(slot):
    return {
        "venue_id": slot.venue_id,
        "court_id": slot.court_id,
        "start_time": slot.start_time.isoformat(),
        "end_time": slot.end_time.isoformat(),
        "available": slot.available,
        "price_pence": slot.price_pence,
        "booking_url": slot.booking_url,
        "detected_at": slot.detected_at.isoformat(),
        "booking_opens_at": slot.booking_opens_at.isoformat() if slot.booking_opens_at else None,
    }


def _save(output: Path, payload: dict):
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(output)


async def refresh_availability(output: Path = OUTPUT):
    now = datetime.now(timezone.utc)
    start_date = now.astimezone(LONDON).date()
    # Better currently exposes today plus five further dates.
    end_date = start_date + timedelta(days=DAYS_AHEAD)
    venues = [venue for venue in load_registry(ROOT / "config/venues.yaml") if venue.availability_urls]
    sources = {
        "better-admin.org.uk": BetterAvailabilitySource(),
        "clubspark.lta.org.uk": ClubSparkAvailabilitySource(),
        "playtomic.com": PlaytomicAvailabilitySource(),
    }
    slots = []
    for venue in venues:
        source_host = urlparse(venue.availability_urls[0]).hostname
        source = sources.get(source_host)
        if source is None:
            raise ValueError(f"No availability source for host: {source_host}")
        venue_slots = await source.fetch_availability(venue, start_date, end_date)
        slots.extend(venue_slots)
        print(f"{venue.name}: {sum(slot.available for slot in venue_slots)} available of {len(venue_slots)} slots")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "coverage_start": start_date.isoformat(),
        "coverage_end": end_date.isoformat(),
        "venue_ids": [venue.id for venue in venues],
        "booking_urls": {venue.id: venue.booking_url for venue in venues},
        "slots": [_slot_json(slot) for slot in slots],
    }
    _save(output, payload)
    print(f"Saved {len(slots)} slots to {output.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(refresh_availability())
