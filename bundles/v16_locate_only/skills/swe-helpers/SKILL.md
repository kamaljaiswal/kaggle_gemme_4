---
name: swe-helpers
description: Ranks the source files for a GitHub issue in /workspace and prints their class/def outline with line numbers. Read-only.
---

# swe-helpers

- `scripts/install.py <words>` (skill script tool, first call): copies locate.py to /tmp/h and runs it.
- `scripts/locate.py <words>`: ranks tracked `.py` files by the issue's identifiers and words (BM25 plus exact-symbol hits;
  scripts/, examples/, docs/ and tests down-weighted) and prints the top 5 with their class/def outline and line spans.
  Read-only; changes nothing.
