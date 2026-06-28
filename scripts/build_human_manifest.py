#!/usr/bin/env python3
"""Section III-D (human reference set): turn RefactoringMiner output into a
manifest scripts/run_pipeline.py can run, by checking out the pre- and
post-refactoring commits as separate git worktrees (full buildable project
trees, not just the one changed file).

Usage:
  uv run python scripts/build_human_manifest.py \
      --repo /path/to/checkout --out manifest.json --worktrees-dir /tmp/efsr-worktrees
  # Runs RefactoringMiner itself if --refactoring-miner-json is omitted.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from efsr.config import DEFAULT_CONFIG
from efsr.generation import (
    RefactoringMinerUnavailable,
    parse_refactoring_miner_output,
    run_refactoring_miner,
)
from efsr.protocol import RefactoringType

_TYPE_MAP = {"Extract Method": RefactoringType.EXTRACT_METHOD, "Extract Class": RefactoringType.EXTRACT_CLASS}


def _add_worktree(repo: Path, commit: str, worktrees_dir: Path) -> Path:
    destination = worktrees_dir / commit
    if not destination.exists():
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(destination), commit],
            cwd=repo, check=True, capture_output=True, text=True,
        )
    return destination


def _class_name_from_path(file_path: str) -> str:
    """Best-effort fully-qualified name from a standard Maven/Gradle layout
    (src/main/java/...); falls back to the bare filename stem if the path
    doesn't follow that convention.
    """
    parts = Path(file_path).parts
    for anchor in ("java",):
        if anchor in parts:
            idx = parts.index(anchor)
            package_parts = parts[idx + 1: -1]
            stem = Path(file_path).stem
            return ".".join((*package_parts, stem))
    return Path(file_path).stem


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--worktrees-dir", type=Path, required=True)
    parser.add_argument("--refactoring-miner-json", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    rm_json = args.refactoring_miner_json
    if rm_json is None:
        rm_json = args.repo / "refactoring-miner-output.json"
        try:
            run_refactoring_miner(args.repo, rm_json, DEFAULT_CONFIG)
        except RefactoringMinerUnavailable as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    mined = parse_refactoring_miner_output(rm_json)
    if args.limit:
        mined = mined[: args.limit]

    args.worktrees_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for i, refactoring in enumerate(mined):
        if not refactoring.file_path:
            continue
        try:
            original_dir = _add_worktree(args.repo, f"{refactoring.commit_sha}^", args.worktrees_dir)
            modified_dir = _add_worktree(args.repo, refactoring.commit_sha, args.worktrees_dir)
        except subprocess.CalledProcessError as exc:
            print(f"skipping {refactoring.commit_sha}: worktree checkout failed: {exc.stderr}", file=sys.stderr)
            continue

        manifest.append({
            "process": "Human",
            "target_id": f"{args.repo.name}:{refactoring.file_path}@{refactoring.commit_sha[:10]}",
            "refactoring_type": _TYPE_MAP[refactoring.refactoring_type].value,
            "original_project_dir": str(original_dir),
            "modified_project_dir": str(modified_dir),
            "original_source_file": str(original_dir / refactoring.file_path),
            "modified_source_file": str(modified_dir / refactoring.file_path),
            "class_name": _class_name_from_path(refactoring.file_path),
            # RefactoringMiner's JSON does carry the specific method name
            # (under the refactoring's code-element locations), but its
            # exact field varies across versions/refactoring kinds; left
            # unset here, which falls back to the class's highest-CC
            # method for the metric(T) check (efsr.metrics.pure_python).
            "method_name": None,
            "generation_index": 0,
        })

    args.out.write_text(json.dumps(manifest, indent=2))
    print(f"Wrote {len(manifest)} human-reference manifest entr(y/ies) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
