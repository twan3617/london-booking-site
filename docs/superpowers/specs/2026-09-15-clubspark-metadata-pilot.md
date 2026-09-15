# ClubSpark metadata pilot

The first metadata adapter reads public ClubSpark HTML for Brook Green Tennis, Finsbury Park and Cottenham Park. It emits provider-independent `VenueMetadata` and never writes to `data/venues.json` or `data/prices.json`. Availability and booking remain out of scope.

Each venue's direct ClubSpark booking URL is the fetched source. The parser extracts explicitly stated venue facts: standard court count, floodlit court count, surface, venue hours, public booking window and release clock. Conflicting booking windows or release clocks remain unknown, as do bare release hours without a clock or AM/PM. Published prices become structured rates only if their booking duration and customer type are clear; otherwise they remain unparsed. In particular, Finsbury Park's page quotes peak and off-peak amounts without a clear session duration, so this pilot does not create hourly rates from them.

The three public HTML pages fetched on 2026-09-15 are saved as test fixtures; a form token is redacted. An HTTP failure raises an error and does not produce a partial refresh. A local preview command prints the normalized record for one registry venue. Fixture tests cover each rule pattern, hidden text, conflicts and a page with no rule. Site JSON remains untouched until the diff and validation milestone.

The first adapter uses the Python standard library to fetch HTML and strip non-visible tags. Provider parsing stays in the ClubSpark module; a later availability source may use an entirely different JSON/feed path.
