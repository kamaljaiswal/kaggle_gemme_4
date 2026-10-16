# Bundle registry

Each folder is a complete submission (zip it with `scripts/validate_bundle.py --zip`).
The bundle id is the first 12 hex digits of the deterministic zip's SHA-256.
Never edit a bundle after it has been scored; copy it to a new folder instead.

| Bundle | Parent | Bundle id | Change (one variable) | Local result | LB |
|---|---|---|---|---|---|
| `run02_baseline` | — | `807f4a38293a` | Budget-Aware v2 as published: single agent, 31B, temp 0.2, output 8192, thinking 4096 (thoughts kept), 28 calls / 8 min | 27.5% (65/236); overflow 30.5% | not submitted by us (author's SuperAgent: 0.18) |
| `v3_overflow_fix` | run02_baseline | `35ac39233068` | Context budget: output 8192→6144, thinking 4096→2048, `include_thoughts` true→false; graph tools removed from `agent.yaml` and the prompt line that banned them | — | — |

## Notes

- `include_thoughts: false` does **not** turn thinking off. Per HARNESS_README §2.4, a positive
  `thinking_budget` still enables reasoning on the current turn; `false` only strips the thoughts from
  the history. To turn thinking off, set `thinking_budget: 0` (a separate experiment).
- Removing the graph tools from `agent.yaml` also removes the harness's "Code Intelligence Tools"
  section from the task prompt (HARNESS_README §5.2), so the saving is larger than the tool schemas alone.
- Bundle ids above were computed with `validate_bundle.py` on 16 Oct 2026. Recompute after any edit.

## Candidates (not yet built)

- `v4_prompt_hygiene` (parent v3): scratch files in `/tmp`; `pytest -q --tb=short | tail -30`;
  grep the most distinctive part of backticked code and error strings from the issue.
- `v5_analyzer` (parent: best of v3/v4): read-only `code_analyzer` as `agent_tool`, short
  LOCATION / ROOT CAUSE / FIX PLAN report. Raise `max_tool_calls` if its calls share the budget.
- `v3_12b`: v3 with `gemma-4-12b-it-qat-w4a16-ct` (speed vs accuracy).
- `v3_nothink`: v3 with `thinking_budget: 0`.
