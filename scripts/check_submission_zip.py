#!/usr/bin/env python3
"""Check a submission.zip exactly as it will be uploaded. Run this on the file before every upload.

Why: submission #1 (19 Oct 2026) failed with "Notebook Threw Exception". The uploaded zip had the
right files, but inside a `submission/` folder (so `agent.yaml` was not at the root) plus macOS
`__MACOSX/` and `._*` entries. validate_bundle.py checks a folder; this checks the zip itself.

Checks:
  - the file is a readable zip
  - a root config (agent.yaml / agent.yml / root_agent.yaml / root_agent.yml) is a top-level entry
  - no junk entries (__MACOSX/, ._*, .DS_Store, Thumbs.db) and no absolute or ../ paths
  - the unzipped contents pass validate_bundle.py's checks
  - with --bundle: the unzipped files are byte-identical to that bundle folder

Usage:
  python scripts/check_submission_zip.py submission.zip
  python scripts/check_submission_zip.py submission.zip --bundle bundles/v3_overflow_fix

Exit code 0 = safe to upload, 1 = do not upload.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_bundle import ROOT_NAMES, validate  # noqa: E402

JUNK_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}


def check(zpath: Path, bundle: Path | None = None) -> tuple[list[str], list[str]]:
    """Return (errors, notes)."""
    errors: list[str] = []
    notes: list[str] = []
    data = zpath.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    notes.append(f"{zpath.name}: {len(data):,} bytes, sha256 {sha} (bundle id {sha[:12]})")
    try:
        z = zipfile.ZipFile(zpath)
    except zipfile.BadZipFile:
        return [f"{zpath} is not a zip file"], notes

    with z:
        names = z.namelist()
        files = [n for n in names if not n.endswith("/")]
        for n in names:
            p = PurePosixPath(n)
            if p.is_absolute() or ".." in p.parts:
                errors.append(f"unsafe path in zip: {n}")
            if "__MACOSX" in p.parts or p.name.startswith("._") or p.name in JUNK_NAMES:
                errors.append(f"junk entry (made by Finder/Explorer?): {n}")

        roots = [n for n in files if n in ROOT_NAMES]
        if len(roots) != 1:
            nested = sorted(n for n in files if PurePosixPath(n).name in ROOT_NAMES)
            hint = ""
            if nested:
                hint = (f"; found {nested[0]} instead. The files are inside a folder: zip the files "
                        "inside the bundle folder, not the folder itself")
            errors.append(f"need exactly one root config at the top level of the zip, found {roots or 'none'}{hint}")

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bundle"
            out.mkdir()
            safe = [n for n in files
                    if not (PurePosixPath(n).is_absolute() or ".." in PurePosixPath(n).parts)]
            for n in safe:
                dest = out / n
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(z.read(n))

            if roots:
                rep, info = validate(out)
                errors += [f"bundle check: {e}" for e in rep.errors]
                notes += [f"bundle check warning: {w}" for w in rep.warnings]
                if info.get("models"):
                    notes.append(f"model: {', '.join(sorted(info['models']))}")
                if info.get("eval"):
                    notes.append(f"eval_config: {info['eval']}")

            if bundle is not None:
                want = {p.relative_to(bundle).as_posix(): p.read_bytes()
                        for p in bundle.rglob("*") if p.is_file()}
                got = {n: (out / n).read_bytes() for n in safe}
                for n in sorted(set(want) - set(got)):
                    errors.append(f"missing from zip (present in {bundle}): {n}")
                for n in sorted(set(got) - set(want)):
                    errors.append(f"extra file in zip (not in {bundle}): {n}")
                for n in sorted(set(want) & set(got)):
                    if want[n] != got[n]:
                        errors.append(f"differs from {bundle}: {n}")
                if not (set(want) ^ set(got)) and all(want[n] == got[n] for n in want):
                    notes.append(f"contents identical to {bundle}")
    return errors, notes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("zip", type=Path)
    ap.add_argument("--bundle", type=Path, help="bundle folder the zip must match exactly")
    args = ap.parse_args()
    if not args.zip.is_file():
        print(f"not a file: {args.zip}", file=sys.stderr)
        return 2
    if args.bundle is not None and not args.bundle.is_dir():
        print(f"not a directory: {args.bundle}", file=sys.stderr)
        return 2
    errors, notes = check(args.zip, args.bundle)
    for m in notes:
        print(f"  info   {m}")
    for m in errors:
        print(f"  ERROR  {m}")
    print("OK: safe to upload" if not errors else "FAIL: do not upload this zip")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
