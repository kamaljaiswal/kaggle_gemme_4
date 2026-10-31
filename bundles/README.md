# Bundle registry

Each folder is a complete submission (zip it with `scripts/validate_bundle.py --zip`).
The bundle id is the first 12 hex digits of the deterministic zip's SHA-256.
Never edit a bundle after it has been scored; copy it to a new folder instead.

| Bundle | Parent | Bundle id | Change (one variable) | Local result | LB |
|---|---|---|---|---|---|
| `run02_baseline` | — | `807f4a38293a` | Budget-Aware v2 as published: single agent, 31B, temp 0.2, output 8192, thinking 4096 (thoughts kept), 28 calls / 8 min | 27.5% (65/236); overflow 30.5% | public notebook flexonafft/gemma-4-budget-aware-coding-agent-v2 (same files): **0.22**; earlier note: author's SuperAgent 0.18 |
| `v3_overflow_fix` | run02_baseline | `35ac39233068` | Context budget: output 8192→6144, thinking 4096→2048, `include_thoughts` true→false; graph tools removed from `agent.yaml` and the prompt line that banned them | 4/12 (33%) on 12 random tasks, median 262 s, no overflows | **0.12** (submission #2, 20 Oct 2026) |
| `v4_prompt_hygiene` | v3_overflow_fix | `021e2d9fbf11` | Prompt only (from smoke traces): one failed edit_file of any kind -> inline script; no escaped newlines/quotes in tool arguments; `git grep -n` named symbols instead of paging a big file; remove every use of a removed import; `py_compile` after each edit; scratch in /tmp and `git checkout` stray repo changes | 4/12 (33%), same 4 tasks as v3; median 228 s; more tool-cap/timeout failures (4 vs 2); faster on solved tasks (385 s vs 704 s) | not submitted |
| `v3_nothink` | v3_overflow_fix | `2e4521486c58` | Speed: `thinking_budget` 2048→0 (thinking off). Only change. | — | — |
| `v3_think1024` | v3_overflow_fix | `9e008131c7b1` | Speed: `thinking_budget` 2048→1024. Only change. | — | — |
| `v5_budget` | v4_prompt_hygiene | `bf42b8801880` | Budget (from the v3/v4 12-task run: 4-5 of 8 failures used all 28 calls; median 4.2 min of 8): `max_tool_calls` 28→40, `timeout_seconds` (per command) 240→90, `max_turns` 80→60; prompt numbers updated (verify to call 30); pytest exit code printed before the tail; /tmp scratch written via run_command (write_file refuses paths outside /workspace) | 20 Oct, same 12 tasks: 4/12 (3/11 without fastapi_14077), same tasks as v3; 3 timeouts; 0.86 h (v3 0.75 h). No gain from 40 calls | not submitted |
| `x_v26_workflow` | external | `56c9c16eefe0` | **Not ours, verbatim reference.** A participant's v26 workflow shared on 20 Oct 2026: SequentialAgent analyst → fixer → verifier, explorer as agent_tool with graph tools, thinking 2048 on three agents, 40 calls / 50 turns / 60 s per command / 8 min. Its nested `config_path: agents/explorer.yaml` only resolves from the bundle root (validator warns); a Kaggle run decides whether the harness loads it | 20 Oct, same 12 tasks: 5/12 (4/11), +rich_3470 over v3; median 389 s, 1.24 h for 12 → ~12.4 h for 120 (over the window); explorer agent_tool loaded (10 calls), so nested config_path resolves from the bundle root | not submitted |
| `x_timeout_probe` | external | `5d07fda7a2a0` | **Not a solver.** Harness probe shared on 20 Oct 2026: writes a marker file, runs a 75 s command against a 30 s command timeout, then idles until the 1.5 min task limit. Graph tools dropped and `thinking_budget: 0` added (neither matters to the probe). Expect 0 resolved; read its traces and ledger rows | 20 Oct: see Harness facts below | not submitted |
| `v6_workflow` | x_v26_workflow | `0b6adc7e3c4f` | Time only: `max_time_minutes` 8→6 (v26 projected ~12.4 h for 120 tasks). Only change | — | — |
| `v7_prompt_fixes` | run02_baseline | `d0810ece9a4c` | Prompt only (shared 21 Oct; model, sampling, tools and limits byte-identical to run02_baseline): protect pytest.ini/conftest.py and keep scratch in /tmp; change every parallel implementation (sync/async, Client/AsyncClient, backends, overloads, `__all__`); finish with `git status --short && git diff` (untracked files are in the graded patch, confirmed by x_timeout_probe); keep current behaviour for inputs the issue does not mention; verify with the issue's own example first, then the whole test file (`-k` only on timeout) | not run locally | submission #3 (planned) |
| `v8_combined` | v7_prompt_fixes | `45115874b157` | Prompt only; config byte-identical to run02_baseline (thinking 4096, thoughts kept, 8192 output, 28 calls, 8 min). Adds to v7: a CONTEXT SAFETY section (another team's variant, 0.18 once); `--tb=short --disable-warnings` on the whole-file test run; a line that a timed-out command returns no output; `submit_patch` patch_size 0 no longer read as "nothing edited" when the change is a new file (seen on Kaggle). See `docs/reassessment_2026-10-21.md` | not run locally | submission #3 (planned, replaces v7) |
| `v9_edit_safety` | v8_combined | `4318096e0c00` | Prompt only: after one failed edit_file of any kind, switch to a Python replacement script; no escaped newlines/quotes in tool arguments; `py_compile` every edited file in the first check. From our traces (malformed edit calls) and SWE-agent's syntax check. See `docs/research_2026-10-21.md` | not run locally | **Notebook Timeout** (submission #3, 21 Oct) |
| `v10_time_safe` | v9_edit_safety | `6b4180954a3d` | Time: verify with `-k` targeted tests again (`timeout 90`, at most 2 verify calls) instead of whole test files; task limit 8→7 min. Everything else as v9. Must be measured locally (mean seconds per task) before submitting | — | — |
| `x_lb024` | external (shared 22 Oct, reported public **0.24**) | `6fdce4371950` | v7 prompt without edit #5 (back to `-k` targeted tests, at most 2 verify calls, output piped to `tail -40`), task limit 8→7 min, `max_output_tokens` 8192→6144; thinking 4096 with thoughts kept, 28 calls, as the base. It finished inside 12 h, which supports the v9 timeout diagnosis (whole-file tests + 8 min were too slow). One score: 0.24 = 14 of 58 | not run locally | reported 0.24 (one run) |
| `v11_lb024_fixes` | x_lb024 | `1a7c5d9f2525` | Prompt only, config byte-identical to x_lb024. Three time-neutral fixes: pytest exit code printed before the log tail (`| tail` hid failures: 39 misleading runs in 11 tasks in the v26 author's traces); one failed edit_file of any kind → Python replacement script, no escaped quotes/newlines (our traces: 67→29 LLM turns on one task); `submit_patch` patch_size 0 no longer read as "nothing edited" for a new file (our probe). Measure time with x_lb024 before submitting | — | public 0.13 (25 Oct, one run) |
| `v12a_think2048` | x_lb024 | `563b0d0da6df` | One change: thinking_budget 4096 → 2048 (summaries stay on). Ayush Thakur's 129-task sweep: 2048 / 4096 / 6144 solved 50 / 48 / 48 (inside noise). Less thinking per turn, so no slower than x_lb024; leaves 4096 output tokens for the visible answer instead of 2048 (fewer cut-off edits). Zip staged in submissions/2026-10-26_v12a_think2048 | — | public 0.15 (26 Oct, one run) |
| `v12b_calls40` | v12a_think2048 | `94b71474fd02` | One change: max_tool_calls 28 → 40 (prompt call plan updated: verify 13-30, no exploration after 30). Time cap stays 7 min, so the worst case per task is unchanged; the mean rises because tasks that stopped at 28 calls now run on. Basis: Ayush Thakur's sweep, 25 vs 50 calls = 36 vs 50 of 129. Time risk: not measured locally. Zip staged in submissions/2026-10-29_v12b_calls40 | — | Notebook Timeout (29 Oct) |
| `x_skill_probe` | new | `` | **Not a solver.** Tests skill scripts: run_skill_script before and after load_skill on `skills/harness-probe/scripts/where.py` (prints cwd, Python, user, /workspace listing, git status, time), then looks for the script with run_command and runs it directly. Answers whether skill scripts can see the repo, how the agent calls them, and what they cost. Run on 2 tasks in the runner; read the traces | — | not submitted |

## Harness facts measured on Kaggle (20 Oct 2026, x_timeout_probe and x_v26_workflow)
- (Reported by smartmanoj, 29 Oct, CPU reproduction on the competition's vLLM 0.19.1 wheel) With the scorer's parser flags and non-streaming calls, a tool call written inside the thought before `<channel|>` is returned as reasoning and never runs; the harness then sends a continuation nudge. About 1% of 31B runs in their 6,485 dev runs. Fixed upstream in vLLM 0.24.0; only the hosts can change it. Our 20 Oct traces show 4 continuation nudges in about 48 task runs (3 in x_timeout_probe); the cause is not visible because those bundles hid thoughts.

- `timeout_seconds` is enforced per command: a 75 s command was killed at 30 s and the agent saw only
  `{"status": "error", "error_type": "TimeoutExceeded", "error_message": "Command timed out after 30 seconds"}` (no output).
- `max_time_minutes` is enforced per task with a few seconds of slack (1.5 min tasks took 93-99 s); the result is
  `Agent exceeded session timeout`, failure type `timeout`.
- Work done before a stop is graded: the marker file written in call 1 was in every graded patch, including on timeout.
- `get_status` reported `patch_size: 0` after a new (untracked) file was written, yet the graded patch contained it.
  Do not treat `patch_size: 0` as "nothing changed" when the change is a new file.
- `fastapi_14077` passed with only the probe's marker file as the patch: its tests pass on the unchanged code, so
  every bundle "solves" it. Report local results with and without it.
- A nested `agent_tool` `config_path` is resolved from the bundle root (x_v26_workflow's explorer was called 10 times).
- Per-task resolved sets are almost identical across bundles and runs: v3 solved the same 4 tasks on 19 and 20 Oct;
  of the 12 tasks, 4 are solved by every bundle and 6 by none, so only 2 tasks separate bundles on this set.

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
