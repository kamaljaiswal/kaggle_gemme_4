# Leaderboard submissions

One row per submission. The zip that was uploaded is stored under `submissions/<date>_<bundle>/`.
Fill in the score when it appears. Never edit a row after the score is in; add a new row instead.
Limit: 1 submission per day (resets about 24 h after use). Final submission 2 Dec 2026.

**Read public scores with care.** The public leaderboard scores 58 tasks, so one task is about 0.017, and identical files have
scored up to 6 tasks apart on repeated runs (source: dmitriigluzdov, *Gemma 4: Task Soundness, Serving and Evaluation*,
citing Dariush Afshar's leaderboard analysis). A difference of less than about 0.10 between two single submissions does not rank them.
Another team resubmitted the unchanged public 0.22 agent (flexonafft budget-aware v2 = our `run02_baseline`) three times and got
0.13, 0.13 and 0.17; their context-safety prompt variant got 0.18 once (notebook *Gemma 4 Developer Agent: The Road from 0.12
to 0.25+*, read 21 Oct 2026). So the base's typical score is about 0.13-0.18, and v3's 0.12 is at the low end of that range.

| # | Date (IST) | Bundle | Bundle id | Zip sha256 (first 12) | Local evidence | Score | Notes |
|---|---|---|---|---|---|---|---|
| 1 | 2026-10-19 | `v3_overflow_fix` | `35ac39233068` | `35ac39233068` | 4/12 (33%) on 12 random tasks; v4 tied on the same 12 | **ERROR** (Notebook Threw Exception) | Expected about 0.20 (range 0.15-0.25) if it had run. Likely cause: the uploaded zip was the hand-made one (6 KiB, files inside a `submission/` folder, so `agent.yaml` not at the root). Upload description: "v3_overflow_fix / bundle id 35ac39233068 / Gemma 4 31B, thinking 2048, 28 calls / 8 min / baseline". |
| 2 | 2026-10-20 | `v3_overflow_fix` | `35ac39233068` | `35ac39233068` | Same 4/12 on 19 and 20 Oct (3/11 without fastapi_14077, which passes unchanged) | **0.12** | Correct zip (`submissions/2026-10-19_v3_overflow_fix/submission.zip`, 3,636 bytes). Succeeded, so the hand-made zip layout caused #1's error. 0.12 = 7 of the 58 public-leaderboard tasks. Below the published single-agent references (0.18-0.22), but repeated public runs of identical files differ by up to 6 of 58 tasks (the unchanged Budget-Fit agent scored 8-11 of 58 over seven runs; a thinking-2048 variant scored 0.17 once), so this score alone does not show that v3's thinking cuts hurt. Local 12-task results (3/11) were higher than 7/58. |
| 3 | 2026-10-21 | `v9_edit_safety` | `4318096e0c00` | `4318096e0c00` | Not run locally | **ERROR: Notebook Timeout** (over the 12-hour limit; no score; counts toward the daily limit) | Config identical to the base (thinking 4096, 8 min/task). The prompt added slower verification: run the whole test file (up to 150 s per run), up to 3 verify calls, py_compile. The base alone is already near the limit (Budget-Fit 31B: 5.4 min/task on an A100; a 12B run at 8 min also timed out). Lesson: never submit a bundle that can be slower than one already scored without measuring its mean time locally first (must be about 282 s/task or less). |
| 4 | 2026-10-23 | `v9_edit_safety` | `4318096e0c00` | `4318096e0c00` | Not run locally | **0.15** (Succeeded) | Same zip as #3, resubmitted unchanged by the user: #3 was Notebook Timeout, this run finished and scored 0.15 (about 9 of 58). So the same files can time out on one run and finish on another: total run time varies between runs (serving speed, how many tasks run long), and v9 sits near the 12-hour edge. A finished run does not make v9 time-safe. Not to be resubmitted; x_lb024 / v11 have the lower time risk (no whole-file test runs). |
| 5 | 2026-10-24 | `x_lb024` | `6fdce4371950` | `6fdce4371950` | Not run locally by us; identical files reported 0.24 (14/58) on the forum | **0.17** (Succeeded) | Second sample of the forum 0.24 files: 0.17 = about 10 of 58. Finished within 12 h, as expected (7-minute cap, targeted tests). Two samples of the same files now span 0.17-0.24, consistent with the up-to-6-task rerun noise. Running mean of this agent family on the public board: v3 0.12, v9 0.15, x_lb024 0.17 (ours) and 0.13/0.13/0.17/0.22/0.24 (others) - about 0.17. Description used: "x_lb024 | id 6fdce4371950 | forum 0.24 bundle, second sample". |
| 6 | 2026-10-25 | `v11_lb024_fixes` | `1a7c5d9f2525` | `1a7c5d9f2525` | Not run locally; config identical to x_lb024 (finished 2 of 2) | **0.13** (Succeeded) | x_lb024 plus three prompt-only fixes: real pytest exit code (log to /tmp, echo $?), Python script after one failed edit_file and no `\n`/`\"` escapes, patch_size 0 with an untracked new file. Zip checked with check_submission_zip.py (OK, 4,265 bytes). Description: "v11_lb024_fixes | id 1a7c5d9f2525 | x_lb024 + exit-code, edit-fallback, untracked-file fixes". Result: 0.13 (about 7-8 of 58), finished within 12 h. x_lb024's files scored 0.17 (ours) and 0.24 (forum); a 2-4 task gap is inside rerun noise, so this neither shows the fixes hurt nor that they helped. |
| 7 | 2026-10-26 | `v12a_think2048` | `563b0d0da6df` | `563b0d0da6df` | Not run locally; x_lb024 with thinking 2048 (less thinking per turn, so no slower) | *pending* | One change against x_lb024 (0.17): thinking_budget 4096 -> 2048, summaries on. Basis: Ayush Thakur's 129-task sweep (2048/4096/6144 solved 50/48/48). Zip checked (OK). Description: "v12a_think2048 \| id 563b0d0da6df \| x_lb024 with thinking 2048". |

## Layout check (important)

The competition needs `agent.yaml` at the **root** of `submission.zip`.

- Correct zip (stored here): `submissions/2026-10-19_v3_overflow_fix/submission.zip`, 4 files, `agent.yaml` at root, sha256 `35ac3923306856f0affa19f6e9623baa443c38a00739088c6ecf96ba2774a29b` (equals the validated bundle id).
- A zip made by hand on 2026-10-19 (sha256 `cc0d71407cc080ec426fd027418614b9f2061545873a379550bd1697b53c6edc`) had the right file contents but put everything inside a `submission/` folder and added `__MACOSX/` files. Its `agent.yaml` is **not** at the root. Do not upload it. If it was uploaded, confirm the result on the Submissions page before counting it.
- Always build the zip with `python scripts/validate_bundle.py bundles/<name> --zip out/` and check `unzip -l` shows `agent.yaml` as a top-level entry.

## Submission #1: which file did the leaderboard get?

Record here after upload which of the two zips went in, and the Kaggle submission status/score:

- uploaded zip: almost certainly the hand-made one (Kaggle showed 6 KiB; the hand-made zip is 6,624 bytes, the correct one is 3,636 bytes), i.e. `agent.yaml` inside `submission/`, plus `__MACOSX/` files. Not confirmed.
- status/score: error, "Notebook Threw Exception", shown about 7 h after upload. No score. Errors count toward the daily limit.
- Next: resubmit as #2 with `submissions/2026-10-19_v3_overflow_fix/submission.zip` (3,636 bytes, `agent.yaml` at root) after the daily limit resets.
- Note: Kaggle's error text does not name the cause, and the local notebook ran the unzipped folder, not the zip. If #2 also errors, the zip layout is not the (only) cause; look for what the real harness does differently from our runner (for example, how it reads `eval_config.yaml`).
