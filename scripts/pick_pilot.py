#!/usr/bin/env python3
"""Pick a fixed, stratified pilot set of task ids from a ledger.

Strata = past outcome (resolved / tests_failed / context_overflow by default)
crossed with repo, so a change shows up where you expect it to help or hurt.
The same seed always gives the same list; commit pilot_ids.txt and reuse it.

Usage:
  python scripts/pick_pilot.py ledger/run_02.csv --per-outcome 8 --out pilot/pilot_ids.txt
Then run the pilot with:  swegemma eval ... --task-ids $(cat pilot/pilot_ids.txt)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


def pick(df: pd.DataFrame, outcomes: list[str], per_outcome: int, seed: int) -> pd.DataFrame:
    chosen = []
    for oc in outcomes:
        pool = df[df["failure_type"] == oc]
        if pool.empty:
            print(f"  no tasks with outcome '{oc}'", file=sys.stderr)
            continue
        k = min(per_outcome, len(pool))
        # allocate across repos in proportion to their share of this outcome, at least 1 each
        share = pool["repo"].value_counts(normalize=True)
        alloc = (share * k).round().astype(int).clip(lower=1)
        while alloc.sum() > k:
            alloc[alloc.idxmax()] -= 1
        while alloc.sum() < k:
            alloc[share.idxmax()] += 1
        for repo, n in alloc.items():
            sub = pool[pool["repo"] == repo]
            chosen.append(sub.sample(n=min(n, len(sub)), random_state=seed))
    return pd.concat(chosen).drop_duplicates("instance_id") if chosen else df.iloc[0:0]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ledger", type=Path)
    ap.add_argument("--outcomes", nargs="+", default=["resolved", "tests_failed", "context_overflow"])
    ap.add_argument("--per-outcome", type=int, default=8)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=Path("pilot/pilot_ids.txt"))
    args = ap.parse_args()
    df = pd.read_csv(args.ledger)
    # one row per task: if the ledger has several runs, use the first
    df = df.drop_duplicates("instance_id", keep="first")
    sel = pick(df, args.outcomes, args.per_outcome, args.seed).sort_values(["failure_type", "repo", "instance_id"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(sel["instance_id"]) + "\n", encoding="utf-8")
    print(sel.groupby(["failure_type", "repo"]).size().to_string())
    print(f"\n{len(sel)} tasks -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
