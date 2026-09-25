# Metadata refresh coverage

Dataset: `config/venues.yaml`, 399 venues. `metadata_source_family` selects the intended metadata adapter. `booking_host` records where the user books; it is not treated as the provider. One venue may cite several kinds of metadata source.

The current pilot snapshot refreshes **8 of 399 venues**.

| Metadata source family | Venues | Share | Tennis | Squash | Padel | In pilot snapshot |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ClubSpark | 232 | 58.1% | 232 | 0 | 0 | 3 |
| Better | 30 | 7.5% | 16 | 14 | 0 | 2 |
| Park Sports | 3 | 0.8% | 3 | 0 | 0 | 0 |
| Generic HTML / unclassified | 134 | 33.6% | 102 | 12 | 20 | 3 |

## Metadata source types

These counts overlap because a venue can cite more than one source type. A cited source is not automatically supported by its parser.

| Detected source type | Venues citing it |
| --- | ---: |
| html | 255 |
| clubspark | 241 |
| pdf | 22 |
| everyoneactive | 4 |
| parksports | 3 |
| placesleisure | 3 |
| openactive | 2 |

## Generic HTML booking hosts

These are booking destinations for venues without a configured provider adapter. The hostname is an investigation group, not a provider classification.

| Booking host | Venues |
| --- | ---: |
| www.everyoneactive.com | 13 |
| playtomic.io | 8 |
| tennistowerhamlets.com | 7 |
| www.hackneytennis.co.uk | 7 |
| allstartennis.co.uk | 6 |
| tennissutton.com | 6 |
| www.sutton.gov.uk | 5 |
| active.lambeth.gov.uk | 4 |
| padelmates.se | 4 |
| www.kingston.gov.uk | 4 |
| www.placesleisure.org | 4 |
| camdenactive.camden.gov.uk | 3 |
| rockslane.co.uk | 3 |
| sportsandleisureroyalparks.bookings.flow.onl | 3 |
| www.matchi.se | 3 |
| Other hosts (1–2 venues each) | 54 |

## Integration order

1. **ClubSpark:** broaden fixture coverage before enabling all 232 configured venues.
2. **Better:** map the remaining venues to official OpenActive records where available; 2 of 30 are in the pilot.
3. **Park Sports:** add one HTML adapter for its 3 venues.
4. **Generic HTML:** investigate repeated hosts first, beginning with the largest groups among the remaining 134 venues. Keep a manual fallback for one-off sources.

This report measures metadata-refresh coverage only. Availability support is a separate capability.
