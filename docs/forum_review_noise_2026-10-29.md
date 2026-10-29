# Review: "Is 0.24 vs 0.22 real? A noise and luck check" (harshitsama) + Adam Johnson's reply, 29 Oct 2026

Source: forum post and notebook text pasted by the user (attachment fc12224f). Leaderboard snapshot fetched by the author on 28 Oct.

## Leaderboard shape (measured)

4,018 teams. Solved tasks of 58: 14 tasks (0.24) 6 teams; 13 (0.22) 48; 12 (0.21) 218; 10 (0.17) 1,260; 9 (0.15) 581;
8 (0.14) 397; 7 (0.12) 320; 6 (0.10) 264. No team at 11 (0.19): scores are counts out of 58, so some values cannot occur.
Our scores: 0.12, 0.15, 0.17, 0.13, 0.15 = 7, 9, 10, 8, 9 tasks. 0.17 is the most common score on the board.

## Noise

- harshitsama (simulation, assumptions stated): sd of one run 2.5-3 tasks; an equal config looks 2+ tasks better about a
  third of the time. The real top (14 tasks of 4,018 teams) is far below the coin-flip prediction for best-of-400 (17-21),
  so real noise is smaller: 3 tasks is an upper bound.
- Adam Johnson (measured, 200+ runs of one config): two same-config pairs landed 0 tasks apart ((0.17, 0.17), (0.18, 0.18)).
  Variance lives only in "flippy" tasks: of 39 task x config cells with 6+ draws, about 67% flippy, 23% never solved,
  10% always solved. Measured sd about 2 tasks per 58-task draw.
- Our four summary-on bundles scored 8, 9, 9, 10 tasks: consistent with equal agents under this noise.
- The forum's 0.24 for the x_lb024 files against our 0.17 is a 4-task gap: possible under this noise but in the tail.

## Ceiling

Adam Johnson: 35 of 38 multi-file reference fixes in the practice set have never been solved by any model or config.
About a quarter of tasks are structurally out of reach, which compresses the top.

## Budget lever is contested

- For: Ayush Thakur's sweep (25 vs 50 calls: 36 vs 50 of 129; 6 vs 15 min: 37 vs 54), on fast GPUs with a 60-min cap.
- Against: Adam Johnson's 154-run replay of "the cap raise" was null (net -1), and his budget-raise submission returned no
  score (scorer error; likely over time, not confirmed).
- So v12b_calls40 (calls 28 -> 40, time cap kept at 7 min) is a test, not an expected gain.

## Implications

1. Our agents are at the board median (9-10 tasks). 0.22 means 13 tasks, top 1.3% of teams on a single run.
2. Gains must come from flippy tasks: making the agent solve tasks it sometimes solves more consistently. Multi-file tasks
   are not worth chasing.
3. Final choice by robustness (never time out) and mean over repeats, as planned.
