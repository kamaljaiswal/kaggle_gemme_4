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
| 3 | planned 2026-10-21 | `v9_edit_safety` (or `v8_combined` if already uploaded) | `4318096e0c00` | `4318096e0c00` | Not run locally. Config identical to run02_baseline (public 0.22 once; 0.13, 0.13, 0.17 in another team's reruns) | — | Replaces the v7 plan: v7's five prompt edits plus context safety, concise test output and the patch_size fix. Expect about 0.13-0.18 like the base; one score is a sanity check, not a ranking. v9 = v8 + edit-failure and syntax-check rules. Zips: `submissions/2026-10-21_v9_edit_safety/submission.zip` (v8: `submissions/2026-10-21_v8_combined/`). |

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
