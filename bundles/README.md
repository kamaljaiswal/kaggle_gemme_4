# Bundle registry

Each folder is a complete submission (zip it with `scripts/validate_bundle.py --zip`).
The bundle id is the first 12 hex digits of the deterministic zip's SHA-256.
Never edit a bundle after it has been scored; copy it to a new folder instead.

| Bundle | Parent | Bundle id | Change (one variable) | Local result | LB |
|---|---|---|---|---|---|
| `run02_baseline` | — | `807f4a38293a` | Budget-Aware v2 as published: single agent, 31B, temp 0.2, output 8192, thinking 4096 (thoughts kept), 28 calls / 8 min | 27.5% (65/236); overflow 30.5% | not submitted by us (author's SuperAgent: 0.18) |
| `v3_overflow_fix` | run02_baseline | `35ac39233068` | Context budget: output 8192→6144, thinking 4096→2048, `include_thoughts` true→false; graph tools removed from `agent.yaml` and the prompt line that banned them | — | — |
| `v4_prompt_hygiene` | v3_overflow_fix | `021e2d9fbf11` | Prompt only (from smoke traces): one failed edit_file of any kind -> inline script; no escaped newlines/quotes in tool arguments; `git grep -n` named symbols instead of paging a big file; remove every use of a removed import; `py_compile` after each edit; scratch in /tmp and `git checkout` stray repo changes | — | — |
| `v3_nothink` | v3_overflow_fix | `2e4521486c58` | Speed: `thinking_budget` 2048→0 (thinking off). Only change. | — | — |
| `v3_think1024` | v3_overflow_fix | `9e008131c7b1` | Speed: `thinking_budget` 2048→1024. Only change. | — | — |

## Notes

- `include_thoughts: false` does **not** turn thinking off. Per HARNESS_README §2.4, a positive
  `thinking_budget` still enables reasoning on the current turn; `false` only strips the thoughts from
  the history. To turn thinking off, set `thinking_budget: 0` (a separate experiment).
- Removing the graph tools from `agent.yaml` also removes the harness's "Code Intelligence Tools"
  section from the task prompt (HARNESS_README §5.2), so the saving is larger than the tool schemas alone.
- Bundle ids above were computed with `validate_bundle.py` on 16 Oct 2026. Recompute after any edit.

## Candidates (not yet built)

- `v4_prompt_hygiene`: built, see the table above. Not yet run.
- `v5_analyzer` (parent: best of v3/v4): read-only `code_analyzer` as `agent_tool`, short
  LOCATION / ROOT CAUSE / FIX PLAN report. Raise `max_tool_calls` if its calls share the budget.
- `v3_12b`: v3 with `gemma-4-12b-it-qat-w4a16-ct` (speed vs accuracy).
- `v3_nothink` and `v3_think1024`: built (see table). Compare against v3 on the same task ids, at least two runs each; judge by resolved count AND median seconds per task.

## Evidence behind v4 (smoke traces, 17 Oct 2026, v3 on fastapi_15661 / requests_7505 / rich_4070)

- requests_7505: 14 consecutive identical `edit_file` calls failed with "mandatory input parameters are not present" (malformed arguments); about half of the 28-call budget was lost. It stopped only after context compaction.
- fastapi_15661: `write_file` content arrived with escaped triple quotes and produced a SyntaxError; the agent also ran its own script, which changed `fastapi/__init__.py` and the release notes in the real tree.
- rich_4070: ~20 of 28 calls were sequential `read_file` chunks of a 2,600-line file although the issue named the symbols; in run 1 the agent removed an import but left its use (`getLogger`), and never ran an import check.
- Decode speed is about 32 tokens/s, so one 2,000-token thinking burst costs about 60 s of the 8-minute budget (2-3 such bursts per task). `v3_nothink` is the test for that.
