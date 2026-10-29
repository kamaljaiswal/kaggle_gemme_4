# Our local evaluation was graded in the wrong environment (29 Oct 2026)

Source: forum post by Zbigniew Kirchner, pasted by the user. He ran every reference (gold) patch through the official
swegemma grader. In a plain Kaggle notebook only 52 of 129 pass; in a scorer-like sandbox built from the published
Dockerfile.sandbox (clean venv, pytest, competition wheels, missing test packages, period-correct versions such as Pygments
for 7 rich tasks) 127 of 129 pass. The other 2 have contradictory skip conditions.

| Repo | Plain notebook | Scorer-like |
|---|---|---|
| fastapi | 10 / 67 | 66 / 67 |
| rich | 39 / 48 | 47 / 48 |
| requests | 3 / 13 | 13 / 13 |
| httpx | 0 / 1 | 1 / 1 |

Resources (Kaggle): notebook "Gemma 4 Agent: Do Gold Patches Pass Locally?" (zbigniewkirchner), datasets
`zbigniewkirchner/gemma-4-agent-local-eval-wheels` and `zbigniewkirchner/gemma-4-agent-local-eval-pythons`
(Apache 2.0 for his files; wheels from PyPI, Pythons from python-build-standalone 20261013), and gold_patch_check.csv.

## What this means for us

- Our runner (`notebooks/build_runner_notebook.py`) calls the Evaluator with `sandbox='subprocess'` in a plain notebook,
  the setup where 52 of 129 gold patches pass. So every local result we have (run_02's 27.5%, the 12-task comparisons of
  19-20 Oct) was graded in an environment where most fastapi and requests tasks could not pass even with the correct fix.
- Our ledgers agree: of 19 tests_failed rows, 5 ended with pytest exit code 2 (collection or import error). Exit code 1
  failures can also come from the environment (wrong library versions).
- Our 12-task set has 7 fastapi and 2 requests tasks. That likely explains "four tasks solved by every bundle, six by none":
  many of the six may have been unsolvable locally. The 12-task comparisons had even less power than we thought.
- Paired comparisons in one environment are still fair between bundles, but tasks that can never pass add only noise.
- gold_patch_check.csv also gives the valid-task list (127 of 129), replacing the need for the soundness dataset.

## Fix

Rebuild the runner's sandbox the scorer-like way (attach the two datasets, follow his notebook), then rerun a calibration:
gold patches should pass on about 127 tasks before any agent comparison.
