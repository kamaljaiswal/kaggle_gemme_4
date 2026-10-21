# Leaderboard submissions

One row per submission. The zip that was uploaded is stored under `submissions/<date>_<bundle>/`.
Fill in the score when it appears. Never edit a row after the score is in; add a new row instead.
Limit: 1 submission per day (resets about 24 h after use). Final submission 2 Dec 2026.

| # | Date (IST) | Bundle | Bundle id | Zip sha256 (first 12) | Local evidence | Score | Notes |
|---|---|---|---|---|---|---|---|
| 1 | 2026-10-19 | `v3_overflow_fix` | `35ac39233068` | `35ac39233068` | 4/12 (33%) on 12 random tasks; v4 tied on the same 12 | **ERROR** (Notebook Threw Exception) | Expected about 0.20 (range 0.15-0.25) if it had run. Likely cause: the uploaded zip was the hand-made one (6 KiB, files inside a `submission/` folder, so `agent.yaml` not at the root). Upload description: "v3_overflow_fix / bundle id 35ac39233068 / Gemma 4 31B, thinking 2048, 28 calls / 8 min / baseline". |
| 2 | 2026-10-20 | `v3_overflow_fix` | `35ac39233068` | `35ac39233068` | Same 4/12 on 19 and 20 Oct (3/11 without fastapi_14077, which passes unchanged) | **0.12** | Correct zip (`submissions/2026-10-19_v3_overflow_fix/submission.zip`, 3,636 bytes). Succeeded, so the hand-made zip layout caused #1's error. Below the expected 0.15-0.25 and below the published single-agent references (0.18, and a public reproduction at 0.20). Local 12-task results overestimated the hidden score by about 2x. |
| 3 | planned | `run02_baseline` | `807f4a38293a` | `807f4a38293a` | run_02: 27.5% local (65/236), 30.5% context overflow | — | A/B against #2 on the hidden set. Differs from v3 only in: thinking 4096 (v3 2048), thoughts kept (v3 stripped), output 8192 (v3 6144), graph tools declared but banned in the prompt. Zip: `submissions/2026-10-21_run02_baseline/submission.zip`. If it scores clearly above 0.12, v3's thinking cuts hurt on hidden tasks. |

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
