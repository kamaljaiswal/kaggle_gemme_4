"""check.py: run /tmp/repro.py (if present) and one test file; print only what matters.

Usage: python3 check.py TEST_FILE [-k KEYWORD] [--timeout SECONDS]
Prints: repro output (last 15 lines), the pytest exit code with its meaning, the summary line, the first failure (short).
"""
import os, re, subprocess, sys

import os as _os, sys as _sys


def _find_root():
    """The repository under test. On the scorer it is /workspace; the local subprocess sandbox puts it at
    <sandbox>/workspace and runs skill scripts from a temp copy under <sandbox>/tmp/, so walk up from both."""
    env = _os.environ.get("WORKSPACE")
    if env and _os.path.isdir(env):
        return env
    cwd = _os.getcwd()
    if _os.path.isdir(_os.path.join(cwd, ".git")) or _os.path.isfile(_os.path.join(cwd, "pyproject.toml")):
        return cwd
    if _os.path.isdir("/workspace"):
        return "/workspace"
    for start in (cwd, _os.path.dirname(_os.path.abspath(__file__))):
        p = start
        for _ in range(8):
            cand = _os.path.join(p, "workspace")
            if _os.path.isdir(cand):
                return cand
            parent = _os.path.dirname(p)
            if parent == p:
                break
            p = parent
    return "/workspace"


ROOT = _find_root()
MEANING = {0: "all selected tests PASSED", 1: "a test FAILED", 2: "collection/import error or interrupted",
           4: "pytest usage error (wrong path or option)", 5: "no tests ran (bad -k keyword or path)", 124: "TIMED OUT"}


def run(cmd, timeout):
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired as e:
        out = e.stdout or ""
        return 124, out.decode(errors="ignore") if isinstance(out, bytes) else out


def main():
    args = sys.argv[1:]
    timeout = 150
    if "--timeout" in args:
        i = args.index("--timeout"); timeout = int(args[i + 1]); del args[i:i + 2]
    kw = None
    if "-k" in args:
        i = args.index("-k"); kw = args[i + 1]; del args[i:i + 2]
    if not args:
        print("usage: check.py TEST_FILE [-k KEYWORD]"); sys.exit(2)
    test = args[0]
    if os.path.isfile("/tmp/repro.py"):
        rc, out = run([sys.executable, "/tmp/repro.py"], 60)
        tail = "\n".join(out.strip().splitlines()[-15:])
        print(f"REPRO /tmp/repro.py exit {rc}:\n{tail or '(no output)'}\n")
    if not os.path.isfile(os.path.join(ROOT, test)):
        print(f"ERROR: test file not found: {test}. Find it with: find tests -name '*keyword*.py'"); sys.exit(2)
    cmd = [sys.executable, "-m", "pytest", test, "-x", "-q", "--tb=short", "-p", "no:cacheprovider"]
    if kw:
        cmd += ["-k", kw]
    rc, out = run(cmd, timeout)
    print(f"PYTEST exit code {rc}: {MEANING.get(rc, 'see output')}")
    lines = out.splitlines()
    summary = [l for l in lines if re.search(r"\d+ (passed|failed|error|skipped|deselected)", l)]
    print("summary:", summary[-1].strip() if summary else "(none)")
    if rc != 0:
        start = next((i for i, l in enumerate(lines) if l.startswith("=") and ("FAILURES" in l or "ERRORS" in l)), None)
        chunk = lines[start:start + 40] if start is not None else lines[-30:]
        print("\n".join(chunk))


if __name__ == "__main__":
    main()
