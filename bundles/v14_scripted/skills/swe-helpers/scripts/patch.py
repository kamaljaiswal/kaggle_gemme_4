"""patch.py: replace lines START..END (1-based, inclusive) of FILE with the text read from stdin, then compile-check.

Usage (quoted heredoc so nothing is escaped):
    python3 patch.py FILE START END <<'PATCH'
    <new text, exactly as it should appear in the file>
    PATCH
Use END = START-1 to insert before START without removing anything.
If the file no longer compiles, the original is restored and the error is printed.
Prints the changed region with line numbers so you can verify it.
"""
import os, py_compile, sys

ROOT = os.environ.get("WORKSPACE", "/workspace")


def main():
    if len(sys.argv) != 4:
        print("usage: patch.py FILE START END  (new text on stdin)"); sys.exit(2)
    path, start, end = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    full = path if os.path.isabs(path) else os.path.join(ROOT, path)
    if not os.path.isfile(full):
        print(f"ERROR: no such file {path}"); sys.exit(2)
    base = os.path.basename(path)
    if "/tests/" in "/" + path or base.startswith("test_") or base.endswith("_test.py") or base in ("conftest.py", "pytest.ini"):
        print("ERROR: refusing to edit a test file"); sys.exit(2)
    new = sys.stdin.read()
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
