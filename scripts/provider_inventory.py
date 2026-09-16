"""Report configured metadata source families separately from booking hosts."""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingestion.registry import load_registry


def host(url):
    return (urlparse(url or "").hostname or "(missing)").lower()


def source_kind(url):
    domain = host(url)
    if domain == "clubspark.lta.org.uk":
        return "clubspark"
    if "/api/openactive/" in url:
        return "openactive"
    if domain == "parksports.co.uk":
        return "parksports"
    if urlparse(url).path.lower().endswith(".pdf"):
        return "pdf"
    return "html"


def build_inventory(venues):
    return sorted(({
        "venue_id": venue.id,
        "name": venue.name,
        "sport": venue.sport,
        "metadata_source_family": venue.provider,
        "booking_host": host(venue.booking_url),
        "booking_url": venue.booking_url,
        "metadata_sources": [
            {"url": url, "detected_kind": source_kind(url)} for url in venue.metadata_sources
        ],
    } for venue in venues), key=lambda item: (item["metadata_source_family"], item["venue_id"]))


def refreshed_ids():
    path = ROOT / "data/ingestion-metadata.json"
    if not path.exists():
        return set()
    return {item["venue_id"] for item in json.loads(path.read_text()).get("venues", [])}


def render_report(inventory, refreshed):
    groups = defaultdict(list)
    booking_hosts = defaultdict(list)
    source_kinds = defaultdict(set)
    for item in inventory:
        groups[item["metadata_source_family"]].append(item)
        if item["metadata_source_family"] == "html":
            booking_hosts[item["booking_host"]].append(item)
        for source in item["metadata_sources"]:
            source_kinds[source["detected_kind"]].add(item["venue_id"])

    total = len(inventory)
    names = {"clubspark": "ClubSpark", "better": "Better", "parksports": "Park Sports", "html": "Generic HTML / unclassified"}
    lines = [
        "# Metadata refresh coverage", "",
        f"Dataset: `config/venues.yaml`, {total} venues. `metadata_source_family` selects the intended metadata adapter. `booking_host` records where the user books; it is not treated as the provider. One venue may cite several kinds of metadata source.", "",
        f"The current pilot snapshot refreshes **{len(refreshed)} of {total} venues**.", "",
        "| Metadata source family | Venues | Share | Tennis | Squash | Padel | In pilot snapshot |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for family in ("clubspark", "better", "parksports", "html"):
        items = groups[family]
        sports = Counter(item["sport"] for item in items)
        pilot = sum(item["venue_id"] in refreshed for item in items)
        lines.append(f"| {names[family]} | {len(items)} | {len(items) / total:.1%} | {sports['tennis']} | {sports['squash']} | {sports['padel']} | {pilot} |")

    lines += [
        "", "## Metadata source types", "",
        "These counts overlap because a venue can cite more than one source type. A cited source is not automatically supported by its parser.", "",
        "| Detected source type | Venues citing it |", "| --- | ---: |",
    ]
    for kind, ids in sorted(source_kinds.items(), key=lambda pair: (-len(pair[1]), pair[0])):
        lines.append(f"| {kind} | {len(ids)} |")

    lines += [
        "", "## Generic HTML booking hosts", "",
        "These are booking destinations for venues without a configured provider adapter. The hostname is an investigation group, not a provider classification.", "",
        "| Booking host | Venues |", "| --- | ---: |",
    ]
    repeated = sorted(booking_hosts.items(), key=lambda pair: (-len(pair[1]), pair[0]))
    for domain, items in repeated:
        if len(items) >= 3:
            lines.append(f"| {domain} | {len(items)} |")
    other = sum(len(items) for _, items in repeated if len(items) < 3)
    lines.append(f"| Other hosts (1–2 venues each) | {other} |")

    lines += [
        "", "## Integration order", "",
        f"1. **ClubSpark:** broaden fixture coverage before enabling all {len(groups['clubspark'])} configured venues.",
        f"2. **Better:** map the remaining venues to official OpenActive records where available; {sum(item['venue_id'] in refreshed for item in groups['better'])} of {len(groups['better'])} are in the pilot.",
        f"3. **Park Sports:** add one HTML adapter for its {len(groups['parksports'])} venues.",
        f"4. **Generic HTML:** investigate repeated hosts first, beginning with the largest groups among the remaining {len(groups['html'])} venues. Keep a manual fallback for one-off sources.",
        "", "This report measures metadata-refresh coverage only. Availability support is a separate capability.", "",
    ]
    return "\n".join(lines)


def main():
    inventory = build_inventory(load_registry(ROOT / "config/venues.yaml"))
    assert len(inventory) == len({item["venue_id"] for item in inventory})
    assert all(item["booking_url"] and item["metadata_sources"] for item in inventory)
    refreshed = refreshed_ids()
    assert refreshed <= {item["venue_id"] for item in inventory}
    (ROOT / "docs/provider-inventory.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n")
    (ROOT / "docs/provider-coverage.md").write_text(render_report(inventory, refreshed))
    print(f"Saved {len(inventory)} venues across {len(set(item['metadata_source_family'] for item in inventory))} metadata source families.")


if __name__ == "__main__":
    main()
