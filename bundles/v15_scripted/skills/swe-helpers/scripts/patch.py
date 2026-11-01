"""patch.py: replace lines START..END (1-based, inclusive) of FILE with the text read from stdin, then compile-check.

Usage (quoted heredoc so nothing is escaped; or --from /tmp/new.txt when stdin is not available):
    python3 patch.py FILE START END <<'PATCH'
    <new text, exactly as it should appear in the file>
    PATCH
Use END = START-1 to insert before START without removing anything.
If the file no longer compiles, the original is restored and the error is printed.
Prints the changed region with line numbers so you can verify it.
"""
import os, py_compile, sys

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


def main():
    args = sys.argv[1:]
    src = None
    if "--from" in args:
        i = args.index("--from"); src = args[i + 1]; del args[i:i + 2]
    if len(args) != 3:
        print("usage: patch.py FILE START END  (new text on stdin, or --from /tmp/new.txt)"); sys.exit(2)
    path, start, end = args[0], int(args[1]), int(args[2])
    full = path if os.path.isabs(path) else os.path.join(ROOT, path)
    if not os.path.isfile(full):
        print(f"ERROR: no such file {path}"); sys.exit(2)
    base = os.path.basename(path)
    if "/tests/" in "/" + path or base.startswith("test_") or base.endswith("_test.py") or base in ("conftest.py", "pytest.ini"):
        print("ERROR: refusing to edit a test file"); sys.exit(2)
    new = open(src, encoding="utf-8").read() if src else sys.stdin.read()
    if new and not new.endswith("\n"):
        new += "\n"
    with open(full, encoding="utf-8") as f:
        lines = f.readlines()
    n = len(lines)
    if not (1 <= start <= n + 1) or not (start - 1 <= end <= n):
        print(f"ERROR: bad range {start}..{end}; file has {n} lines"); sys.exit(2)
    original = "".join(lines)
    removed = lines[start - 1:end]
    updated = "".join(lines[:start - 1]) + new + "".join(lines[end:])
    with open(full, "w", encoding="utf-8") as f:
        f.write(updated)
    if full.endswith(".py"):
        try:
            py_compile.compile(full, doraise=True)
        except py_compile.PyCompileError as e:
            with open(full, "w", encoding="utf-8") as f:
                f.write(original)
            print("ERROR: file does not compile after the edit; original restored.\n" + str(e).strip()[-600:])
            print("--- the text you sent, with line numbers (check indentation) ---")
            for i, l in enumerate(new.splitlines(), 1):
                print(f"{i:4d}| {l}")
            sys.exit(1)
    added = new.count("\n")
    print(f"OK: {path} lines {start}-{end} ({len(removed)} lines) replaced by {added} lines; compiles.")
    new_lines = updated.splitlines()
    lo, hi = max(1, start - 6), min(len(new_lines), start - 1 + added + 6)
    for i in range(lo, hi + 1):
        flag = "*" if start <= i < start + added else " "
        print(f"{i:5d}{flag} {new_lines[i - 1]}")


if __name__ == "__main__":
    main()
