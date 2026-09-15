# Booking provider and metadata-source inventory

Dataset: `data/venues.json`, 399 venues. Classification uses each booking URL's hostname; it does not prove the backend used by an operator or council site. The [per-venue inventory](provider-inventory.json) records every booking URL and all existing metadata sources.

**Direct platform links:** 239. **Operator-domain links:** 58. **Other site links with unverified backend:** 102.

| Booking provider or site | Venues | Share | Tennis | Squash | Padel | Classification |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| ClubSpark | 232 | 58.1% | 232 | 0 | 0 | direct_platform |
| Better | 30 | 7.5% | 16 | 14 | 0 | operator_domain |
| Everyone Active | 13 | 3.3% | 9 | 4 | 0 | operator_domain |
| tennistowerhamlets.com | 7 | 1.8% | 7 | 0 | 0 | site_domain_only |
| www.hackneytennis.co.uk | 7 | 1.8% | 7 | 0 | 0 | site_domain_only |
| allstartennis.co.uk | 6 | 1.5% | 6 | 0 | 0 | site_domain_only |
| tennissutton.com | 6 | 1.5% | 6 | 0 | 0 | site_domain_only |
| www.sutton.gov.uk | 5 | 1.3% | 5 | 0 | 0 | site_domain_only |
| Places Leisure | 4 | 1.0% | 1 | 3 | 0 | operator_domain |
| active.lambeth.gov.uk | 4 | 1.0% | 2 | 2 | 0 | site_domain_only |
| www.kingston.gov.uk | 4 | 1.0% | 4 | 0 | 0 | site_domain_only |
| Flow (Royal Parks) | 3 | 0.8% | 1 | 0 | 2 | direct_platform |
| Game4Padel | 3 | 0.8% | 0 | 0 | 3 | operator_domain |
| Park Sports | 3 | 0.8% | 3 | 0 | 0 | operator_domain |
| camdenactive.camden.gov.uk | 3 | 0.8% | 3 | 0 | 0 | site_domain_only |
| rockslane.co.uk | 3 | 0.8% | 3 | 0 | 0 | site_domain_only |
| Other sites (each 1–2 venues) | 66 | 16.5% | 48 | 3 | 15 | See inventory |

## Metadata source coverage

Every venue has at least one source URL. The counts below are distinct venues citing a host, not pages or confirmed refreshable fields. Multiple hosts can support one venue.

| Metadata-source host | Venues citing it |
| --- | ---: |
| clubspark.lta.org.uk | 241 |
| www.better.org.uk | 32 |
| www.barnet.gov.uk | 22 |
| www.merton.gov.uk | 15 |
| lewisham.gov.uk | 11 |
| www.sutton.gov.uk | 11 |
| pre.hillingdon.gov.uk | 10 |
| newhamparkstennis.org.uk | 9 |
| www.brent.gov.uk | 9 |
| www.ealing.gov.uk | 9 |
| www.everyoneactive.com | 9 |
| www.kingston.gov.uk | 9 |
| www.twistfizz.co.uk | 9 |
| tennistowerhamlets.com | 7 |
| www.bexley.gov.uk | 7 |

## Integration order suggested by this dataset

1. **ClubSpark:** 232 direct booking links (58.1%). Start with representative tennis pages and verify which fields remain in public HTML. A page parser for this family has the largest possible reach.
2. **Better:** 30 operator/booking links (7.5%). Check official OpenActive data against the actual venue IDs before deciding which metadata fields it covers; use the linked public pages for missing rules.
3. **Generic public-page extraction:** The remaining sites span many council, leisure and independent domains. Start with a field-specific HTML fallback that reports missing or changed values; add site adapters only for repeated layouts. Operator-domain links do not establish their booking backend.
4. **Smaller repeated sources:** Everyone Active, Hackney Tennis, Tennis Tower Hamlets, Tennis Sutton, All Star Tennis and Newham Parks Tennis each cover several venues. Pilot them after the two largest groups.

No direct booking links in this snapshot use a Fusion Lifestyle, Playfinder or Bookteq domain. This is a dataset count, not a statement that those providers lack London courts. The one `leisurecentre.com` record is Downham; [Lewisham Council identifies its operator as 1Life](https://lewisham.gov.uk/inmyarea/sport/leisure-centres), so it should not be counted as Fusion.

This inventory is a starting classification for a curated registry. Review site-domain-only rows before assigning a platform adapter. It does not refresh metadata or inspect availability.
