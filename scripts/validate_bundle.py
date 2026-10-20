#!/usr/bin/env python3
"""Validate a submission bundle against the competition rules, then package it.

Checks are taken from HARNESS_README.md (sections 2.2-2.4 and 3.2):
  - exactly one root config (agent.yaml / agent.yml / root_agent.yaml / root_agent.yml)
  - every !include resolves to a file inside the bundle (no absolute paths, no ..)
  - no symlinks, only allowed file extensions, total size < 3 GiB
  - exactly one declared base model, from the allowed list
  - tool names are known harness tools (agent_tool entries are followed)
  - sampling limits: max_output_tokens and thinking_budget in range
  - eval_config.yaml (if present) has only known keys

Usage:
  python scripts/validate_bundle.py bundles/v3_overflow_fix            # validate only
  python scripts/validate_bundle.py bundles/v3_overflow_fix --zip out/  # validate + zip

The zip is deterministic (fixed timestamps, sorted entries), so the same bundle
always gives the same SHA-256. Use that hash as the bundle's version id in the ledger.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

import yaml

ROOT_NAMES = ["agent.yaml", "agent.yml", "root_agent.yaml", "root_agent.yml"]
ALLOWED_MODELS = {
    "gemma-4-31b-it-qat-w4a16-ct",
    "gemma-4-12b-it-qat-w4a16-ct",
    "gemma-4-e4b-it-qat-w4a16-ct",
    "gemma-4-e2b-it-qat-w4a16-ct",
}
KNOWN_TOOLS = {
    "run_command", "submit_patch", "get_status", "read_file", "edit_file", "write_file",
    "get_code_neighbors", "search_similar_code", "get_code_subgraph",
}
ALLOWED_EXT = {".yaml", ".yml", ".md", ".txt", ".py", ".json", ".safetensors"}
MAX_TOTAL_BYTES = 3 * 1024 ** 3
MAX_CONTEXT = 32768
EVAL_KEYS = {"timeout_seconds", "max_tool_calls", "max_time_minutes", "max_turns"}
# ADK fills {name} placeholders in instructions from session state. These are the ones the
# harness provides; anything else must come from an output_key in your own agents.
KNOWN_STATE_KEYS = {"problem_description", "hints"}


class Include(str):
    """Marker for an unresolved !include path."""


class Loader(yaml.SafeLoader):
    pass


Loader.add_constructor("!include", lambda loader, node: Include(loader.construct_scalar(node)))


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.info: list[str] = []

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def note(self, msg: str) -> None:
        self.info.append(msg)


def load_yaml(path: Path, bundle: Path, rep: Report, depth: int = 0):
    """Load YAML and resolve !include recursively (md/txt -> str, yaml -> parsed)."""
    if depth > 10:
        rep.err(f"{path}: include depth > 10")
        return None
    data = yaml.load(path.read_text(encoding="utf-8"), Loader=Loader)
    return resolve(data, path.parent, bundle, rep, depth)


def resolve(node, base: Path, bundle: Path, rep: Report, depth: int):
    if isinstance(node, Include):
        rel = str(node)
        if rel.startswith("/") or "\x00" in rel or ".." in Path(rel).parts:
            rep.err(f"illegal include path: {rel}")
            return ""
        target = (base / rel).resolve()
        if bundle.resolve() not in target.parents:
            rep.err(f"include escapes bundle: {rel}")
            return ""
        if not target.is_file():
            rep.err(f"include not found: {rel} (from {base})")
            return ""
        if target.suffix in (".md", ".txt"):
            return target.read_text(encoding="utf-8")
        if target.suffix in (".yaml", ".yml"):
            return load_yaml(target, bundle, rep, depth + 1)
        rep.err(f"include of unsupported type: {rel}")
        return ""
    if isinstance(node, dict):
        return {k: resolve(v, base, bundle, rep, depth) for k, v in node.items()}
    if isinstance(node, list):
        return [resolve(v, base, bundle, rep, depth) for v in node]
    return node


def walk_agent(cfg: dict, cfg_path: Path, bundle: Path, rep: Report, seen: set, out: dict) -> None:
    """Collect models, tools, instructions and sampling from an agent and its children."""
    key = str(cfg_path.resolve())
    if key in seen:
        return
    seen.add(key)
    name = cfg.get("name", cfg_path.stem)
    agent_class = cfg.get("agent_class", "LlmAgent")
    out["agents"].append(f"{name} ({agent_class}) <- {cfg_path.relative_to(bundle)}")

    if cfg.get("model"):
        model = re.sub(r"^(openai|google|hosted_vllm|custom)/", "", str(cfg["model"]))
        out["models"].add(model)
    elif agent_class == "LlmAgent":
        rep.warn(f"agent '{name}' declares no model")

    instr = cfg.get("instruction") or ""
    if instr:
        out["instructions"][name] = instr
        for var in set(re.findall(r"(?<!\{)\{([A-Za-z_]\w*)\}(?!\})", instr)):
            if var not in KNOWN_STATE_KEYS:
                rep.warn(f"agent '{name}': instruction uses {{{var}}}; ADK will try to fill it from "
                         f"session state and may fail if no agent sets output_key '{var}'")
        if "{hints}" in instr:
            rep.warn(f"agent '{name}': {{hints}} is only set when hints_text is non-empty "
                     "(it is empty for all 129 public tasks)")

    gcc = cfg.get("generate_content_config")
    if isinstance(gcc, dict):
        out["sampling"][name] = gcc
        check_sampling(name, gcc, rep)

    def child(rel: str) -> None:
        p = (cfg_path.parent / rel).resolve()
        if bundle.resolve() not in p.parents or not p.is_file():
            # Not found next to the referencing file. Nested config_paths written relative to the bundle root
            # (agents/analyst.yaml -> agent_tool config_path: agents/explorer.yaml) load in the real harness:
            # x_v26_workflow's explorer ran on Kaggle on 20 Oct 2026.
            q = (bundle / rel).resolve()
            if bundle.resolve() in q.parents and q.is_file() and cfg_path.parent.resolve() != bundle.resolve():
                rep.note(f"agent '{name}': config_path '{rel}' resolves from the bundle root, not from "
                         f"{cfg_path.parent.relative_to(bundle)}/ (the harness accepts this: seen on Kaggle, 20 Oct 2026)")
                p = q
            else:
                rep.err(f"agent '{name}': config_path not found inside bundle: {rel}")
                return
        sub = load_yaml(p, bundle, rep)
        if isinstance(sub, dict):
            walk_agent(sub, p, bundle, rep, seen, out)

    for t in cfg.get("tools") or []:
        if isinstance(t, str):
            out["tools"].setdefault(name, []).append(t)
            if t not in KNOWN_TOOLS:
                rep.err(f"agent '{name}': unknown tool '{t}'")
        elif isinstance(t, dict) and "agent_tool" in t:
            at = t["agent_tool"] or {}
            out["tools"].setdefault(name, []).append(f"agent_tool:{at.get('config_path')}")
            if at.get("config_path"):
                child(at["config_path"])
        elif isinstance(t, dict):
            rep.warn(f"agent '{name}': inline tool entry not checked: {list(t)}")
    for sa in cfg.get("sub_agents") or []:
        if isinstance(sa, dict) and sa.get("config_path"):
            child(sa["config_path"])
    for s in cfg.get("skills") or []:
        sp = (cfg_path.parent / s)
        if not (sp / "SKILL.md").is_file():
            rep.err(f"agent '{name}': skill '{s}' has no SKILL.md")
        else:
            head = (sp / "SKILL.md").read_text(encoding="utf-8")
            if not re.search(r"^---\s*\n(?:.*\n)*?name:\s*\S+", head):
                rep.err(f"skill '{s}': SKILL.md frontmatter must contain 'name:'")


def check_sampling(name: str, gcc: dict, rep: Report) -> None:
    mot = gcc.get("max_output_tokens")
    tc = gcc.get("thinking_config") or {}
    tb = tc.get("thinking_budget")
    if mot is not None and not (1 <= int(mot) <= MAX_CONTEXT):
        rep.err(f"agent '{name}': max_output_tokens {mot} outside 1..{MAX_CONTEXT}")
    if tb is not None and not (0 <= int(tb) <= MAX_CONTEXT):
        rep.err(f"agent '{name}': thinking_budget {tb} outside 0..{MAX_CONTEXT}")
    if mot and tb and int(tb) > 0 and int(mot) - int(tb) < 2048:
        rep.warn(f"agent '{name}': only {int(mot) - int(tb)} output tokens left after thinking; "
                 "large edit_file calls may be cut off (README gotcha #1)")
    if tc.get("thinking_level") is not None:
        rep.warn(f"agent '{name}': README advises omitting thinking_level when serving via vLLM")
    if tb is not None and int(tb) > 0 and tc.get("include_thoughts") is False:
        rep.note(f"agent '{name}': thinking is ON (budget {tb}) but thoughts are stripped from "
                 "history (include_thoughts: false). Set thinking_budget: 0 to turn thinking off.")


def check_files(bundle: Path, rep: Report) -> list[Path]:
    files, total = [], 0
    for p in sorted(bundle.rglob("*")):
        if p.is_symlink():
            rep.err(f"symlink not allowed: {p.relative_to(bundle)}")
            continue
        if p.is_file():
            if p.suffix.lower() not in ALLOWED_EXT:
                rep.err(f"disallowed extension: {p.relative_to(bundle)}")
            total += p.stat().st_size
            files.append(p)
    if total >= MAX_TOTAL_BYTES:
        rep.err(f"bundle is {total:,} bytes; limit is < 3 GiB")
    rep.note(f"{len(files)} files, {total:,} bytes")
    return files


def check_eval_config(bundle: Path, rep: Report) -> dict:
    p = next((bundle / n for n in ("eval_config.yaml", "eval_config.yml") if (bundle / n).is_file()), None)
    if p is None:
        rep.warn("no eval_config.yaml: harness defaults apply (about 60 min and 100 tool calls per "
                 "task), which can exhaust the 12-hour total on stuck tasks")
        return {}
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    ev = raw.get("evaluation", raw)
    unknown = set(ev) - EVAL_KEYS
    if unknown:
        rep.err(f"eval_config.yaml: unknown keys {sorted(unknown)}")
    if "max_time_minutes" in ev:
        worst = float(ev["max_time_minutes"]) * 120 / 60
        rep.note(f"worst case at {ev['max_time_minutes']} min/task x 120 tasks = {worst:.1f} h "
                 "(limit 12 h incl. setup)")
    return ev


def validate(bundle: Path) -> tuple[Report, dict]:
    rep = Report()
    out = {"agents": [], "models": set(), "tools": {}, "instructions": {}, "sampling": {}}
    roots = [n for n in ROOT_NAMES if (bundle / n).is_file()]
    if len(roots) != 1:
        rep.err(f"need exactly one root config, found {roots or 'none'}")
        return rep, out
    files = check_files(bundle, rep)
    root = bundle / roots[0]
    cfg = load_yaml(root, bundle, rep)
    if not isinstance(cfg, dict):
        rep.err("root config is not a mapping")
        return rep, out
    walk_agent(cfg, root, bundle, rep, set(), out)
    if len(out["models"]) != 1:
        rep.err(f"exactly one base model required, found {sorted(out['models'])}")
    elif next(iter(out["models"])) not in ALLOWED_MODELS:
        rep.err(f"model {next(iter(out['models']))} is not an allowed competition model")
    out["eval"] = check_eval_config(bundle, rep)
    chars = sum(len(s) for s in out["instructions"].values())
    rep.note(f"instruction text: {chars:,} chars (~{chars // 4:,} tokens, a rough estimate)")
    out["files"] = [str(f.relative_to(bundle)) for f in files]
    return rep, out


def make_zip(bundle: Path, out_dir: Path) -> tuple[Path, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    zpath = out_dir / f"{bundle.name}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(p for p in bundle.rglob("*") if p.is_file()):
            info = zipfile.ZipInfo(p.relative_to(bundle).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, p.read_bytes())
    with zipfile.ZipFile(zpath) as z:
        names = z.namelist()
        assert any(n in ROOT_NAMES for n in names), "root config missing from zip root"
    return zpath, hashlib.sha256(zpath.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--zip", type=Path, metavar="OUT_DIR", help="also write a deterministic zip here")
    ap.add_argument("--json", action="store_true", help="print a machine-readable summary")
    args = ap.parse_args()
    bundle = args.bundle.resolve()
    if not bundle.is_dir():
        print(f"not a directory: {bundle}", file=sys.stderr)
        return 2
    rep, out = validate(bundle)

    print(f"Bundle: {bundle}")
    for a in out["agents"]:
        print(f"  agent  {a}")
    print(f"  model  {', '.join(sorted(out['models'])) or '-'}")
    for name, tools in out["tools"].items():
        print(f"  tools  {name}: {', '.join(tools)}")
    for name, s in out["sampling"].items():
        print(f"  sample {name}: {json.dumps(s, sort_keys=True)}")
    if out.get("eval"):
        print(f"  eval   {json.dumps(out['eval'], sort_keys=True)}")
    for m in rep.info:
        print(f"  info   {m}")
    for m in rep.warnings:
        print(f"  WARN   {m}")
    for m in rep.errors:
        print(f"  ERROR  {m}")

    if rep.errors:
        print(f"FAILED: {len(rep.errors)} error(s)")
        return 1
    print("PASSED")
    if args.zip:
        zpath, sha = make_zip(bundle, args.zip)
        print(f"zip    {zpath}  sha256={sha}  (bundle id {sha[:12]})")
    if args.json:
        print(json.dumps({"bundle": str(bundle), "models": sorted(out["models"]), "tools": out["tools"],
                          "errors": rep.errors, "warnings": rep.warnings}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
