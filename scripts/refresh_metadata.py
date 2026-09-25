"""Refresh the currently supported venue metadata into one JSON snapshot."""

import asyncio
import json
import sys
from dataclasses import asdict, replace
from datetime import datetime, time
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingestion.models import PriceRate, VenueMetadata, apply_metadata_patch
from ingestion.providers.clubspark import ClubSparkSource
from ingestion.providers.everyoneactive import EveryoneActiveMetadataSource
from ingestion.providers.openactive import OpenActiveSource
from ingestion.registry import load_registry
from ingestion.review import format_review, review_metadata, validate_metadata

OUTPUT = ROOT / "data/ingestion-metadata.json"
EVERYONE_ACTIVE = EveryoneActiveMetadataSource()
SOURCES = {
    "hammersmith-and-fulham-brook-green-tennis": ClubSparkSource(),
    "haringey-finsbury-park": ClubSparkSource(),
    "merton-cottenham-park": ClubSparkSource(),
    "hounslow-gunnersbury-park-sports-hub": (ClubSparkSource(), OpenActiveSource()),
    "squash-islington-finsbury": OpenActiveSource(),
    "squash-kensington-westway-portobello": EVERYONE_ACTIVE,
    "squash-sutton-cheam": EVERYONE_ACTIVE,
    "squash-westminster-porchester": EVERYONE_ACTIVE,
    "squash-westminster-queen-mother": EVERYONE_ACTIVE,
}


def _record(metadata):
    record = asdict(metadata)
    record["last_checked"] = metadata.last_checked.isoformat()
    record["release_time"] = metadata.release_time.isoformat() if metadata.release_time else None
    record["surface"] = list(metadata.surface)
    record["prices"] = [
        {
            "amount_gbp": str(rate.amount_gbp),
            "duration_minutes": rate.duration_minutes,
            "customer": rate.customer,
            "time_band": rate.time_band,
            "lights_included": rate.lights_included,
        }
        for rate in metadata.prices
    ]
    record["opening_hours"] = (
        {day: [[start.isoformat(), end.isoformat()] for start, end in periods] for day, periods in metadata.opening_hours.items()}
        if metadata.opening_hours
        else None
    )
    return record


def _metadata(record):
    hours = record.get("opening_hours")
    return VenueMetadata(
        venue_id=record["venue_id"],
        name=record["name"],
        booking_url=record["booking_url"],
        last_checked=datetime.fromisoformat(record["last_checked"]),
        source_url=record["source_url"],
        court_count=record.get("court_count"),
        floodlit_court_count=record.get("floodlit_court_count"),
        surface=tuple(record.get("surface", [])),
        floodlit=record.get("floodlit"),
        prices=tuple(
            PriceRate(
                Decimal(rate["amount_gbp"]),
                rate["duration_minutes"],
                rate.get("customer"),
                rate.get("time_band"),
                rate.get("lights_included"),
            )
            for rate in record.get("prices", [])
        ),
        booking_window_days=record.get("booking_window_days"),
        member_booking_window_days=record.get("member_booking_window_days"),
        release_time=time.fromisoformat(record["release_time"]) if record.get("release_time") else None,
        slot_duration_minutes=record.get("slot_duration_minutes"),
        opening_hours=(
            {day: tuple((time.fromisoformat(start), time.fromisoformat(end)) for start, end in periods) for day, periods in hours.items()}
            if hours is not None
            else None
        ),
        membership_required=record.get("membership_required"),
    )


def load_snapshot(path=OUTPUT):
    if not path.exists():
        return {}
    document = json.loads(path.read_text())
    if not isinstance(document, dict) or not isinstance(document.get("venues"), list):
        raise ValueError("Metadata snapshot must contain a venues list")
    result = {}
    for record in document["venues"]:
        metadata = _metadata(record)
        if metadata.venue_id in result:
            raise ValueError(f"Duplicate metadata venue ID: {metadata.venue_id}")
        issues = validate_metadata(metadata)
        if issues:
            raise ValueError(f"Invalid saved metadata for {metadata.venue_id}: {', '.join(issue.field for issue in issues)}")
        result[metadata.venue_id] = metadata
    return result


def _save_snapshot(path, metadata):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    document = {"venues": [_record(metadata[venue_id]) for venue_id in sorted(metadata)]}
    temporary.write_text(json.dumps(document, indent=2) + "\n")
    temporary.replace(path)


async def refresh_metadata(venues, sources, output=OUTPUT):
    existing = load_snapshot(output)
    refreshed = dict(existing)
    reports = []
    for venue in venues:
        venue_sources = sources.get(venue.id)
        if venue_sources is None:
            continue
        previous = existing.get(venue.id)
        candidate = previous
        for source in venue_sources if isinstance(venue_sources, tuple) else (venue_sources,):
            candidate = apply_metadata_patch(venue, await source.fetch_metadata(venue), candidate)
        invalid_fields = [issue.field for issue in validate_metadata(candidate)]
        if invalid_fields:
            raise ValueError(f"Invalid refreshed metadata for {venue.id}: {', '.join(invalid_fields)}")
        if previous is None:
            refreshed[venue.id] = candidate
            reports.append(f"{candidate.name}\nNew metadata record.")
            continue
        review = review_metadata(previous, candidate)
        errors = [issue for issue in review.issues if issue.level == "error"]
        if errors:
            raise ValueError(f"Invalid refreshed metadata for {venue.id}: {', '.join(issue.field for issue in errors)}")
        preserved = {change.field: change.before for change in review.changes if change.blocked}
        refreshed[venue.id] = replace(candidate, **preserved)
        reports.append(format_review(review))
    _save_snapshot(output, refreshed)
    return tuple(reports)


def main():
    venues = load_registry(ROOT / "config/venues.yaml")
    reports = asyncio.run(refresh_metadata(venues, SOURCES))
    print("\n\n".join(reports))
    print(f"\nSaved {len(reports)} refreshed venues to {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
