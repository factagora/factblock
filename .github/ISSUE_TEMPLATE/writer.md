---
name: New writer, reader or projection
about: Propose an adapter for a store or feed, or a projection to another standard
title: ""
labels: proposal
---

**What it reads or writes** (the store, feed or standard, with a link to its format)

**How its clocks map**: where `asserted_at`, `valid_from`/`valid_to` and `known_at` come from, and what is
self-reported (self-reported knowledge time becomes a declared backfill batch, SPEC.md section 6).

**What the projection loses**, if it is a projection.

**Will you maintain it?** A writer or reader maintained outside this repository is what takes the format to 1.0.0.
