# Plan

Written 16 Oct 2026. Update the status column and the results table as runs come in.

## Where we stand (honest version)

- **run_02 is the public Budget-Aware v2 agent, unchanged.** 27.5% resolved locally (65 of 236 attempts).
  That is the public starting line, not an edge. The same agent family scored 0.18 on the hidden set,
  so expect roughly 0.18–0.22 there. The public leaderboard top is 0.24, and the top four are within
  one or two tasks of each other (noise on ~60 public tasks).
- **One measured, fixable problem:** 30.5% of attempts end in **context overflow**. That bucket is as
  large as wrong fixes (31.8%).
- **Everything else is untested ideas** (decision cards, analyzer, workflow agents, skills, routing).
  None goes in without an A/B on the same tasks.

## run_02 failure breakdown (236 attempts)

| Outcome | Share | Group |
|---|---|---|
| resolved | 27.5% | |
| tests failed | 31.8% | skill |
| context overflow | 30.5% | budget |
| other harness error | 5.5% | harness |
| no patch | 4.2% | skill |
| session timeout | 0.4% | budget |

Timing: p50 3.1 min/task, 12.65 h for 236 tasks (~6.4 h for ~120 hidden tasks). 21.6% hit the 28-call cap.

## Constraints (from HARNESS_README.md and the competition page)

- One base model for all agents (31B / 12B / E4B / E2B, 4-bit). Declarative YAML only, < 3 GiB.
- 32,768-token context for everything. Tool output capped at 5,000 chars; `read_file` at 150 lines.
- Harness compaction fixed (threshold 14,336 tokens, interval 15, keep 5). Not configurable.
- 12 h total for ~120 hidden tasks; per-task budgets come from our `eval_config.yaml`.
- Hidden set comes from **private repos**. Public data: 129 tasks, 4 repos, Python only, no hints.
- Kaggle L4×4 quota burns at 2×: a full run is roughly a week of quota.

## Data facts that shape the approach

- Median issue 58 words (rich: 13). 59% of issues name neither the edited function nor its module.
  21% are pull-request templates. 1% contain a traceback.
- 71% of fixes touch one file; 51% change ≤ 12 lines. **Finding the place is the hard part.**
- Plain TF-IDF puts the gold file in the top 5 for only ~48% of tasks (fastapi ~39%, rich ~47%).
- fastapi is 52% of tasks.

## Priorities (ranked by evidence per hour)

| # | Change | Confidence | Expected | Status |
|---|---|---|---|---|
| 1 | **v3: overflow fix** — output 6144, thinking 2048, `include_thoughts: false`, graph tools removed | High | +3 to +8 pts | bundle ready |
| 2 | **Read 15 traces** (5 pass / 5 tests_failed / 5 overflow); bucket: misunderstood / wrong place / wrong edit | High | decides #4 | todo |
| 3 | **v4: prompt hygiene** — scratch files in `/tmp`, `pytest -q --tb=short \| tail -30`, grep backticked literals | Medium | +1 to +3 | todo |
| 4 | **v5: analyzer sub-agent** (`agent_tool`, read-only, own context) — README's own advice | Medium | 0 to +5 | todo |
| 5 | **31B vs 12B** on the pilot; spend saved time on more calls or a retry | Medium | 0 to +4 | todo |
| 6 | Best-of-2 with a reproduction check, if time per task allows | Medium | +2 to +5 | later |
| 7 | One LoRA round on our own passing traces (after 12 Nov) | Low–medium | 0 to +5 | later |

**Dropped before 2 Dec:** Sequential/Loop/Parallel workflow agents, multi-path routing, six intent
skills, Colab runs on other benchmarks, training on the 129 public tasks. Each costs a week we do not have
and none has evidence here.

## Calendar

| Dates | Agent (score) | Paper (evidence) |
|---|---|---|
| Oct 16–22 | v3 smoke → rerun the 72 overflow tasks → full set. Read traces. One leaderboard submission as calibration | Ledger for run_02. Localization benchmark on all 129 |
| Oct 23–29 | v4, then v5 (analyzer) on the pilot, paired. 31B vs 12B | Full-set runs of the best bundles; feature table |
| Oct 30–Nov 5 | Best bundle on the full 129, twice (measure our own variance) | Pre-registered analysis; figures |
| Nov 6–12 | Freeze the agent | Write, trim to 3,000 words, **submit by 12 Nov 23:59 UTC** |
| Nov 13–25 | Accept competition rules by **25 Nov**. Optional LoRA round with go/no-go on the pilot | |
| Nov 26–Dec 2 | Final submission **2 Dec** | |

## Decision gates

- **v3 does not cut overflow** → the cause is something else. Read one overflow error from `logs/`
  before changing anything else.
- **A change does not beat its parent on the paired pilot** (two runs each) → discard it.
- **Below 25% locally by end of week 2** → stop adding; back to budgets and traces.
- **Fewer than ~400 logged attempts by week 2** → shrink the paper's profile section; lean on the
  overflow finding and the localization benchmark.

## Experiment rules

1. One variable per bundle. New folder per bundle, never edit a scored bundle.
2. Same task list for A/B (the pilot), at least two runs each; compare per task, not just totals.
3. Every run stores bundle id, tasks-file hash, model, and per-task results (`kaggle_runner.ipynb` does this).
4. Report budget failures and skill failures separately.
5. The leaderboard is a check, not a target.

## Paper track

Strongest story with the data we have: **separating budget failures from skill failures changes what a
resolved rate means** (run_02: ~36% budget, ~36% skill), plus the **localization benchmark** (how often
cheap methods and the provided graph/embedding tools find the right file). The per-skill profile
(SkillManifest) is the second half, sized to however many attempts we log.

The current draft (`paper/project-description.md`) predates this plan and still leads with the
profile hypothesis. Rewrite the framing once the first ledgers and the benchmark are in.

## Open questions

- What exactly triggers the overflows (vLLM prompt-length rejection, compaction, output truncation)?
- Do sub-agent tool calls count against the shared 28-call budget?
- Do the graph and embedding tools help at all? (the benchmark answers this)
- Why 236 attempts for 129 tasks in run_02 (repeats or a different list)?
