# Next steps

Paused on 21 September 2026 after agreeing on a hybrid ingestion strategy.

## Agreed sequence

1. Add a small typed metadata-patch model: venue ID, source URL, checked time and only the fields actually observed.
2. Validate and diff patches against the curated catalogue; missing fields retain their existing values.
3. Convert the five existing ClubSpark/OpenActive pilots to patches.
4. Build a local Better availability MVP for one or two mapped venues:
   - canonical availability slots
   - generated local `data/availability.json`
   - date, start time and duration selection
   - distance ordering, map cards and official booking links
   - last-checked time
5. Expand metadata and availability provider by provider.

Do not wait for complete metadata automation before testing availability. Aim for roughly 80–90% automated metadata with a curated manual fallback for the long tail.

## ClubSpark finding

A read-only sample of one ClubSpark venue per borough fetched 27 of 27 pages, but a venue page alone exposed court count for 7 venues and booking windows for 6. Shared scheme pages and PDFs contain many of the missing facts.

Altash Gardens also demonstrated the contextual parsing risk: its page publishes 14 days for members and 7 days for pay-and-play. The current parser saw only 14 days. Do not enable all 232 ClubSpark venues until patches can combine multiple sources without overwriting curated values.

## Repository state

- Worktree: `/Users/wang_to/workspace/book-court/.worktrees/metadata-openactive-m4`
- Current branch: `metadata-clubspark-coverage`
- Provider/source separation: commit `1c1c9c0`
- Direct five-venue refresh: commit `3e5f247`
- No merge or push has been performed.

Never push from `main`; the user controls external data. Local branches, worktrees, commits and merges are allowed.
