#!/usr/bin/env python3
"""Localization benchmark: can a cheap method find the file the reference fix edits?

No GPU and no model. For every task it ranks the repository's non-test .py files with
four methods and records where the first gold file lands:

  tfidf   TF-IDF over code-aware tokens of each file vs the issue text
  grep    files containing code-like literals from the issue (backticked code,
          dotted names, snake_case / CamelCase identifiers, quoted messages),
          weighted by how rare each literal is in the repo
  embed   emulates search_similar_code: issue identifiers are resolved to graph
          nodes, and other nodes are ranked by cosine similarity of the provided
          256-d embeddings (the harness has no text encoder, so a query must be a symbol)
  graph   emulates get_code_neighbors: files of the resolved nodes plus files of
          their call-graph neighbours

Each method is scored two ways:
  strict  only files the method actually scores (no seed or no match = a miss)
  hybrid  the method's files first, then the rest in TF-IDF order

The reference patch is used ONLY to find the gold files for scoring. Nothing from it
reaches any ranking. These are file-level results; the agent still has to find the line.

Usage (on Kaggle, competition data attached):
  python analysis/localization_benchmark.py \
      --data /kaggle/input/competitions/gemma-4-developer-agent --out results/localization
Outputs per_task.csv, summary.csv and summary.md in --out.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import tarfile
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

KS = [1, 3, 5, 10, 20]
MAX_FILE_BYTES = 1_000_000
STOP = {
    "self", "none", "true", "false", "import", "from", "return", "print", "def", "class", "pass",
    "python", "pip", "install", "http", "https", "github", "com", "www", "issue", "error", "test",
    "tests", "the", "and", "for", "with", "this", "that", "args", "kwargs", "str", "int", "dict",
    "list", "bool", "float", "type", "object", "value", "name", "data", "json", "main", "init",
}


# ---------------------------------------------------------------- text helpers
def split_ident(tok: str) -> list[str]:
    parts = re.split(r"[_\W]+", re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", tok))
    return [p.lower() for p in parts if len(p) > 1]


def code_tokens(text: str) -> str:
    toks = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text)
    out = []
    for t in toks:
        out.append(t.lower())
        sub = split_ident(t)
        if len(sub) > 1:
            out.extend(sub)
    return " ".join(out)


def strip_template(text: str) -> str:
    """Drop pull-request template noise: HTML comments and checklist lines."""
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    keep = [ln for ln in text.splitlines() if not re.match(r"\s*[-*]\s*\[[ xX]\]", ln)]
    return "\n".join(keep)


def is_test_path(p: str) -> bool:
    p = p.lower()
    return bool(re.search(r"(^|/)(tests?|testing)/", p) or re.search(r"(^|/)test_[^/]*\.py$", p)
                or p.endswith("_test.py") or p.endswith("conftest.py"))


def files_in_patch(patch: str) -> list[str]:
    out = []
    for line in (patch or "").splitlines():
        if line.startswith("+++ "):
            p = line[4:].split("\t")[0].strip()
            if p != "/dev/null":
                out.append(p[2:] if p.startswith(("a/", "b/")) else p)
    return sorted(set(out))


def extract_literals(issue: str) -> list[str]:
    """Code-like strings an agent could grep for, most specific first."""
    text = strip_template(issue)
    lits: list[str] = []
    for span in re.findall(r"`([^`\n]{2,120})`", text):
        lits.extend(re.findall(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*", span))
    lits += re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+\b", text)   # dotted
    lits += re.findall(r"\b[a-z0-9]+_[a-z0-9_]+\b", text)                                    # snake_case
    lits += re.findall(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\b", text)                      # CamelCase
    lits += [m for m in re.findall(r"[\"']([^\"'\n]{8,80})[\"']", text) if " " in m]         # messages
    seen, out = set(), []
    for lit in lits:
        lit = lit.strip().strip(".")
        if len(lit) < 4 or lit.lower() in STOP or lit in seen or re.fullmatch(r"\d+", lit):
            continue
        if re.match(r"^(https?|www)\b", lit) or lit.endswith((".com", ".org", ".io")):
            continue
        seen.add(lit)
        out.append(lit)
    return out[:40]


# ---------------------------------------------------------------- data loading
ROOT_MARKERS = (".git", "pyproject.toml", "setup.py", "setup.cfg", "README.md", "README.rst")


def _norm(name: str) -> str:
    return name[2:] if name.startswith("./") else name


def read_snapshot(tgz: Path) -> tuple[dict[str, str], str]:
    """Return ({path: source} for .py files, wrapper_prefix).

    Paths are relative to the repository root. If the archive wraps the repo in one
    top-level directory (detected by a .git or packaging file directly inside it), that
    directory is stripped. The prefix is returned so callers can retry without it.
    """
    raw: dict[str, str] = {}
    tops, markers = set(), set()
    with tarfile.open(tgz, "r:*") as tar:
        for m in tar:
            name = _norm(m.name)
            parts = name.split("/")
            tops.add(parts[0])
            if len(parts) >= 2 and parts[1] in ROOT_MARKERS:
                markers.add(parts[0])
            if not m.isfile() or not name.endswith(".py") or m.size > MAX_FILE_BYTES:
                continue
            if "/.git/" in f"/{name}":
                continue
            f = tar.extractfile(m)
            if f is not None:
                raw[name] = f.read().decode("utf-8", errors="replace")
    prefix = ""
    if len(tops) == 1 and next(iter(tops)) in markers:
        prefix = next(iter(tops)) + "/"
        raw = {p[len(prefix):]: s for p, s in raw.items() if p.startswith(prefix)}
    return raw, prefix


def align_paths(src: dict[str, str], gold: set[str]) -> dict[str, str]:
    """If no gold path matches, try removing / adding one leading directory (path layout only)."""
    if not gold or gold & set(src):
        return src
    tops = {p.split("/", 1)[0] for p in src if "/" in p}
    if len(tops) == 1:
        pre = next(iter(tops)) + "/"
        alt = {p[len(pre):]: s for p, s in src.items() if p.startswith(pre)}
        if gold & set(alt):
            return alt
    return src


def load_graph(path: Path):
    if not path.is_file():
        return None
    g = json.loads(path.read_text(encoding="utf-8"))
    nodes = [n.get("id") for n in g.get("nodes", [])]
    adj = defaultdict(set)
    for e in g.get("edges", g.get("links", [])):
        s, t = e.get("source"), e.get("target")
        if s is not None and t is not None:
            adj[s].add(t)
            adj[t].add(s)
    return nodes, adj


def load_embeddings(path: Path):
    if not path.is_file():
        return None
    z = np.load(path, allow_pickle=False)
    keys = [k[:-4] if k.endswith(".npy") else k for k in z.files]
    mat = np.stack([z[k] for k in z.files]).astype(np.float32)
    mat /= np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9
    return keys, mat


def bare(node_id: str) -> str:
    """'fastapi/fastapi;fastapi.routing.f' -> 'fastapi.routing.f'"""
    return node_id.split(";", 1)[-1] if node_id else node_id


class ModuleIndex:
    """Map dotted node ids to repository files via module-path suffixes."""

    def __init__(self, files: list[str]):
        self.by_suffix: dict[str, list[str]] = defaultdict(list)
        for f in files:
            mod = f[:-3].replace("/", ".")
            if mod.endswith(".__init__"):
                mod = mod[: -len(".__init__")]
            parts = mod.split(".")
            for i in range(len(parts)):
                self.by_suffix[".".join(parts[i:])].append(f)

    def file_of(self, node_id: str) -> str | None:
        parts = bare(node_id).split(".")
        for j in range(len(parts), 0, -1):
            cands = self.by_suffix.get(".".join(parts[:j]))
            if cands:
                return min(cands, key=len)
        return None


def resolve_seeds(literals: list[str], nodes: list[str], max_ambiguity: int = 20) -> list[str]:
    """Resolve issue identifiers to graph nodes (exact / suffix match, like the harness)."""
    by_tail: dict[str, list[str]] = defaultdict(list)
    for n in nodes:
        b = bare(n).split(".")
        by_tail[b[-1]].append(n)
        if len(b) > 1:
            by_tail[".".join(b[-2:])].append(n)
    full = {bare(n): n for n in nodes}
    seeds: list[str] = []
    for lit in literals:
        if " " in lit:
            continue
        if lit in full:
            seeds.append(full[lit])
            continue
        tail2 = ".".join(lit.split(".")[-2:])
        cands = by_tail.get(tail2) or by_tail.get(lit.split(".")[-1]) or []
        if 0 < len(cands) <= max_ambiguity:
            seeds.extend(cands)
    return list(dict.fromkeys(seeds))


# ---------------------------------------------------------------- rankers
def rank_tfidf(files: list[str], src: dict[str, str], issue: str) -> list[str]:
    docs = [code_tokens(f + " " + src[f]) for f in files]
    vec = TfidfVectorizer(token_pattern=r"[a-z0-9_]{2,}", sublinear_tf=True, max_features=200_000)
    X = vec.fit_transform(docs)
    q = vec.transform([code_tokens(strip_template(issue))])
    scores = (X @ q.T).toarray().ravel()
    return [files[i] for i in np.argsort(-scores, kind="stable")]


def rank_grep(files: list[str], src: dict[str, str], literals: list[str]) -> list[str]:
    n = len(files)
    score = Counter()
    for lit in literals:
        hits = [f for f in files if lit in src[f]]
        if not hits or len(hits) > 0.5 * n:
            continue
        w = math.log(n / len(hits)) + (1.0 if "." in lit or "_" in lit or " " in lit else 0.0)
        for f in hits:
            score[f] += w
    return [f for f, _ in score.most_common()]


def rank_embed(seeds, emb, midx: ModuleIndex) -> list[str]:
    if not seeds or emb is None:
        return []
    keys, mat = emb
    pos = {k: i for i, k in enumerate(keys)}
    rows = [pos[s] for s in seeds if s in pos] or [pos[bare(s)] for s in seeds if bare(s) in pos]
    if not rows:
        return []
    sims = mat @ mat[rows].T                 # (nodes, seeds)
    best = sims.max(axis=1)
    file_score: dict[str, float] = {}
    for i in np.argsort(-best):
        f = midx.file_of(keys[i])
        if f and f not in file_score:
            file_score[f] = float(best[i])
        if len(file_score) >= 50:
            break
    return list(file_score)


def rank_graph(seeds, graph, midx: ModuleIndex, max_neighbors: int = 50) -> list[str]:
    if not seeds or graph is None:
        return []
    _, adj = graph
    score = Counter()
    for s in seeds:
        f = midx.file_of(s)
        if f:
            score[f] += 2.0
        for nb in list(adj.get(s, ()))[:max_neighbors]:
            fn = midx.file_of(nb)
            if fn:
                score[fn] += 1.0
    return [f for f, _ in score.most_common()]


def first_rank(ranking: list[str], gold: set[str]) -> int | None:
    for i, f in enumerate(ranking, 1):
        if f in gold:
            return i
    return None


def hybrid(primary: list[str], fallback: list[str]) -> list[str]:
    seen = set(primary)
    return primary + [f for f in fallback if f not in seen]


# ---------------------------------------------------------------- main loop
def run(data: Path, out: Path, limit: int | None, ids: set[str] | None) -> pd.DataFrame:
    tasks = [json.loads(l) for l in (data / "tasks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    if ids:
        tasks = [t for t in tasks if t["instance_id"] in ids]
    if limit:
        tasks = tasks[:limit]
    rows = []
    t0 = time.time()
    for k, t in enumerate(tasks, 1):
        iid = t["instance_id"]
        row = {"instance_id": iid, "repo": t.get("repo")}
        try:
            src_all, _ = read_snapshot(data / "snapshots" / f"{iid}.tgz")
            gold = {g for g in files_in_patch(t.get("patch", "")) if not is_test_path(g)}
            src_all = align_paths(src_all, gold)
            files = sorted(f for f in src_all if not is_test_path(f))
            gold_in_repo = gold & set(files)
            row.update({"n_files": len(files), "gold_files": ";".join(sorted(gold)),
                        "gold_found": bool(gold_in_repo)})
            if not gold_in_repo:
                row["note"] = "gold file not among snapshot .py files (new file or path mismatch)"
                rows.append(row)
                continue
            issue = t.get("problem_statement", "") + "\n" + (t.get("hints_text") or "")
            lits = extract_literals(issue)
            graph = load_graph(data / "graphs" / f"{iid}.json")
            emb = load_embeddings(data / "embeddings" / f"{iid}.npz")
            midx = ModuleIndex(files)
            seeds = resolve_seeds(lits, graph[0] if graph else (emb[0] if emb else []))
            r_tfidf = rank_tfidf(files, src_all, issue)
            strict = {
                "tfidf": r_tfidf,
                "grep": rank_grep(files, src_all, lits),
                "embed": rank_embed(seeds, emb, midx),
                "graph": rank_graph(seeds, graph, midx),
            }
            row.update({"n_literals": len(lits), "n_seeds": len(seeds),
                        "has_graph": graph is not None, "has_embed": emb is not None})
            for m, r in strict.items():
                row[f"{m}_strict"] = first_rank(r, gold_in_repo)
                row[f"{m}_hybrid"] = first_rank(hybrid(r, r_tfidf), gold_in_repo)
                row[f"{m}_covered"] = bool(r)
        except Exception as e:  # keep going; record the failure
            row["note"] = f"{type(e).__name__}: {e}"[:200]
        rows.append(row)
        if k % 10 == 0 or k == len(tasks):
            print(f"  {k}/{len(tasks)} tasks  ({time.time() - t0:.0f}s)", flush=True)
    df = pd.DataFrame(rows)
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "per_task.csv", index=False)
    return df


def summarize(df: pd.DataFrame, out: Path) -> pd.DataFrame:
    ok = df[df.get("gold_found", False) == True]  # noqa: E712
    recs = []
    for scope, d in [("ALL", ok)] + [(r, g) for r, g in ok.groupby("repo")]:
        for m in ["tfidf", "grep", "embed", "graph"]:
            for mode in ["strict", "hybrid"]:
                col = f"{m}_{mode}"
                if col not in d:
                    continue
                r = d[col]
                rec = {"scope": scope, "method": m, "mode": mode, "n": len(d)}
                for k in KS:
                    rec[f"hit@{k}"] = round(float((r.fillna(1e9) <= k).mean()), 3)
                rec["mrr"] = round(float((1.0 / r.dropna()).sum() / max(len(d), 1)), 3)
                if mode == "strict":
                    rec["covered"] = round(float(d[f"{m}_covered"].mean()), 3)
                recs.append(rec)
    s = pd.DataFrame(recs)
    s.to_csv(out / "summary.csv", index=False)
    lines = ["# Localization benchmark", "",
             f"Tasks: {len(df)}; with gold file in snapshot: {len(ok)}; "
             f"skipped: {len(df) - len(ok)}", "",
             "`covered` = share of tasks where the method returned any file at all.", ""]
    allv = s[s["scope"] == "ALL"]
    if len(allv):
        lines.append(allv.drop(columns=["scope"]).to_markdown(index=False))
    lines += ["", "## By repository", ""]
    rep = s[(s["scope"] != "ALL") & (s["mode"] == "hybrid")]
    if len(rep):
        lines.append(rep.to_markdown(index=False))
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return s


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, required=True, help="competition data dir (tasks.jsonl, snapshots/, ...)")
    ap.add_argument("--out", type=Path, default=Path("results/localization"))
    ap.add_argument("--limit", type=int, default=None, help="only the first N tasks (for a quick check)")
    ap.add_argument("--ids", type=Path, default=None, help="file with one instance_id per line")
    args = ap.parse_args()
    ids = set(args.ids.read_text().split()) if args.ids else None
    df = run(args.data, args.out, args.limit, ids)
    s = summarize(df, args.out)
    allv = s[(s["scope"] == "ALL")]
    print(allv.drop(columns=["scope"]).to_string(index=False))
    print(f"\nwrote {args.out}/per_task.csv, summary.csv, summary.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
