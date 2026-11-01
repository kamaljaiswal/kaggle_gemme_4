"""locate.py: rank tracked Python files in /workspace by the issue text and print outlines of the top ones.

Usage: python3 locate.py <any words from the issue: title, identifiers, error message, paths>
Standard library only. Prints at most ~120 lines.
"""
import ast, collections, math, os, re, subprocess, sys

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
TOP = 5
STOP = set("the a an and or of to in on for is are was be it this that with as by from not if when but at into "
           "can should would does do did has have had will i we you they use used using get set new add fix bug error "
           "issue problem expected actual behavior behaviour code like just also".split())


def tracked_py():
    try:
        out = subprocess.run(["git", "-C", ROOT, "ls-files", "*.py", "**/*.py"], capture_output=True, text=True, timeout=30).stdout
        files = [f for f in out.split("\n") if f.endswith(".py")]
    except Exception:
        files = []
    if not files:
        for d, _, fs in os.walk(ROOT):
            if any(p.startswith(".") for p in d.split(os.sep)):
                continue
            files += [os.path.relpath(os.path.join(d, f), ROOT) for f in fs if f.endswith(".py")]
    return sorted(set(files))


def is_test(path):
    p = path.lower()
    return "/tests/" in "/" + p or p.startswith("tests/") or os.path.basename(p).startswith("test_") or p.endswith("_test.py")


def tokens(text):
    return [t.lower() for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text)]


def split_ident(t):
    parts = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", t).replace("_", " ").lower().split()
    return [p for p in parts if len(p) > 2]


def main():
    query_text = " ".join(sys.argv[1:])
    if not query_text.strip():
        print("usage: locate.py <words from the issue>"); return
    idents = set(re.findall(r"`([^`]+)`", query_text))
    idents |= set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+\b", query_text))  # dotted names
    idents |= set(re.findall(r"\b[a-z]+_[a-z0-9_]+\b", query_text))                                     # snake_case
    idents |= set(re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z0-9]+)+\b", query_text))                        # CamelCase
    paths = set(re.findall(r"[\w/.-]+\.py\b", query_text))
    q = collections.Counter()
    for t in tokens(query_text):
        if t not in STOP:
            q[t] += 1
            for p in split_ident(t):
                q[p] += 0.5

    files = tracked_py()
    docs, df = {}, collections.Counter()
    for f in files:
        try:
            with open(os.path.join(ROOT, f), errors="ignore") as fh:
                text = fh.read()
        except Exception:
            continue
        tf = collections.Counter()
        for t in tokens(text):
            tf[t] += 1
            for p in split_ident(t):
                tf[p] += 0.3
        docs[f] = (text, tf, len(text))
        for t in set(tf):
            df[t] += 1
    N = max(1, len(docs))
    avgdl = sum(d[2] for d in docs.values()) / N if docs else 1
    k1, b = 1.2, 0.75
    scores = {}
    for f, (text, tf, dl) in docs.items():
        s = 0.0
        for t, qw in q.items():
            if t not in tf:
                continue
            idf = math.log(1 + (N - df[t] + 0.5) / (df[t] + 0.5))
            s += qw * idf * (tf[t] * (k1 + 1)) / (tf[t] + k1 * (1 - b + b * dl / avgdl))
        for ident in idents:
            last = ident.split(".")[-1]
            if last and re.search(r"\b" + re.escape(last) + r"\b", text):
                s += 4.0
                if re.search(r"^\s*(def|class)\s+" + re.escape(last) + r"\b", text, re.M):
                    s += 6.0
        for p in paths:
            if f.endswith(p):
                s += 20.0
        if is_test(f):
            s *= 0.35
        if f.startswith("docs_src/"):
            s *= 0.8 if "docs" in q else 0.6
        scores[f] = s
    ranked = [f for f, s in sorted(scores.items(), key=lambda x: -x[1]) if s > 0][:TOP]
    if not ranked:
        print("no matching files; try other words from the issue"); return
    print("TOP FILES (best first). Read only the span you need, e.g. sed -n 'A,Bp' FILE")
    for f in ranked:
        text = docs[f][0]
        print(f"\n== {f}  ({text.count(chr(10)) + 1} lines, score {scores[f]:.1f})")
        try:
            tree = ast.parse(text)
        except Exception as e:
            print("   (outline unavailable:", type(e).__name__ + ")"); continue
        hits = {i.split(".")[-1] for i in idents}
        lines = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                mark = " <==" if node.name in hits else ""
                lines.append(f"   {node.lineno:5d}-{getattr(node, 'end_lineno', node.lineno):<5d} {type(node).__name__[:5].lower():5s} {node.name}{mark}")
                if isinstance(node, ast.ClassDef):
                    for sub in node.body:
                        if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            m2 = " <==" if sub.name in hits else ""
                            lines.append(f"   {sub.lineno:5d}-{getattr(sub, 'end_lineno', sub.lineno):<5d}   .{sub.name}{m2}")
        marked = [l for l in lines if "<==" in l]
        shown = lines if len(lines) <= 18 else (marked + [l for l in lines if l not in marked][: max(0, 18 - len(marked))])
        print("\n".join(shown) if shown else "   (no top-level defs)")
        if len(lines) > len(shown):
            print(f"   ... {len(lines) - len(shown)} more defs; marked ones (<==) match the issue")


if __name__ == "__main__":
    main()
