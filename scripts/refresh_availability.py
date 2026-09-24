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
from ingestion.providers.lta import LtaAvailabilitySource
from ingestion.providers.matchi import MatchiAvailabilitySource
from ingestion.providers.padelmates import PadelMatesAvailabilitySource
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
        "www.lta.org.uk": LtaAvailabilitySource(),
        "api.matchi.com": MatchiAvailabilitySource(),
        "fastapi-production-fargate.padelmates.io": PadelMatesAvailabilitySource(),
        "playtomic.com": PlaytomicAvailabilitySource(),
    }
    venues_by_host = {}
    for venue in venues:
        source_host = urlparse(venue.availability_urls[0]).hostname
        if source_host not in sources:
            raise ValueError(f"No availability source for host: {source_host}")
        venues_by_host.setdefault(source_host, []).append(venue)

    providers = {}
    failed_providers = []
    for source_host, provider_venues in venues_by_host.items():
        slots = []
        try:
            for venue in provider_venues:
                venue_slots = await sources[source_host].fetch_availability(venue, start_date, end_date)
                slots.extend(venue_slots)
                print(f"{venue.name}: {sum(slot.available for slot in venue_slots)} available of {len(venue_slots)} slots")
        except Exception as error:
            failed_providers.append(source_host)
            print(f"{source_host} refresh failed: {error}", file=sys.stderr)
            continue
        providers[source_host] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "coverage_start": start_date.isoformat(),
            "coverage_end": end_date.isoformat(),
            "venue_ids": [venue.id for venue in provider_venues],
            "booking_urls": {venue.id: venue.booking_url for venue in provider_venues},
            "slots": [_slot_json(slot) for slot in slots],
        }
    if not providers:
        raise RuntimeError("All availability providers failed")

    snapshots = list(providers.values())
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "coverage_start": start_date.isoformat(),
        "coverage_end": end_date.isoformat(),
        "venue_ids": [venue_id for snapshot in snapshots for venue_id in snapshot["venue_ids"]],
        "booking_urls": {venue_id: url for snapshot in snapshots for venue_id, url in snapshot["booking_urls"].items()},
        "slots": [slot for snapshot in snapshots for slot in snapshot["slots"]],
        "providers": providers,
        "failed_providers": failed_providers,
    }
    _save(output, payload)
    print(f"Saved {len(payload['slots'])} slots to {output.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(refresh_availability())
