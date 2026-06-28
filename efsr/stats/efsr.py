"""The formal model (Section IV, equations 1-3): EFSR and its Wilson interval.

    Pi(S)    = { T in T(S) : compile(T) AND tests(T) AND metric(T) }                 (1)
    EFSR(S)  = |{ T in Pi(S) : div(T) = DIVERGE }| / |Pi(S)|                          (2)
    Wilson 95% CI for p_hat = EFSR(S) over n = |Pi(S)|:
        ( p_hat + z^2/2n +/- z*sqrt[ p_hat(1-p_hat)/n + z^2/4n^2 ] ) / ( 1 + z^2/n )  (3)
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from efsr.config import PipelineConfig, DEFAULT_CONFIG


@dataclass
class EFSRResult:
    process: str
    diverge_count: int
    denom: int
    p_hat: float
    ci_low: float
    ci_high: float


def wilson_interval(p_hat: float, n: int, z: float = DEFAULT_CONFIG.wilson_z) -> tuple[float, float]:
    """Equation (3). Returns (ci_low, ci_high). n=0 -> (0.0, 1.0) (undefined, maximally wide)."""
    if n <= 0:
        return 0.0, 1.0
    if not (0.0 <= p_hat <= 1.0):
        raise ValueError(f"p_hat must be in [0, 1], got {p_hat}")

    denom = 1 + (z ** 2) / n
    centre = p_hat + (z ** 2) / (2 * n)
    half_width = z * math.sqrt((p_hat * (1 - p_hat)) / n + (z ** 2) / (4 * n ** 2))
    lo = (centre - half_width) / denom
    hi = (centre + half_width) / denom
    return max(0.0, lo), min(1.0, hi)


def compute_efsr(
    diverge_count: int, denom: int, process: str = "",
    config: PipelineConfig = DEFAULT_CONFIG,
) -> EFSRResult:
    """Equation (2) plus its Wilson interval.

    `denom` is |Pi(S)| -- protocol-passing AND not a priori excluded
    (Stage 5) transformations. `diverge_count` is the number of those with
    a confirmed DIVERGE verdict (Stage 8). Raises if diverge_count > denom,
    which would indicate a bookkeeping error upstream.
    """
    if denom < 0 or diverge_count < 0:
        raise ValueError("counts must be non-negative")
    if diverge_count > denom:
        raise ValueError(f"diverge_count ({diverge_count}) cannot exceed denom ({denom})")

    p_hat = diverge_count / denom if denom else 0.0
    ci_low, ci_high = wilson_interval(p_hat, denom, config.wilson_z)
    return EFSRResult(process=process, diverge_count=diverge_count, denom=denom,
                       p_hat=p_hat, ci_low=ci_low, ci_high=ci_high)


def compute_efsr_from_rows(rows: list[dict], process: str, config: PipelineConfig = DEFAULT_CONFIG) -> EFSRResult:
    """Compute EFSR(S) directly from ResultsStore rows for one process.

    Pi(S) membership = admitted == True AND retained == True AND
    excluded_nondeterministic == False. `retained` excludes the protocol-
    passing-but-not-selected siblings of an LLM strategy's 3x sampling
    (Section III-D); it defaults to True for rows/processes that never
    went through that selection step (JDeodorant, Human, or rows written
    before this field existed).
    DIVERGE membership = verdict == "DIVERGE" (Stage 8-confirmed only).
    Rows with verdict == "ERROR" are excluded from the denominator with a
    warning -- they represent transformations the pipeline could not
    actually subject to differential testing (e.g. missing tool), not a
    measured NO_DIFFERENCE outcome, and silently treating them as
    non-divergent would understate EFSR.
    """
    process_rows = [r for r in rows if r.get("process") == process]
    pi_s = [
        r for r in process_rows
        if _to_bool(r.get("admitted")) and _retained(r) and not _to_bool(r.get("excluded_nondeterministic"))
    ]
    usable = [r for r in pi_s if r.get("verdict") != "ERROR"]
    error_count = len(pi_s) - len(usable)
    diverge_count = sum(1 for r in usable if r.get("verdict") == "DIVERGE")

    result = compute_efsr(diverge_count, len(usable), process=process, config=config)
    if error_count:
        import warnings
        warnings.warn(
            f"{error_count} Pi(S) transformation(s) for process {process!r} had verdict=ERROR "
            f"(differential testing could not run) and were excluded from the EFSR denominator.",
            stacklevel=2,
        )
    return result


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes")


def _retained(row: dict) -> bool:
    """`retained` defaults to True when absent/empty (see compute_efsr_from_rows)."""
    value = row.get("retained", "")
    if value in (None, ""):
        return True
    return _to_bool(value)
