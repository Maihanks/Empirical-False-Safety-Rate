"""Section III-D: the retained-output selection rule.

"Each LLM strategy is sampled under temperature-zero decoding and
generated three times; the retained output is selected by an explicit,
pre-registered rule: among the three generations that satisfy the
three-check protocol, the one minimising the post-transformation target
metric is kept, with ties broken by smallest textual diff. Generations
failing the protocol are recorded but excluded from EFSR's denominator."

This module implements exactly that rule. It does not re-run the protocol
itself (efsr.protocol does that); it consumes already-computed
ProtocolResults for a batch of generations of the *same* target and picks
the one to carry forward into Stage 5-9.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Optional

from efsr.metrics.types import StructuralMetrics
from efsr.protocol import ProtocolResult, RefactoringType, _CLASS_LEVEL_TYPES, _METHOD_LEVEL_TYPES


@dataclass
class SelectionCandidate:
    generation_index: int
    modified_source: str
    protocol_result: ProtocolResult


def target_metric_value(metrics: StructuralMetrics, refactoring_type: RefactoringType) -> float:
    """The single "post-transformation target metric" a generation is
    asked to minimise (Section III-B): CC for method-level refactorings,
    WMC for class-level ones.
    """
    if refactoring_type in _METHOD_LEVEL_TYPES:
        if metrics.cc is None:
            raise ValueError("cc required to rank a method-level generation")
        return metrics.cc
    if refactoring_type in _CLASS_LEVEL_TYPES:
        if metrics.wmc is None:
            raise ValueError("wmc required to rank a class-level generation")
        return metrics.wmc
    raise ValueError(f"no target-metric rule for refactoring type {refactoring_type!r}")


def textual_diff_size(original_source: str, modified_source: str) -> int:
    """Number of changed (added/removed) lines between two source texts,
    used as the tie-break ("smallest textual diff") when two protocol-
    passing generations achieve the same target-metric value.
    """
    diff = difflib.unified_diff(original_source.splitlines(), modified_source.splitlines(), lineterm="")
    return sum(1 for line in diff if line.startswith(("+", "-")) and not line.startswith(("+++", "---")))


def select_retained_output(
    candidates: list[SelectionCandidate],
    refactoring_type: RefactoringType,
    original_source: str,
) -> Optional[SelectionCandidate]:
    """Pick the retained generation among protocol-passing candidates.

    Returns None if no candidate satisfies the three-check protocol --
    callers should record all candidates (Stage 1-4 status preserved on
    each) but admit none of them to Pi(S).
    """
    admitted = [c for c in candidates if c.protocol_result.admitted]
    if not admitted:
        return None

    def _key(candidate: SelectionCandidate) -> tuple[float, int]:
        metric_value = target_metric_value(candidate.protocol_result.post_metrics, refactoring_type)
        diff_size = textual_diff_size(original_source, candidate.modified_source)
        return (metric_value, diff_size)

    return min(admitted, key=_key)
