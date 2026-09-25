# Backend status

The backend MVP is ready for frontend polish. Deployment and scheduled refreshes remain disabled.

## Completed

- Availability covers 244 of 399 venues: 216 tennis, 11 squash and 17 padel.
- Better, Royal Parks, LTA Play, Playtomic, MATCHi and Padel Mates normalize prices and durations from the same responses used for availability. These values remain live snapshot metadata rather than committed catalogue facts.
- Provider batches stop on their first error. Successful batches are saved atomically, failed batches retain their last published snapshot, and a total failure replaces nothing.
- The metadata CLI supports ClubSpark, Better OpenActive, Everyone Active and Places Leisure. The committed snapshot currently contains eight refreshed venues.
- Places Leisure metadata is verified for Tolworth, Balham and Tooting: all expose 45-minute squash sessions and stable weekly hours.

## Remaining squash availability

Squash availability covers 11 of 26 venues. The remaining 15 are intentionally deferred:

| Group | Venues | Current blocker |
| --- | ---: | --- |
| Better | 3 | Woolwich Waves, Kensington and Teddington still need verified booking-product mappings. |
| Everyone Active | 4 | Westway Portobello, Cheam, Porchester and Queen Mother require an account for availability. Public metadata remains supported. |
| Places Leisure | 3 | Tolworth, Balham and Tooting expose public timetable metadata, but the availability endpoint timed out in two paced probes. |
| Active Lambeth | 2 | Brixton and Flaxman use an authentication-protected Flow booking path. |
| Independent | 3 | Bloomsbury Fitness, Brunel and Mulberry Academy Shoreditch have no verified public availability API. |

Do not probe the account-protected providers again unless credentials or a documented public endpoint becomes available. Keep sending users to the official booking page for unsupported venues.

## Next product work

Polish the location cards and time grid, especially freshness, unsupported-provider messaging and direct booking links. After that, deploy the existing Netlify function once and validate one manual snapshot upload before enabling an hourly schedule.
