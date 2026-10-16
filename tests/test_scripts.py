"""End-to-end tests for the scripts on a tiny synthetic competition dataset.

Run:  python -m pytest tests -q      (or: python tests/test_scripts.py)

The fixture mimics the documented data layout (tasks.jsonl, snapshots/<id>.tgz,
graphs/<id>.json node-link format, embeddings/<id>.npz) and the results layout
(task_results.jsonl, patches/<id>.patch). Field names in task_results.jsonl are
guesses; the real file may differ, which build_ledger.py reports at run time.
"""
from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable


def _tgz(path: Path, files: dict[str, str], prefix: str = "") -> None:
    with tarfile.open(path, "w:gz") as tar:
        for name, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(prefix + name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))


def _patch(path: str, old: str, new: str) -> str:
    return f"--- a/{path}\n+++ b/{path}\n@@ -1,1 +1,1 @@\n-{old}\n+{new}\n"


def make_data(root: Path) -> Path:
    data = root / "data"
    for d in ("snapshots", "graphs", "embeddings"):
        (data / d).mkdir(parents=True)
    rng = np.random.default_rng(0)
    tasks = []

    # task 1: issue names the function -> every method should find it
    files1 = {
        "pkg/pretty.py": "def render_params(sig):\n    if default == Parameter.empty:\n        return None\n",
        "pkg/console.py": "class Console:\n    def print(self, x):\n        pass\n",
        "pkg/utils.py": "def helper():\n    return 1\n",
        "tests/test_pretty.py": "def test_x():\n    assert True\n",
    }
    _tgz(data / "snapshots" / "demo_1.tgz", files1, prefix="demo_1/")
    nodes = ["pkg.pretty.render_params", "pkg.console.Console", "pkg.console.Console.print", "pkg.utils.helper"]
    graph = {"directed": True, "multigraph": True, "graph": {},
             "nodes": [{"id": f"demo/pkg;{n}", "name": n, "text": ""} for n in nodes],
             "edges": [{"source": "demo/pkg;pkg.console.Console.print", "target": "demo/pkg;pkg.pretty.render_params",
                        "type": "calls", "key": 0}]}
    (data / "graphs" / "demo_1.json").write_text(json.dumps(graph))
    np.savez(data / "embeddings" / "demo_1.npz",
             **{f"demo/pkg;{n}": rng.normal(size=256).astype(np.float32) for n in nodes})
    tasks.append({"instance_id": "demo_1", "repo": "demo/pkg", "base_commit": "0" * 40,
                  "problem_statement": "`render_params` breaks when a class overrides __eq__: "
                                       "`default == Parameter.empty` can be True.",
                  "hints_text": "", "created_at": "2026-01-01T00:00:00Z",
                  "patch": _patch("pkg/pretty.py", "    if default == Parameter.empty:",
                                  "    if default is Parameter.empty:"),
                  "test_patch": _patch("tests/test_pretty.py", "    assert True", "    assert 1")})

    # task 2: behaviour-only issue, pull-request template noise
    files2 = {
        "lib/client.py": "def send(request, timeout=None):\n    return request\n",
        "lib/models.py": "class Response:\n    status_code = 200\n",
        "lib/__init__.py": "",
    }
    _tgz(data / "snapshots" / "demo_2.tgz", files2)
    tasks.append({"instance_id": "demo_2", "repo": "demo/lib", "base_commit": "1" * 40,
                  "problem_statement": "## Checklist\n- [x] I've run black\n<!-- template -->\n"
                                       "Requests ignore the timeout when sending.",
                  "hints_text": "", "created_at": "2026-02-01T00:00:00Z",
                  "patch": _patch("lib/client.py", "    return request", "    return request.with_timeout(timeout)"),
                  "test_patch": ""})

    # task 3: fix creates a new file (gold not in snapshot) -> skipped, not crashed
    _tgz(data / "snapshots" / "demo_3.tgz", {"lib/a.py": "x = 1\n"})
    tasks.append({"instance_id": "demo_3", "repo": "demo/lib", "base_commit": "2" * 40,
                  "problem_statement": "Add a new module.", "hints_text": "",
                  "created_at": "2026-03-01T00:00:00Z",
                  "patch": "--- /dev/null\n+++ b/lib/new.py\n@@ -0,0 +1,1 @@\n+y = 2\n", "test_patch": ""})

    (data / "tasks.jsonl").write_text("\n".join(json.dumps(t) for t in tasks) + "\n")
    return data


