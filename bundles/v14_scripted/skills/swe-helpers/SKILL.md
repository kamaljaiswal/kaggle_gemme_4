---
name: swe-helpers
description: Three deterministic helpers for fixing a GitHub issue in /workspace - locate the files to edit, apply a checked edit, run the checks. Use them instead of hand-written grep, edit and pytest commands.
---

# swe-helpers

Scripts (standard library only, run from anywhere, all paths relative to /workspace):

- `scripts/locate.py <words from the issue>`: ranks tracked `.py` files by the issue's identifiers and words, prints the top 5
  with their class/def outline and line spans. One call replaces several greps and reads.
- `scripts/patch.py <file> <start_line> <end_line>`: replaces lines start..end (inclusive, 1-based) with the text given on
  stdin; refuses if the file does not compile afterwards (restores the original) and prints the result with line numbers.
  Use through run_command with a quoted heredoc: `python3 <path>/patch.py pkg/mod.py 120 124 <<'EOF' ... EOF`.
- `scripts/check.py <test_file> [-k keyword]`: runs /tmp/repro.py if it exists, then that test file with pytest
  (timeout, -x, short traceback) and prints only the exit code, a summary line and the first failure.
