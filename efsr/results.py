"""Stage 9: results store.

One CSV row per transformation, holding the three-check outcomes, the
Pi(S)-admission decision, the pre-transformation structural metrics, the
differential-testing verdict, and the divergence taxonomy category. This
file is the single source of truth that the stats module (efsr/stats/)
reads from to compute Table I / Table II of the paper.
"""
from __future__ import annotations

import csv
import dataclasses
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    ERROR = "ERROR"


class Verdict(str, Enum):
    NOT_ADMITTED = "NOT_ADMITTED"      # failed compile/tests/metric -> never enters Pi(S)
    EXCLUDED = "EXCLUDED"               # admitted but excluded a priori (Stage 5, non-determinism)
    DIVERGE = "DIVERGE"                 # confirmed behavioural divergence (false-safe instance)
    NO_DIFFERENCE = "NO_DIFFERENCE"      # no divergence detected within budget (not proven equivalent)
    ERROR = "ERROR"                      # pipeline/tooling error distinct from a real verdict


class TaxonomyCategory(str, Enum):
    FUNCTIONAL = "Functional"
    EXCEPTIONAL = "Exceptional"
    STATE = "State"
    INTERFACE_API = "Interface/API"
    OUT_OF_TAXONOMY = "OutOfTaxonomy"
    NONE = "None"


# Column order is fixed so the CSV schema is stable across runs.
FIELDNAMES = [
    "timestamp",
    "process",
    "target_id",
    "refactoring_type",
    "generation_index",
    "compile_status",
    "tests_status",
    "metric_status",
    "admitted",
    "excluded_nondeterministic",
    "exclusion_reason",
    "cc", "wmc", "ce", "cbo", "rfc", "lcom", "dit", "loc",
    "generation_budget_seconds",
    "generation_seed",
    "evosuite_candidates",
    "randoop_candidates",
    "candidate_divergences",
    "replay_repetitions",
    "verdict",
    "taxonomy_category",
    "divergence_channel",
    "notes",
]


@dataclass
class ResultRow:
    process: str
    target_id: str
    refactoring_type: str
    generation_index: int = 0

    compile_status: str = CheckStatus.SKIP.value
    tests_status: str = CheckStatus.SKIP.value
    metric_status: str = CheckStatus.SKIP.value
    admitted: bool = False

    excluded_nondeterministic: bool = False
    exclusion_reason: str = ""

    cc: Optional[float] = None
    wmc: Optional[float] = None
    ce: Optional[float] = None
    cbo: Optional[float] = None
    rfc: Optional[float] = None
    lcom: Optional[float] = None
    dit: Optional[float] = None
    loc: Optional[float] = None

    generation_budget_seconds: Optional[int] = None
    generation_seed: Optional[int] = None
    evosuite_candidates: int = 0
    randoop_candidates: int = 0
    candidate_divergences: int = 0
    replay_repetitions: int = 0

    verdict: str = Verdict.NOT_ADMITTED.value
    taxonomy_category: str = TaxonomyCategory.NONE.value
    divergence_channel: str = ""
    notes: str = ""

    timestamp: Optional[str] = None  # set in __post_init__ if left unspecified

    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def to_row(self) -> dict:
        d = dataclasses.asdict(self)
        return {k: ("" if v is None else v) for k, v in d.items()}


class ResultsStore:
    """Append-only CSV store, one row per transformation (Stage 9)."""

    def __init__(self, csv_path: Path):
        self.csv_path = Path(csv_path)
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.csv_path.exists():
            with self.csv_path.open("w", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
                writer.writeheader()

    def append(self, row: ResultRow) -> None:
        with self.csv_path.open("a", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
            writer.writerow(row.to_row())

    def read_all(self) -> list[dict]:
        if not self.csv_path.exists():
            return []
        with self.csv_path.open(newline="") as fh:
            return list(csv.DictReader(fh))
