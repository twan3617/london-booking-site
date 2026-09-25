"""Refresh the small set of configured live availability sources."""

import argparse
import asyncio
import json
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingestion.models import PriceRate
from ingestion.providers.better import BetterAvailabilitySource, metadata_patch_from_slots
from ingestion.providers.lta import LtaAvailabilitySource
from ingestion.providers.matchi import MatchiAvailabilitySource
from ingestion.providers.padelmates import PadelMatesAvailabilitySource
from ingestion.providers.playtomic import PlaytomicAvailabilitySource
from ingestion.registry import load_registry
from ingestion.sources import RequestPacer

OUTPUT = ROOT / "data/availability.json"
LONDON = ZoneInfo("Europe/London")
DAYS_AHEAD = 5
PROVIDERS = {
    "better": ("better-admin.org.uk", BetterAvailabilitySource, 1, 150),
    "royal-parks": ("flow.onl", BetterAvailabilitySource, 1, 20),
    "lta": ("www.lta.org.uk", LtaAvailabilitySource, 1, 1250),
    "matchi": ("api.matchi.com", MatchiAvailabilitySource, 10, 50),
    "padelmates": ("fastapi-production-fargate.padelmates.io", PadelMatesAvailabilitySource, 10, 30),
    "playtomic": ("playtomic.com", PlaytomicAvailabilitySource, 1, 50),
}


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


def _metadata_json(patch):
    values = {}
    for field, value in patch.values.items():
        if isinstance(value, tuple) and all(isinstance(rate, PriceRate) for rate in value):
            value = [{
                "amount_gbp": str(rate.amount_gbp),
                "duration_minutes": rate.duration_minutes,
                "customer": rate.customer,
                "time_band": rate.time_band,
                "lights_included": rate.lights_included,
            } for rate in value]
        elif isinstance(value, time):
            value = value.isoformat()
        values[field.value] = value
    return {"source_url": patch.source_url, "checked_at": patch.checked_at.isoformat(), "values": values}


def _save(output: Path, payload: dict):
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(output)


async def refresh_availability(output: Path = OUTPUT, provider: str | None = None, plan: bool = False):
    now = datetime.now(timezone.utc)
    start_date = now.astimezone(LONDON).date()
    # Better currently exposes today plus five further dates.
    end_date = start_date + timedelta(days=DAYS_AHEAD)
    venues = [venue for venue in load_registry(ROOT / "config/venues.yaml") if venue.availability_urls]
    selected = {provider: PROVIDERS[provider]} if provider else PROVIDERS
    sources = {
        host: source(request_pacer=RequestPacer(interval, request_limit))
        for host, source, interval, request_limit in selected.values()
    }
    venues_by_host = {}
    for venue in venues:
        source_host = urlparse(venue.availability_urls[0]).hostname
        if source_host not in {details[0] for details in PROVIDERS.values()}:
            raise ValueError(f"No availability source for host: {source_host}")
        if source_host in sources:
            venues_by_host.setdefault(source_host, []).append(venue)

    if plan:
        for name, (host, _, interval, request_limit) in selected.items():
            print(f"{name}: {len(venues_by_host.get(host, []))} venues, {interval}s pacing, request limit {request_limit}")
        return

    providers = {}
    failed_providers = []
    for source_host, provider_venues in venues_by_host.items():
        slots = []
        metadata = {}
        try:
            for venue in provider_venues:
                venue_slots = await sources[source_host].fetch_availability(venue, start_date, end_date)
                slots.extend(venue_slots)
                if source_host in {"better-admin.org.uk", "flow.onl"}:
                    patch = metadata_patch_from_slots(venue, venue_slots)
                    if patch and patch.values:
                        metadata[venue.id] = _metadata_json(patch)
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
            "metadata": metadata,
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
        "metadata": {venue_id: metadata for snapshot in snapshots for venue_id, metadata in snapshot["metadata"].items()},
        "providers": providers,
        "failed_providers": failed_providers,
    }
    _save(output, payload)
    print(f"Saved {len(payload['slots'])} slots to {output.relative_to(ROOT)}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all", action="store_true", help="refresh every configured provider")
    selection.add_argument("--provider", choices=PROVIDERS, help="refresh one provider")
    parser.add_argument("--plan", action="store_true", help="show the refresh scope without making requests")
    args = parser.parse_args(argv)
    asyncio.run(refresh_availability(provider=args.provider, plan=args.plan))


if __name__ == "__main__":
    main()
