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

## First scorer-like run, 31 Oct 2026 (session 20261031_1753, 41 valid tasks, seed 1)

- Gold check: 41/41 reference patches pass. The sandbox works.
- `v12a_think2048`: 15/41 solved (37%; fastapi 5/21, rich 7/15, requests 3/4, httpx 0/1). Mean 315 s/task, p90 423 s,
  9 tasks at the 7-minute cap, 10 empty patches. 3.59 h for 41 tasks → about 10.5 h for 120 plus startup.
- `v14_scripted` (first version): 17/41 (fastapi 5, rich 8, requests 3, httpx 1). 13 solved by both, 2 only v12a, 4 only v14.
  Mean 310 s. The 2-task gap is inside noise, and the scripts were NOT working in this run (see below), so this is a
  prompt-difference comparison only.
- `x_skill_probe` findings: `run_skill_script` works without `load_skill`, returns stdout, and runs the script from a temp
  copy of the skill folder (cwd = that copy, not the repo). In the local subprocess sandbox `/workspace` does not exist;
  the repo is at `<sandbox>/workspace` and `run_command` runs there (the harness translates `/workspace` in shell
  commands, not inside Python). `run_command` can find and run the bundle's scripts directly. Shell variables do not
  survive between calls. In the first v14 run every script call therefore failed ("no matching files", "no such file",
  "test file not found", or `/scripts/locate.py` once `$SWE_HELPERS` was lost).
- Fixes in v14 (bundle id 21e4fbf90baa): scripts find the repo (env, cwd, /workspace, or a `workspace` dir up the tree);
  patch.py accepts `--from FILE`; the prompt's first call copies the scripts to /tmp/h and runs locate, and every later
  call uses /tmp/h/<script>. Not yet run.
