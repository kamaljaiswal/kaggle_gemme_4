# Review of the forum post behind the 0.24 bundle (x_lb024), 22 Oct 2026

The post: base flexonafft budget-aware v2 (public 0.22); built after the author's v4 hit Notebook Timeout / Notebook
Threw Exception; config changes "for safety margins only" (8→7 min, output 8192→6144); prompt = our v7 edits without
the whole-test-file run; public score 0.24. Its notebook builds files identical to `bundles/x_lb024` (sha256 ece1efc8…).

## Claim by claim

| Claim | Assessment |
|---|---|
| Base scored 0.22 | That was one run. Another team rescored the same files 0.13, 0.13, 0.17 |
| The author's v4 (whole-file tests) timed out | Matches our v9 timeout with the same prompt idea. Two independent timeouts: strong evidence that whole-file test runs at 8 min do not fit |
| 8 → 7 min gives slack | True on average, but not a guarantee: the worst case is still 120 × 7 = 14 h. Fitting depends on most tasks ending early |
| 8192 → 6144 because vLLM rejects prompt + max_output > 32,768 | Plausible and important: with 8192 the prompt can only reach 24,576 tokens; with 6144, 26,624. This is a likely mechanism for run_02's 30.5% context-overflow failures, and v3 (also 6144) had no overflows in 24 task runs |
| "Thinking budget 4096 still fits" | Only just. If a turn uses all 4096 thinking tokens, 2048 remain for the visible answer and the tool call. A long `edit_file` or heredoc script can then be cut off and arrive malformed. v3 (6144 output, 2048 thinking) keeps 4096 for the answer |
| Prompt changes | Sound. Untracked files do enter the graded patch (our probe), so the /tmp and `git status --short` rules fix a real leak |
| pytest piped through `tail -40` | A flaw: the command reports tail's exit status, so failed tests look like success (39 misleading runs in 11 tasks in the v26 author's traces). Fixed in v11 |
| Removing the whole-file run was the main timeout fix | Supported (our v9 and the author's v4), though the 7-minute cap also helps |
| 0.24 | One run, 14 of 58 tasks. Identical files vary by up to 6 tasks. It shows the bundle finishes within 12 h; it does not show it is better than the base |

## What it means for us

- Use `x_lb024` as the time-safe base. Resubmit it to get a second score.
- `v11_lb024_fixes` fixes the exit-code flaw and two harness issues without adding time.
- Open question worth one paired local test: thinking 4096 with only 2048 left for the answer (x_lb024) against thinking 2048 with 4096 left (v3-style). Check the traces for cut-off tool calls (failed calls with truncated arguments).