def make_results(root: Path, data: Path) -> Path:
    run = root / "results" / "run_test"
    (run / "patches").mkdir(parents=True)
    tasks = {json.loads(l)["instance_id"]: json.loads(l) for l in (data / "tasks.jsonl").read_text().splitlines()}
    recs = [
        {"instance_id": "demo_1", "resolved": True, "tool_calls": 12, "duration_seconds": 150.0,
         "agent_patch": tasks["demo_1"]["patch"]},
        {"instance_id": "demo_2", "resolved": False, "tool_calls": 28, "duration_seconds": 300.0,
         "agent_patch": _patch("lib/models.py", "    status_code = 200", "    status_code = 201"),
         "test_exit_code": 1},
        {"instance_id": "demo_3", "resolved": False, "tool_calls": 20, "duration_seconds": 200.0,
         "agent_patch": "", "error": "BadRequestError: This model's maximum context length is 32768 tokens"},
    ]
    (run / "task_results.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + "\n")
    return run


def sh(*args: str) -> str:
    p = subprocess.run([PY, *args], cwd=REPO, capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    return p.stdout


def test_validate_bundles(tmp_path=None):
    tmp = Path(tmp_path or tempfile.mkdtemp())
    for b in sorted((REPO / "bundles").iterdir()):
        if (b / "agent.yaml").is_file():
            out = sh("scripts/validate_bundle.py", str(b), "--zip", str(tmp / "zips"))
            assert "PASSED" in out and "sha256=" in out


def test_validate_rejects_bad_bundle(tmp_path=None):
    tmp = Path(tmp_path or tempfile.mkdtemp())
    bad = tmp / "bad"
    shutil.copytree(REPO / "bundles" / "run02_baseline", bad)
    (bad / "agent.yaml").write_text((bad / "agent.yaml").read_text().replace("run_command", "run_shell"))
    (bad / "notes.csv").write_text("x")
    p = subprocess.run([PY, "scripts/validate_bundle.py", str(bad)], cwd=REPO, capture_output=True, text=True)
    assert p.returncode == 1
    assert "unknown tool 'run_shell'" in p.stdout and "disallowed extension: notes.csv" in p.stdout


def test_ledger_and_pilot(tmp_path=None):
    tmp = Path(tmp_path or tempfile.mkdtemp())
    data = make_data(tmp)
    run = make_results(tmp, data)
    out = sh("scripts/build_ledger.py", str(run), "--bundle-id", "abc123", "--tasks", str(data / "tasks.jsonl"),
             "--tool-cap", "28", "--out", str(tmp / "ledger.csv"))
    df = pd.read_csv(tmp / "ledger.csv").set_index("instance_id")
    assert df.loc["demo_1", "failure_type"] == "resolved" and df.loc["demo_1", "loc_hit"] == True  # noqa: E712
    assert df.loc["demo_2", "failure_type"] == "tests_failed" and df.loc["demo_2", "loc_hit"] == False  # noqa: E712
    assert df.loc["demo_3", "failure_type"] == "context_overflow"
    assert "by group" in out and "wrong place" in out
    out = sh("scripts/pick_pilot.py", str(tmp / "ledger.csv"), "--per-outcome", "1", "--out", str(tmp / "pilot.txt"))
    ids = (tmp / "pilot.txt").read_text().split()
    assert set(ids) == {"demo_1", "demo_2", "demo_3"}


def test_localization_benchmark(tmp_path=None):
    tmp = Path(tmp_path or tempfile.mkdtemp())
    data = make_data(tmp)
    sh("analysis/localization_benchmark.py", "--data", str(data), "--out", str(tmp / "loc"))
    per = pd.read_csv(tmp / "loc" / "per_task.csv").set_index("instance_id")
    assert per.loc["demo_1", "gold_found"] and per.loc["demo_1", "grep_strict"] == 1
    assert per.loc["demo_1", "graph_strict"] == 1 and per.loc["demo_1", "n_seeds"] >= 1
    assert per.loc["demo_1", "tfidf_strict"] == 1
    assert per.loc["demo_2", "gold_found"] and not per.loc["demo_3", "gold_found"]
    assert (tmp / "loc" / "summary.md").is_file()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
