"""RQ2 (Section III-I): between-process EFSR comparisons.

Per-project EFSR rates are compared pairwise across processes with the
Mann-Whitney U test (non-parametric, appropriate for small per-project
sample counts and proportions that may not be normally distributed),
Bonferroni-corrected for the number of pairwise comparisons performed, and
accompanied by Cliff's delta as the effect size.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import numpy as np
from scipy import stats

from efsr.config import PipelineConfig, DEFAULT_CONFIG


@dataclass
class PairwiseComparison:
    process_a: str
    process_b: str
    statistic: float
    p_value: float
    p_value_bonferroni: float
    cliffs_delta: float
    significant: bool


def cliffs_delta(a: list[float], b: list[float]) -> float:
    """Cliff's delta effect size: P(a > b) - P(a < b), in [-1, 1]."""
    a_arr, b_arr = np.asarray(a), np.asarray(b)
    greater = sum(x > y for x in a_arr for y in b_arr)
    less = sum(x < y for x in a_arr for y in b_arr)
    n = len(a_arr) * len(b_arr)
    return (greater - less) / n if n else 0.0


def per_project_rates(rows: list[dict], process: str, project_key: str = "target_id") -> dict[str, float]:
    """EFSR per project for one process, keyed by a project identifier
    derived from `target_id` (assumed of the form "<project>:<rest>").
    """
    from efsr.stats.efsr import compute_efsr, _to_bool

    by_project: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("process") != process:
            continue
        project = str(r.get(project_key, "")).split(":")[0]
        by_project.setdefault(project, []).append(r)

    rates: dict[str, float] = {}
    for project, project_rows in by_project.items():
        pi_s = [r for r in project_rows if _to_bool(r.get("admitted")) and not _to_bool(r.get("excluded_nondeterministic"))]
        usable = [r for r in pi_s if r.get("verdict") != "ERROR"]
        if not usable:
            continue
        diverge = sum(1 for r in usable if r.get("verdict") == "DIVERGE")
        rates[project] = compute_efsr(diverge, len(usable)).p_hat
    return rates


def compare_processes(
    rows: list[dict],
    processes: list[str],
    config: PipelineConfig = DEFAULT_CONFIG,
) -> list[PairwiseComparison]:
    """All pairwise Mann-Whitney U comparisons of per-project EFSR rates,
    with Bonferroni correction across the number of pairs tested.
    """
    rates_by_process = {p: list(per_project_rates(rows, p).values()) for p in processes}
    pairs = list(combinations(processes, 2))
    n_comparisons = len(pairs)
    results = []
    for proc_a, proc_b in pairs:
        a, b = rates_by_process[proc_a], rates_by_process[proc_b]
        if len(a) < 1 or len(b) < 1:
            results.append(PairwiseComparison(proc_a, proc_b, float("nan"), float("nan"),
                                               float("nan"), float("nan"), False))
            continue
        statistic, p_value = stats.mannwhitneyu(a, b, alternative="two-sided")
        p_bonf = min(1.0, p_value * n_comparisons) if n_comparisons else p_value
        delta = cliffs_delta(a, b)
        results.append(PairwiseComparison(
            process_a=proc_a, process_b=proc_b, statistic=float(statistic), p_value=float(p_value),
            p_value_bonferroni=float(p_bonf), cliffs_delta=delta,
            significant=p_bonf < config.bonferroni_alpha,
        ))
    return results
