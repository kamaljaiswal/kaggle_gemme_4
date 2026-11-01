# Offline benchmark for locate.py (no GPU)

`prep.py` builds the 41 tasks of the 31 Oct scorer-like run: issue text (from the traces), gold files (from the ledger) and
the base commit (parent of the PR's commit, found by `git log --grep '#<PR>'` in full clones of the four repos).
`evalloc.py <locate.py>` checks out each base commit as a git worktree, runs locate on the issue text and reports how often a
gold file is in the top 1 / 3 / 5.

| locate version | top-1 | top-3 | top-5 |
|---|---|---|---|
| v14 first version (plain BM25 + symbol bonus) | 12/41 | 19/41 | 23/41 |
| + down-weight scripts/benchmarks/examples/tools/docs, boost the package | 15/41 | 24/41 | 28/41 |
| + strip PR-template boilerplate, HTML comments and URLs; BM25 b 0.75 -> 0.5; `__main__.py` down-weighted (v15) | 16/41 | 30/41 | 36/41 |
| v15 given only the first 250 characters of the issue | 16/41 | 27/41 | 36/41 |

For comparison: the agent's own edits touched a gold file in 27 of the 31 tasks where v12a edited anything; 10 tasks had no
edit at all. Caveat: tuned on these 41 tasks; the changes are generic (no repo or task names), but expect somewhat lower
numbers on unseen tasks.
