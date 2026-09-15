"""Classify existing booking links without guessing hidden booking backends."""

import json
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
VENUES = json.loads((ROOT / "data/venues.json").read_text())["venues"]


def host(url):
    return (urlparse(url or "").hostname or "(missing)").lower()


def classify(url):
    domain = host(url)
    if domain == "clubspark.lta.org.uk":
        return "ClubSpark", "direct_platform"
    if domain == "bookings.better.org.uk" or domain == "www.better.org.uk":
        return "Better", "operator_domain"
    if domain.endswith(".bookings.flow.onl"):
        return "Flow (Royal Parks)", "direct_platform"
    if domain in ("playtomic.com", "www.playtomic.com"):
        return "Playtomic", "direct_platform"
    if domain == "padelmates.se":
        return "Padel Mates", "direct_platform"
    operators = {
        "www.everyoneactive.com": "Everyone Active",
        "www.placesleisure.org": "Places Leisure",
        "parksports.co.uk": "Park Sports",
        "www.game4padel.com": "Game4Padel",
        "sportsandleisure.royalparks.org.uk": "Royal Parks Sports",
        "www.leisurecentre.com": "LeisureCentre.com",
        "padelsocial.club": "Padel Social Club",
    }
    if domain in operators:
        return operators[domain], "operator_domain"
    return domain, "site_domain_only"


inventory = []
for venue in VENUES:
    provider, basis = classify(venue.get("booking_url"))
    inventory.append({
        "venue_id": venue["id"],
        "name": venue["name"],
        "sport": venue["sport"],
        "provider_or_source": provider,
        "classification_basis": basis,
        "booking_url": venue.get("booking_url"),
        "metadata_sources": venue.get("sources", []),
    })
inventory.sort(key=lambda item: (item["provider_or_source"], item["venue_id"]))
assert len(inventory) == len({item["venue_id"] for item in inventory})
assert all(item["booking_url"] and item["metadata_sources"] for item in inventory)

groups = defaultdict(list)
source_hosts = defaultdict(set)
for item in inventory:
    groups[item["provider_or_source"]].append(item)
    for source in item["metadata_sources"]:
        source_hosts[host(source["url"])].add(item["venue_id"])

total = len(inventory)
counts = Counter(item["classification_basis"] for item in inventory)
top = sorted(groups.items(), key=lambda pair: (-len(pair[1]), pair[0]))
lines = [
    "# Booking provider and metadata-source inventory", "",
    f"Dataset: `data/venues.json`, {total} venues. Classification uses each booking URL's hostname; it does not prove the backend used by an operator or council site. The [per-venue inventory](provider-inventory.json) records every booking URL and all existing metadata sources.", "",
    f"**Direct platform links:** {counts['direct_platform']}. **Operator-domain links:** {counts['operator_domain']}. **Other site links with unverified backend:** {counts['site_domain_only']}.", "",
    "| Booking provider or site | Venues | Share | Tennis | Squash | Padel | Classification |",
    "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
]
for name, items in top:
    if len(items) < 3:
        continue
    sports = Counter(item["sport"] for item in items)
    lines.append(f"| {name} | {len(items)} | {len(items) / total:.1%} | {sports['tennis']} | {sports['squash']} | {sports['padel']} | {items[0]['classification_basis']} |")
small = [item for name, items in top if len(items) < 3 for item in items]
sports = Counter(item["sport"] for item in small)
lines += [
    f"| Other sites (each 1–2 venues) | {len(small)} | {len(small) / total:.1%} | {sports['tennis']} | {sports['squash']} | {sports['padel']} | See inventory |",
    "", "## Metadata source coverage", "",
    "Every venue has at least one source URL. The counts below are distinct venues citing a host, not pages or confirmed refreshable fields. Multiple hosts can support one venue.", "",
    "| Metadata-source host | Venues citing it |", "| --- | ---: |",
]
for domain, ids in sorted(source_hosts.items(), key=lambda pair: (-len(pair[1]), pair[0]))[:15]:
    lines.append(f"| {domain} | {len(ids)} |")
lines += [
    "", "## Integration order suggested by this dataset", "",
    f"1. **ClubSpark:** {len(groups['ClubSpark'])} direct booking links ({len(groups['ClubSpark']) / total:.1%}). Start with representative tennis pages and verify which fields remain in public HTML. A page parser for this family has the largest possible reach.",
    f"2. **Better:** {len(groups['Better'])} operator/booking links ({len(groups['Better']) / total:.1%}). Check official OpenActive data against the actual venue IDs before deciding which metadata fields it covers; use the linked public pages for missing rules.",
    "3. **Generic public-page extraction:** The remaining sites span many council, leisure and independent domains. Start with a field-specific HTML fallback that reports missing or changed values; add site adapters only for repeated layouts. Operator-domain links do not establish their booking backend.",
    "4. **Smaller repeated sources:** Everyone Active, Hackney Tennis, Tennis Tower Hamlets, Tennis Sutton, All Star Tennis and Newham Parks Tennis each cover several venues. Pilot them after the two largest groups.",
    "", "No direct booking links in this snapshot use a Fusion Lifestyle, Playfinder or Bookteq domain. This is a dataset count, not a statement that those providers lack London courts. The one `leisurecentre.com` record is Downham; [Lewisham Council identifies its operator as 1Life](https://lewisham.gov.uk/inmyarea/sport/leisure-centres), so it should not be counted as Fusion.",
    "", "This inventory is a starting classification for a curated registry. Review site-domain-only rows before assigning a platform adapter. It does not refresh metadata or inspect availability.", "",
]

(ROOT / "docs/provider-inventory.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n")
(ROOT / "docs/provider-coverage.md").write_text("\n".join(lines))
print(f"Saved {total} venue classifications across {len(groups)} booking provider/site groups.")
