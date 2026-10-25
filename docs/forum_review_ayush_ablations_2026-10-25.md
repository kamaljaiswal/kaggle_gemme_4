# Review: "Gemma 4 agent experiments: sampling, thinking, time limits, and tool ablations" (Ayush Thakur), 25 Oct 2026

Source: forum post and 9 comments pasted by the user (attachment c03c696e). Follow-up post referenced:
discussion/747857 (not read). The post is the largest controlled sweep seen so far: gemma-4-31b-it-qat-w4a16-ct on
32 B40 GPUs, the same 129 local tasks for every run, single runs, 50 calls and a 60-minute cap unless stated.

## How much noise to expect

The author's own repeat (E30 vs E34, same configuration) gave 55 and 48 of 129. So differences of about 7 tasks
(5 points) are noise. Only effects well beyond that count as evidence.

## Effects that are larger than the noise

| Change | Resolved / 129 | vs reference | Reading |
|---|---|---|---|
| Thinking disabled (E17) | 23 vs 48 | -25 | Thinking is essential |
| Thought summaries disabled, thinking 4096 (E18) | 35 vs 51 | -16 | Hiding summaries costs about 12 points |
| Thought summaries disabled, thinking 2048 (E19) | 34 vs 50 (E15) | -16 | Same |
| 6-minute active cap (E20) | 37 vs 54 (15 min) | -17 | Time cap matters |
| 10-minute active cap (E21) | 46 vs 54 | -8 | |
| 25 tool calls instead of 50 (E37) | 36 vs 50 (E35) | -14 | Call cap matters |

## Effects inside the noise (no evidence either way)

Temperature 0.0 / 0.2 / 0.4 / 1.0 (47 / 48 / 51 / 51), top-p 0.80 / 0.95 / 1.00 (48 / 48 / 48), thinking budget
2048 / 4096 / 6144 (50 / 48 / 48), analyzer sub-agent (+1), graph tools (50 vs 55 historical; 31 graph calls, none
returned the gold file; all 21 semantic searches empty), 15-minute vs 60-minute cap (54 vs 51).

## What it means for our bundles

1. **`include_thoughts: false` is the main suspect for v3's 0.12.** v3, v4, v5, v3_think1024 and v3_nothink all set it
   to false (checked in `bundles/*/configs/sampling.yaml`). v3 = E19's configuration, which scored about 0.67x the
   summaries-on runs locally. Applying that ratio to x_lb024's public 0.17 gives about 0.11, close to v3's 0.12.
   This is a post-hoc fit on one score, so it is a hypothesis, not proof. Mechanism (inference, not read in the harness):
   without summaries the model does not see its earlier reasoning on later turns. Our own 12-task local runs could not
   have detected a 10-point difference. `x_lb024`, `v11`, `v9`, `run02_baseline` and `x_v26` all use `true`.
2. **Thinking budget is not a lever** between 2048 and 6144 when summaries are on. With `x_lb024`'s output limit of
   6144, thinking 2048 leaves 4096 tokens for the visible answer (against 2048 at thinking 4096) and costs less time.
   Candidate: same settings, thinking 2048.
3. **The call cap is probably limiting us.** 28 calls sits near E37's 25 (-14 tasks). 21.6% of run_02 attempts hit
   28 calls. Raising `max_tool_calls` to about 40 while keeping `max_time_minutes: 7` leaves the worst-case time
   unchanged and lets those runs finish. The mean time per task rises a little (estimate, unmeasured).
4. **Time on Kaggle is the real constraint.** The author's calibration on Kaggle 4xL4: 900.8 s per million tokens
   (about 1,110 tok/s) and 8.68 s per model call with thinking on. Successful runs take 40-50 LLM and tool calls and
   300-350k tokens, about 5 minutes. He uses 5.5 minutes per task as the safe operating figure (120 x 5.5 = 11 h).
   A commenter reports a 4.5-minute cap took about 10 hours in scored runs, so each task adds roughly 0.5 minutes
   beyond the cap. A 7-minute cap cannot be guaranteed to fit 12 hours; it fits only if enough tasks end early.
   x_lb024 has finished twice (the forum author's run and ours), v9 at 8 minutes finished once and timed out once.
5. Our earlier conclusions that agree with this post: graph tools do not help, analyzer sub-agents do not clearly
   help, noise between identical runs is large.

## Ideas from the comments (untested)

- Ali Hassan: `search_similar_code` returns nothing for free text because embeddings are stored per node id.
  Seeding `get_code_neighbors` with exact symbol names put the edit site within 2 hops for 47.9% of tasks, against
  14.5% Hit@5 for TF-IDF keywords (his study of 117 tasks).
- Hitarth Jain: first identifier-grep hit is a gold file 30% of the time; grep + BM25 fused gives 61% in the top 5
  and 74% in the top 10; 35 of 128 issues contain no code identifier. Suggestion: list candidate files before reading.

## Caveats

- Different hardware and caps from the Kaggle run: his local sweep used 50 calls and 60 minutes. The direction of the
  large effects should transfer; the sizes may not.
- Single runs, one author, a local score on 129 tasks including about 15 unsound ones.
- The "thought summaries" setting is assumed to be `include_thoughts` in the sampling YAML (his reference
  configuration lists "thought summaries enabled" next to a 4096 thinking budget, the same fields).

## Candidate bundles (not built yet)

- `v12a`: `x_lb024` with `thinking_budget: 2048`. Time-safe by construction (less thinking per turn).
- `v12b`: `v12a` with `max_tool_calls: 40` and the prompt numbers updated (28 -> 40, edit by call 16, verify 17-30).
  Needs a measured total time before submitting (rule: 12 tasks x 10 in at most about 9.5 h).
