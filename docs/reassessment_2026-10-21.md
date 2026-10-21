# Reassessment of every idea, 21 Oct 2026

Sources: our Kaggle runs (19 and 20 Oct, 12 tasks; `runs/`), our timeout probe, submissions #1-#2
(`submissions/LOG.md`), a participant's v26 workflow, and three public notebooks: *Task Soundness, Serving and
Evaluation* (dmitriigluzdov), *The Road from 0.12 to 0.25+* (reproduction log), and the v7 prompt-edit candidate.

## What limits every conclusion

- The public leaderboard scores **58 tasks**; one task is about 0.017.
- Identical files score **up to 6 tasks apart** across runs. The public "0.22" agent scored 0.13, 0.13 and 0.17 when
  another team resubmitted it; the Budget-Fit agent scored 8-11 of 58 over seven runs.
- So any single score between about 0.12 and 0.19 is consistent with this agent family. Only paired local runs on
  many valid tasks, or the average of several submissions, can rank two bundles.

## Each idea

| Idea | Evidence | Verdict |
|---|---|---|
| Base single agent (run02_baseline / flexonafft v2 / Budget-Fit family) | Most public runs; 0.13-0.18 typical | **Keep as the base** |
| Cut thinking 4096 to 2048, strip thoughts, output 6144 (our v3) | v3 0.12 once; a 2048 variant 0.17 once; our traces: thinking is 59-86% of output time | Unproven either way. Do not use as the base until a paired local test |
| Thinking 1024 | Another team's run pending | Wait for it |
| Keep `include_thoughts: true` | ADK leaves thought-only parts out of later requests, so it costs time, not context; the old serving bug was fixed by the organizers | **Keep the base's setting** |
| More tool calls (28 to 40, our v5) | Same 4/12 as v3, three more timeouts | **Drop** |
| Shorter per-task limit (6 min) | A six-minute plan solved 7 vs 12 of 44 on a confirmation repo (dmitriigluzdov) | **Drop**, except to make a slow bundle fit 12 h |
| 12-hour budget | About 282 s per task with startup and a 25% margin; v3 measured 225-250 s on 4xL4 | Measure the base's mean before the final choice |
| Multi-agent workflow (x_v26) | +1 task of 11, 65% more time (12.4 h projected) | **Drop for now** |
| Two-agent coder-analyzer | Scored 0.12, 0.10, 0.06 publicly; lost 16 vs 27 of 70 to a single coder | **Drop** |
| Reviewer voting | 13 vs 16 of 70 | **Drop** |
| Simple single coder (4 tools, 5 min, 20 calls) | 27 vs 16 of 70 against the coder-analyzer; tie on Rich with 43% less time | Promising for **time**; worth one paired local test against the base |
| v7 edit 1: protect pytest.ini/conftest.py, scratch in /tmp | Our probe: untracked files end up in the graded patch | **Keep** |
| v7 edit 2: change every parallel implementation | Reasoned, not measured; low risk | **Keep** |
| v7 edit 3: `git status --short && git diff` | Same probe finding | **Keep** |
| v7 edit 4: keep behaviour for inputs the issue does not mention | Grader runs whole test files | **Keep** |
| v7 edit 5: run the issue's example, then the whole test file | Better check, more time per verify | **Keep**, with concise pytest flags |
| Context-safety prompt section | 0.18 once (noise range); targets the 30.5% overflow seen in run_02 | **Keep** (prompt only, low risk) |
| `submit_patch` patch_size 0 with new files | Seen on Kaggle: get_status reported 0 although the graded patch had the new file | **Fix the prompt line** |
| A timed-out command returns no output | Seen on Kaggle | **Tell the agent**; wrap tests in `timeout 150` |
| Our v4 hygiene rules | Same 4/12 as v3; faster on solved tasks; failures moved to budget | Partly covered by v7/v8; not added separately |
| Graph tools declared but banned | No evidence either way | Leave as in the base (byte-identical config) |
| LoRA | Lower loss, fewer solved tasks (2 vs 4 of 16) | **Drop** before 2 Dec |
| 12B / E4B models | Far fewer solved, not faster | **Drop** |

## Result: `v8_combined`

Config byte-identical to the base. Prompt = base + every "Keep" row above. It is the best-supported candidate, not a
proven improvement: expect about 0.13-0.18 per run like the base.

## What would actually move the score

1. A paired local run on 40+ valid tasks (from the soundness dataset): `run02_baseline` vs `v8_combined`, then
   the base vs a thinking cut. Adopt a change only when it wins clearly and fits about 282 s per task.
2. For the final two selections, use bundles with the best paired local evidence, not the best single public score.
