# Metadata patches

## Goal

Make provider results partial so a source can update verified fields without implying that every omitted field was deleted.

## Steps

1. Add a typed `MetadataPatch` and a standard field enum.
2. Add one overlay function that applies a patch to existing metadata or a registry-derived base record.
3. Change ClubSpark and OpenActive parsers to emit only observed values.
4. Keep the current snapshot, validation, diff and atomic-write behavior.
5. Update fixture tests and verify a live repeat refresh for the five pilots.

Multi-source patch persistence and automatic acceptance remain deferred until a venue actually uses more than one automated source.
