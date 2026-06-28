#!/usr/bin/env python3
"""Section III-D: drive one LLM strategy over a corpus (scripts/build_corpus.py
output), 3x-sampling each target and applying the retained-output rule.

The model client is intentionally pluggable: pass `--complete-fn
module.path:function_name` pointing at a zero-dependency callable of the
shape `def complete(prompt: str) -> str`. This script has no SDK of its
own to keep efsr vendor-agnostic; wire up whatever client the actual study
uses behind that one function.

Usage:
  uv run python scripts/run_llm_strategy.py \
      --corpus corpus.json --original-project /path/to/checkout \
      --strategy "LLM-A" --complete-fn mymodule:complete
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from efsr.config import DEFAULT_CONFIG
from efsr.corpus import SmellCandidate
from efsr.generation import LLMRefactoringGenerator
from efsr.pipeline import run_llm_strategy_for_target
from efsr.protocol import RefactoringType
from efsr.results import ResultsStore


def load_complete_fn(spec: str):
    module_name, _, attr = spec.partition(":")
    if not attr:
        raise ValueError(f"--complete-fn must be 'module.path:function_name', got {spec!r}")
    module = importlib.import_module(module_name)
    return getattr(module, attr)


def load_corpus(path: Path) -> list[SmellCandidate]:
    records = json.loads(path.read_text())
    targets = []
    for r in records:
        targets.append(SmellCandidate(
            source_file=Path(r["source_file"]), class_name=r["class_name"],
            refactoring_type=RefactoringType(r["refactoring_type"]),
            method_name=r.get("method_name"), cc=r.get("cc"), loc=r.get("loc"),
            wmc=r.get("wmc"), nom=r.get("nom"), line_coverage=r.get("line_coverage"),
        ))
    return targets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--original-project", type=Path, required=True)
    parser.add_argument("--strategy", required=True,
                         choices=["LLM-A", "LLM-B", "LLM-A (chain-of-thought)"])
    parser.add_argument("--complete-fn", required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_CONFIG.results_dir / "work")
    args = parser.parse_args()

    complete_fn = load_complete_fn(args.complete_fn)
    targets = load_corpus(args.corpus)
    if args.limit:
        targets = targets[: args.limit]

    chain_of_thought = args.strategy == "LLM-A (chain-of-thought)"
    generator = LLMRefactoringGenerator(
        process_name=args.strategy, complete_fn=complete_fn, chain_of_thought=chain_of_thought,
        temperature=DEFAULT_CONFIG.llm_temperature,
    )

    store = ResultsStore(DEFAULT_CONFIG.results_csv)
    print(f"Running {args.strategy} over {len(targets)} corpus target(s); "
          f"writing to {DEFAULT_CONFIG.results_csv}")

    for i, target in enumerate(targets, start=1):
        original_source = Path(target.source_file).read_text()
        relative_path = Path(target.source_file).resolve().relative_to(args.original_project.resolve())
        target_id = target.class_name + (f"#{target.method_name}" if target.method_name else "")

        rows = run_llm_strategy_for_target(
            generator=generator, target=target, original_source=original_source,
            original_project_dir=args.original_project, target_relative_path=str(relative_path),
            process_target_id=target_id, work_dir=args.work_dir, config=DEFAULT_CONFIG, store=store,
        )
        verdicts = [r.verdict for r in rows]
        print(f"[{i}/{len(targets)}] {target_id} -> {verdicts}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
