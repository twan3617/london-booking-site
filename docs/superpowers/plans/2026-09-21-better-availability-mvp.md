# Better availability MVP

1. Add a provider-independent availability slot model and one optional availability URL to the venue registry.
2. Parse Better's date-scoped booking JSON into canonical slots with fixture tests.
3. Add a plain Python refresh script that writes seven days to `data/availability.json` atomically.
4. Add start time, duration and available-only controls to the existing page; reuse its distance sorting, maps and cards.
5. Run a live Gunnersbury refresh and the Python and frontend test suites.

Out of scope: alerts, automatic booking, scheduling, full RPDE harvesting and additional providers.
