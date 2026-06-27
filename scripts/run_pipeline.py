#!/usr/bin/env python3
"""Full-corpus driver: loop the Stage 0-9 pipeline over a corpus manifest.

The manifest is a JSON file listing TransformationSpec-shaped dicts -- one
per (process, target, generated-transformation) triple to evaluate. This
script does not generate transformations itself (that is the job of the
LLM strategies / JDeodorant / RefactoringMiner extraction, run upstream and
recorded into the manifest); it runs the measurement pipeline over
whatever the manifest already contains and appends one row per
transformation to results/csv/transformations.csv.

Manifest schema (list of objects):
  {
    "process": "LLM-A",
    "target_id": "commons-lang:org.apache.commons.lang3.StringUtils#join",
    "refactoring_type": "ExtractMethod",
    "original_project_dir": "/path/to/original/checkout",
    "modified_project_dir": "/path/to/candidate/checkout",
    "original_source_file": "/path/to/original/.../StringUtils.java",
    "modified_source_file": "/path/to/candidate/.../StringUtils.java",
    "class_name": "org.apache.commons.lang3.StringUtils",
    "method_name": "join",
    "generation_index": 0
  }

Usage: python scripts/run_pipeline.py manifest.json [--limit N]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from efsr.config import DEFAULT_CONFIG
from efsr.pipeline import run_pipeline_for_transformation
from efsr.protocol import RefactoringType, TransformationSpec
from efsr.results import ResultsStore


def load_manifest(path: Path) -> list[TransformationSpec]:
    entries = json.loads(path.read_text())
    specs = []
    for e in entries:
        specs.append(TransformationSpec(
            process=e["process"],
            target_id=e["target_id"],
            refactoring_type=RefactoringType(e["refactoring_type"]),
            original_project_dir=Path(e["original_project_dir"]),
            modified_project_dir=Path(e["modified_project_dir"]),
            original_source_file=Path(e["original_source_file"]),
            modified_source_file=Path(e["modified_source_file"]),
            class_name=e["class_name"],
            method_name=e.get("method_name"),
            generation_index=e.get("generation_index", 0),
        ))
    return specs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--limit", type=int, default=None, help="process at most N entries")
    args = parser.parse_args()

    specs = load_manifest(args.manifest)
    if args.limit:
        specs = specs[: args.limit]

    store = ResultsStore(DEFAULT_CONFIG.results_csv)
    print(f"Running {len(specs)} transformation(s); writing to {DEFAULT_CONFIG.results_csv}")
    for i, spec in enumerate(specs, start=1):
        row = run_pipeline_for_transformation(spec, DEFAULT_CONFIG, store)
        print(f"[{i}/{len(specs)}] {spec.process} {spec.target_id} -> verdict={row.verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
