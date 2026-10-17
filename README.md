# Gemma 4 Developer Agent: competition + paper track

Working repo for the Kaggle **Gemma 4 Developer Agent** competition (final submission 2 Dec 2026)
and its **paper track** (deadline 12 Nov 2026, 23:59 UTC = 13 Nov 05:29 IST).

See **[PLAN.md](PLAN.md)** for the plan, the calendar and the decision gates.

## Layout

```
bundles/                 one folder per agent version (exactly what goes into submission.zip)
  run02_baseline/        Budget-Aware v2, as run in run_02 (27.5% local, 236 attempts)
  v3_overflow_fix/       run02 + smaller output/thinking caps, thoughts stripped, graph tools removed
  README.md              registry: what changed in each bundle and what it scored
scripts/
  validate_bundle.py     checks a bundle against the harness rules, writes a deterministic zip + bundle id
  build_ledger.py        results dir(s) -> one ledger table, budget vs skill failure split
  pick_pilot.py          fixed, stratified pilot task list from a ledger
  trace_stats.py         per-task trace statistics: failed calls, first edit, verification, hidden-thinking share
analysis/
  localization_benchmark.py   TF-IDF vs grep vs embeddings vs graph: Hit@k for the gold file (CPU only)
notebooks/
  kaggle_runner.ipynb    Kaggle notebook: validate -> smoke/pilot/all run -> ledger -> submission.zip
  build_runner_notebook.py   source of the notebook (edit this, then regenerate)
paper/                   paper-track draft and figures
pilot/                   pilot_ids.txt (create it from the run_02 ledger, see below)
tests/                   end-to-end tests of the scripts on a synthetic dataset
```

## The loop

```
edit a bundle  ->  validate_bundle.py  ->  kaggle_runner (smoke, then pilot)  ->  build_ledger.py  ->  keep or discard
```

One change per bundle. Never overwrite a result. Every run records the bundle id (zip hash)
and the hash of `tasks.jsonl`.

## Quick start

```bash
pip install -r requirements.txt

# 1. check a bundle and build its zip
python scripts/validate_bundle.py bundles/v3_overflow_fix --zip out/

# 2. after a run, build the ledger (on Kaggle the runner notebook does this for you)
python scripts/build_ledger.py results/run_02 --bundle-id 807f4a38293a \
    --tasks /kaggle/input/competitions/gemma-4-developer-agent/tasks.jsonl --tool-cap 28 --out ledger/run_02.csv

# 2b. why tasks failed: failed tool calls, first edit, verification, thinking share (from the run's trace files)
python scripts/trace_stats.py results/run_X/harness/traces --out ledger/trace_stats_X.csv

# 3. make the fixed pilot list (8 resolved, 8 tests_failed, 8 overflow from run_02)
python scripts/pick_pilot.py ledger/run_02.csv --per-outcome 8 --out pilot/pilot_ids.txt

# 4. localization benchmark (CPU, competition data attached)
python analysis/localization_benchmark.py --data /kaggle/input/competitions/gemma-4-developer-agent --out results/localization

# tests (synthetic data, no GPU)
python tests/test_scripts.py
```

## Running on Kaggle

L4 sessions have internet off, so the notebook cannot `git clone`. Zip this repo, upload it as a
private Kaggle Dataset, and attach it with the competition data, the Gemma 4 model and the
`gemma-4-developer-agent-wheelhouse` dataset. Then open `notebooks/kaggle_runner.ipynb`, set
`BUNDLES` (one or several bundle folders) and `MODE` in the first cell, and run all. With several bundles and
`REPEATS = 2`, one GPU session compares them on the same tasks and prints a comparison table at the end. Details are in the notebook's first cell.

## What is verified and what is not

- The scripts pass end-to-end tests on a synthetic dataset that follows the documented data layout.
- They have **not** run on the real competition data from here (no access to it). On the first real run:
  - `build_ledger.py` prints which result fields it found; if any are missing, pass `--map field=key`.
  - `localization_benchmark.py` prints a note for any task whose gold file it cannot match to the snapshot.
- The runner notebook follows the official starter notebook's API calls, but has not been executed.
  Run it in `smoke` mode first.

## Credits

`bundles/run02_baseline` is the configuration from the public Kaggle notebook
"Gemma 4 | Budget-Aware Coding Agent v2", which adapts matterhorn3838's "Gemma 4 SuperAgent".
The runner's setup cells follow the official "Getting Started: Gemma 4 Developer Agent" notebook.
