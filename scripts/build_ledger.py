#!/usr/bin/env python3
"""Turn one or more swegemma results directories into a single ledger table.

One row per task attempt, with:
  run_id, bundle_id, instance_id, repo, outcome, failure_type, resolved,
  tool_calls, llm_calls, duration_s, patch_chars, files_touched,
  gold_files, loc_hit (did the patch touch a file the reference fix touched?)

failure_type separates BUDGET failures from SKILL failures:
  resolved            tests passed
  tests_failed        patch applied, hidden tests failed            (skill)
  no_patch            agent produced no source edit                 (skill)
  context_overflow    prompt + output exceeded the 32k window       (budget)
  timeout             session time ran out                          (budget)
  tool_cap            hit max_tool_calls without resolving          (budget, if no other cause)
  patch_apply_failed  verification could not apply the patch        (harness)
  harness_error       any other error                               (harness)

The exact field names in task_results.jsonl were not available when this was
written, so the script tries several candidate names per field and prints
which ones it used and which keys it ignored. Check that output on your first
run and pass --map field=key to correct any mapping.

Usage:
  python scripts/build_ledger.py results/run_02 --bundle-id 807f4a38293a \
      --tasks /kaggle/input/competitions/gemma-4-developer-agent/tasks.jsonl \
      --out ledger/run_02.csv
  # several runs at once (bundle ids in the same order):
  python scripts/build_ledger.py results/run_02 results/run_03 --bundle-id 807f4a38 35ac3923 ...
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

# Candidate source keys for each ledger field, most likely first.
CANDIDATES = {
    "instance_id": ["instance_id", "task_id", "id"],
    "repo": ["repo", "repository"],
    "resolved": ["resolved", "success", "passed"],
    "tool_calls": ["tool_calls", "num_tool_calls", "tool_calls_used"],
    "llm_calls": ["llm_calls", "total_llm_calls", "num_llm_calls", "turns", "model_calls"],
    "duration_s": ["duration_seconds", "duration_s", "duration", "elapsed_seconds"],
    "test_exit_code": ["test_exit_code", "exit_code"],
    "patch": ["agent_patch", "patch", "prediction"],
    "error": ["error", "agent_error", "error_message", "failure_reason", "status_message"],
    "test_output": ["test_output"],
}

BUDGET = {"context_overflow", "timeout", "tool_cap"}
SKILL = {"tests_failed", "no_patch"}
HARNESS = {"patch_apply_failed", "harness_error"}

OVERFLOW_PAT = re.compile(
    r"context.{0,20}(length|window|limit)|maximum context|max_model_len|too many tokens|"
    r"ContextWindow|prompt.{0,30}too long|exceeds?.{0,30}(context|tokens)", re.I)
TIMEOUT_PAT = re.compile(r"time ?out|timed out|TimeoutExceeded|time budget|deadline", re.I)
# Test-environment problems that no patch can fix (e.g. a pytest plugin missing in the offline sandbox).
# Only a flag, never a failure type: it marks tasks to look at, it does not remove them from the score.
ENV_PAT = re.compile(r"ERROR at setup of|recursive dependency involving fixture|fixture '[^']+' not found", re.I)
APPLY_PAT = re.compile(r"failed to apply|patch.{0,20}(apply|does not apply)", re.I)


def pick(rec: dict, field: str, mapping: dict, used: dict):
    keys = [mapping[field]] if field in mapping else CANDIDATES[field]
    for k in keys:
        if k in rec and rec[k] is not None:
            used.setdefault(field, Counter())[k] += 1
            return rec[k]
    return None


def files_in_patch(patch: str) -> list[str]:
    out = []
    for line in (patch or "").splitlines():
        if line.startswith("+++ "):
            p = line[4:].split("\t")[0].strip()
            if p != "/dev/null":
                out.append(p[2:] if p.startswith(("a/", "b/")) else p)
        elif line.startswith("diff --git "):
            m = re.match(r"diff --git a/(\S+) b/(\S+)", line)
            if m:
                out.append(m.group(2))
    return sorted(set(out))


def is_test_path(p: str) -> bool:
    p = p.lower()
    return bool(re.search(r"(^|/)(tests?|testing)/", p) or re.search(r"(^|/)test_[^/]*\.py$", p)
                or p.endswith("_test.py") or p.endswith("conftest.py"))


def classify(rec: dict, resolved, patch: str, err: str, tool_calls, tool_cap) -> str:
    if resolved in (True, 1, "true", "True"):
        return "resolved"
    blob = err + " " + json.dumps({k: v for k, v in rec.items() if k not in ("agent_patch", "patch")},
                                  default=str)[:20000]
    if OVERFLOW_PAT.search(blob):
        return "context_overflow"
    if APPLY_PAT.search(blob):
        return "patch_apply_failed"
    if TIMEOUT_PAT.search(err):
        return "timeout"
    if not (patch or "").strip() or (patch or "").strip() == "NO_PATCH":
        if tool_cap and tool_calls is not None and int(tool_calls) >= tool_cap:
            return "tool_cap"
        return "no_patch" if not err else "harness_error"
    if err:
        return "harness_error"
    return "tests_failed"


def load_gold(tasks_path: Path | None) -> dict:
    if not tasks_path:
        return {}
    gold = {}
    with open(tasks_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                t = json.loads(line)
                src = [p for p in files_in_patch(t.get("patch", "")) if not is_test_path(p)]
                gold[t["instance_id"]] = {"repo": t.get("repo"), "gold_files": src}
    return gold


def read_run(run_dir: Path, bundle_id: str, gold: dict, mapping: dict, tool_cap: int | None,
             results_file: str = "task_results.jsonl") -> pd.DataFrame:
    path = run_dir / results_file
    if not path.is_file() and (run_dir / "runner_results.jsonl").is_file():
        path = run_dir / "runner_results.jsonl"
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found")
    rows, used, all_keys = [], {}, Counter()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        all_keys.update(rec.keys())
        iid = pick(rec, "instance_id", mapping, used)
        patch = pick(rec, "patch", mapping, used)
        pfile = run_dir / "patches" / f"{iid}.patch"
        if not patch and pfile.is_file():
            patch = pfile.read_text(encoding="utf-8", errors="replace")
        err = str(pick(rec, "error", mapping, used) or "")
        resolved = pick(rec, "resolved", mapping, used)
        tool_calls = pick(rec, "tool_calls", mapping, used)
        touched = [p for p in files_in_patch(patch or "") if not is_test_path(p)]
        g = gold.get(iid, {})
        gold_files = g.get("gold_files", [])
        rows.append({
            "run_id": run_dir.name,
            "bundle_id": bundle_id,
            "instance_id": iid,
            "repo": pick(rec, "repo", mapping, used) or g.get("repo") or (iid.rsplit("_", 1)[0] if iid else None),
            "resolved": bool(resolved in (True, 1, "true", "True")),
            "failure_type": classify(rec, resolved, patch or "", err, tool_calls, tool_cap),
            "tool_calls": tool_calls,
            "llm_calls": pick(rec, "llm_calls", mapping, used),
            "duration_s": pick(rec, "duration_s", mapping, used),
            "test_exit_code": pick(rec, "test_exit_code", mapping, used),
            "env_suspect": bool(ENV_PAT.search(str(pick(rec, "test_output", mapping, used) or ""))),
            "patch_chars": len((patch or "").strip()) if (patch or "").strip() != "NO_PATCH" else 0,
            "files_touched": ";".join(touched),
            "gold_files": ";".join(gold_files),
            "loc_hit": (bool(set(touched) & set(gold_files)) if gold_files and touched else None),
            "error": err[:300],
        })
    print(f"[{run_dir.name}] {len(rows)} records")
    for field, c in used.items():
        print(f"  {field:15s} <- {', '.join(f'{k} ({n})' for k, n in c.items())}")
    unused = sorted(set(all_keys) - {k for c in used.values() for k in c})
    if unused:
        print(f"  keys not used: {', '.join(unused)}")
    missing = [f for f in CANDIDATES if f not in used and f not in ("repo",)]
    if missing:
        print(f"  fields not found (pass --map field=key if they exist under another name): {missing}")
    df = pd.DataFrame(rows)
    df["failure_group"] = df["failure_type"].map(
        lambda t: "resolved" if t == "resolved" else "budget" if t in BUDGET
        else "skill" if t in SKILL else "harness")
    return df


def summarize(df: pd.DataFrame) -> str:
    out = []
    for (run, bid), d in df.groupby(["run_id", "bundle_id"], sort=False):
        n = len(d)
        out.append(f"\nRUN {run}  bundle {bid}  tasks {n}  resolved {d['resolved'].sum()} "
                   f"({d['resolved'].mean():.1%})")
        vc = d["failure_type"].value_counts()
        for k, v in vc.items():
            out.append(f"  {k:20s} {v:4d}  {v / n:6.1%}")
        secs = pd.to_numeric(d["duration_s"], errors="coerce").dropna()
        if len(secs):
            out.append(f"  seconds per task: median {secs.median():.0f}, p90 {secs.quantile(0.9):.0f}, "
                       f"total {secs.sum() / 3600:.2f} h")
        grp = d["failure_group"].value_counts()
        out.append("  -- by group: " + ", ".join(f"{k} {v / n:.1%}" for k, v in grp.items()))
        finished = d[d["failure_group"].isin(["resolved", "skill"])]
        if len(finished):
            out.append(f"  resolved among tasks without budget/harness failure: "
                       f"{finished['resolved'].mean():.1%} ({finished['resolved'].sum()}/{len(finished)})")
        es = d[(d["failure_type"] == "tests_failed") & d["env_suspect"]]
        if len(es):
            out.append(f"  env_suspect: {len(es)} tests_failed task(s) show test-setup errors "
                       f"({', '.join(es['instance_id'].astype(str).head(5))}) - check before blaming the agent")
        lh = d["loc_hit"].dropna()
        if len(lh):
            out.append(f"  patch touched a gold file: {lh.mean():.1%} of {len(lh)} patched tasks")
            tf = d[(d["failure_type"] == "tests_failed")]["loc_hit"].dropna()
            if len(tf):
                out.append(f"    among tests_failed: right file {tf.mean():.1%} "
                           f"(wrong edit) vs wrong file {1 - tf.mean():.1%} (wrong place)")
        if "repo" in d and d["repo"].notna().any():
            pr = d.groupby("repo")["resolved"].agg(["sum", "count"])
            out.append("  by repo: " + ", ".join(f"{r} {s}/{c}" for r, (s, c) in pr.iterrows()))
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+", type=Path, help="results directories (each with task_results.jsonl)")
    ap.add_argument("--bundle-id", nargs="+", default=None, help="bundle id per run (from validate_bundle.py)")
    ap.add_argument("--tasks", type=Path, help="tasks.jsonl, for gold files and repo names")
    ap.add_argument("--tool-cap", type=int, default=None, help="max_tool_calls used in the run(s)")
    ap.add_argument("--map", nargs="*", default=[], metavar="FIELD=KEY", help="override field mapping")
    ap.add_argument("--results-file", default="task_results.jsonl",
                    help="file name inside each run dir (the Kaggle runner writes runner_results.jsonl)")
    ap.add_argument("--out", type=Path, default=Path("ledger/ledger.csv"))
    args = ap.parse_args()
    mapping = dict(m.split("=", 1) for m in args.map)
    bids = args.bundle_id or ["unknown"] * len(args.runs)
    if len(bids) != len(args.runs):
        print("--bundle-id needs one value per run", file=sys.stderr)
        return 2
    gold = load_gold(args.tasks)
    df = pd.concat([read_run(r, b, gold, mapping, args.tool_cap, args.results_file) for r, b in zip(args.runs, bids)],
                   ignore_index=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(summarize(df))
    print(f"\nwrote {args.out} ({len(df)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
