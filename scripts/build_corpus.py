#!/usr/bin/env python3
"""Section III-C: build a refactoring-target corpus from a Java project
checkout plus a JaCoCo XML coverage report, and write it to a JSON file.

The output is a list of smell candidates (Long Method / Large Class),
each carrying enough information to seed a TransformationSpec once a
refactoring-producing process (efsr.generation) has acted on it.

Usage:
  uv run python scripts/build_corpus.py --project /path/to/checkout \
      --jacoco /path/to/jacoco.xml --out corpus.json
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from efsr.config import DEFAULT_CONFIG
from efsr.corpus import build_corpus


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--jacoco", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    candidates = build_corpus(args.project, args.jacoco, DEFAULT_CONFIG)
    records = []
    for c in candidates:
        record = dataclasses.asdict(c)
        record["source_file"] = str(c.source_file)
        record["refactoring_type"] = c.refactoring_type.value
        records.append(record)

    args.out.write_text(json.dumps(records, indent=2))
    print(f"Wrote {len(records)} corpus target(s) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
