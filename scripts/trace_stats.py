#!/usr/bin/env python3
"""Per-task statistics from ATIF trace files (harness/traces/trace_<id>.json).

Why: the ledger says *what* happened (resolved, overflow, ...). The traces say *why*:
how many tool calls failed, when the first edit happened, whether the agent ever
verified anything, and how much of the output budget went on hidden thinking.

Columns:
  calls            tool calls in the trace (failed calls included)
  failed_calls     calls whose result was an error (some are not charged to the 28-call budget)
  first_edit_call  index of the first edit_file/write_file call (empty if none)
  verify_calls     run_command calls that ran pytest / unittest / py_compile / python -c / a script
  read_calls       read_file calls
  search_calls     other run_command calls
  completion_tok   total completion tokens (thinking + visible)
  hidden_tok       completion tokens minus an estimate of the visible tool-call text
  hidden_share     hidden_tok / completion_tok  (estimate; visible text is approximated from its length)
  burst_calls      calls with more than 1,000 completion tokens
  max_prompt_tok   largest prompt sent (the 32,768-token window is the limit)
  compactions      times the prompt shrank by more than 30% between calls
  wall_s           elapsed seconds at the last call
Wall time is almost exactly completion_tok / ~32 (decode speed measured on 4xL4, 31B w4a16).

Usage:
  python scripts/trace_stats.py results/<run>/harness/traces --out ledger/trace_stats.csv
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

VERIFY = re.compile(r"pytest|unittest|py_compile|python3? -c|python3? \S+\.py")


def _kind(tc: dict) -> str:
    name = tc.get("function_name", "")
    if name == "run_command":
        cmd = (tc.get("arguments") or {}).get("command", "")
        return "verify" if VERIFY.search(cmd) else "search"
    return {"read_file": "read", "edit_file": "edit", "write_file": "edit"}.get(name, name)


def _failed(obs: str) -> bool:
    head = (obs or "")[:80]
    return '"status": "error"' in (obs or "")[:400] or head.startswith('{"error"') or "Invoking" in head


def trace_row(path: Path) -> dict:
    d = json.loads(path.read_text(encoding="utf-8"))
    calls, comp, vis, bursts, prompts, last_t = [], 0, 0.0, 0, [], 0.0
    for st in d.get("steps", []):
        if st.get("source") != "agent" or not st.get("metrics"):
            continue
        c = st["metrics"].get("completion_tokens") or 0
        comp += c
        bursts += c > 1000
        prompts.append(st["metrics"].get("prompt_tokens") or 0)
        v = len(str(st.get("message") or "")) / 3.5
        obs = (st.get("observation") or {}).get("content", "")
        for tc in st.get("tool_calls", []) or []:
            v += len(json.dumps(tc.get("arguments", {}))) / 3.2 + 8
            last_t = max(last_t, (tc.get("extra") or {}).get("elapsed_s") or 0)
            calls.append((_kind(tc), _failed(obs)))
        vis += min(v, c)
    kinds = [k for k, _ in calls]
    first_edit = next((i + 1 for i, k in enumerate(kinds) if k == "edit"), None)
    compactions = sum(1 for a, b in zip(prompts, prompts[1:]) if b < a * 0.7)
    return {
        "instance_id": path.stem.replace("trace_", "", 1),
        "calls": len(calls), "failed_calls": sum(f for _, f in calls),
        "first_edit_call": first_edit, "verify_calls": kinds.count("verify"),
        "read_calls": kinds.count("read"), "search_calls": kinds.count("search"),
        "completion_tok": comp, "hidden_tok": round(comp - vis),
        "hidden_share": round((comp - vis) / comp, 2) if comp else None,
        "burst_calls": bursts, "max_prompt_tok": max(prompts, default=0),
        "compactions": compactions, "wall_s": round(last_t),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("traces", type=Path, help="directory with trace_<id>.json files")
    ap.add_argument("--out", type=Path, default=Path("ledger/trace_stats.csv"))
    a = ap.parse_args()
    files = sorted(a.traces.glob("trace_*.json"))
    if not files:
        print(f"no trace_*.json in {a.traces}", file=sys.stderr)
        return 2
    df = pd.DataFrame([trace_row(f) for f in files])
    a.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(a.out, index=False)
    print(df.to_string(index=False))
    print(f"\nmedian: calls {df['calls'].median():.0f}, failed {df['failed_calls'].median():.0f}, "
          f"first edit at call {df['first_edit_call'].median()}, hidden share {df['hidden_share'].median():.0%}, "
          f"wall {df['wall_s'].median():.0f}s; never verified: {(df['verify_calls'] == 0).mean():.0%} of tasks")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
