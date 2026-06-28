"""Section III-I: sample-size / power planning for EFSR estimation.

"A sample-size and power consideration based on the pilot divergence rate
determines the minimum number of protocol-passing instances required per
process; the target corpus size is set accordingly, and any process not
reaching it is reported with interval estimates rather than hypothesis
tests."

This module answers two distinct questions:

1. How many protocol-passing transformations |Pi(S)| does a process need
   so that its EFSR's Wilson interval is no wider than a target margin of
   error, given a pilot estimate of the divergence rate? (estimation
   precision -- the primary question the paper text describes.)
2. How many *per-project* observations are needed for the RQ2 between-
   process comparison (Mann-Whitney U) to have a target power at a given
   effect size? (comparison power -- a secondary, standard power
   calculation, included so a target corpus size can also be justified
   for the hypothesis tests in Section III-I / RQ2.)
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import stats as scipy_stats

from efsr.config import PipelineConfig, DEFAULT_CONFIG
from efsr.stats.efsr import wilson_interval


@dataclass
class SampleSizeResult:
    pilot_p_hat: float
    target_half_width: float
    required_n: int
    achieved_half_width: float


def required_sample_size_for_efsr_precision(
    pilot_p_hat: float,
    target_half_width: float,
    config: PipelineConfig = DEFAULT_CONFIG,
    max_n: int = 1_000_000,
) -> SampleSizeResult:
    """Smallest n such that the Wilson 95% half-width at `pilot_p_hat` is
    <= `target_half_width`.

    Searches directly against `wilson_interval` (rather than the closed-
    form normal-approximation formula n = z^2 p(1-p) / E^2) so the
    requirement is internally consistent with the interval this codebase
    actually reports in Table I.
    """
    if not (0.0 <= pilot_p_hat <= 1.0):
        raise ValueError(f"pilot_p_hat must be in [0, 1], got {pilot_p_hat}")
    if target_half_width <= 0:
        raise ValueError("target_half_width must be positive")

    lo, hi = 1, max_n
    while lo < hi:
        mid = (lo + hi) // 2
        ci_low, ci_high = wilson_interval(pilot_p_hat, mid, config.wilson_z)
        half_width = (ci_high - ci_low) / 2
        if half_width <= target_half_width:
            hi = mid
        else:
            lo = mid + 1

    ci_low, ci_high = wilson_interval(pilot_p_hat, lo, config.wilson_z)
    achieved = (ci_high - ci_low) / 2
    if achieved > target_half_width:
        raise ValueError(
            f"target_half_width={target_half_width} not achievable within max_n={max_n} "
            f"(best achieved: {achieved:.4f} at n={lo})"
        )
    return SampleSizeResult(
        pilot_p_hat=pilot_p_hat, target_half_width=target_half_width,
        required_n=lo, achieved_half_width=achieved,
    )


@dataclass
class ComparisonPowerResult:
    effect_size: float
    power_target: float
    alpha: float
    required_n_per_group: int


def required_n_for_mannwhitney_power(
    effect_size: float,
    power_target: float = 0.8,
    alpha: float = 0.05,
    n_simulations: int = 2000,
    max_n_per_group: int = 500,
    random_state: int = 0,
) -> ComparisonPowerResult:
    """Smallest per-group n such that a Mann-Whitney U test attains the
    target power against a Cliff's-delta-style location shift, estimated
    by simulation (no closed-form power formula exists for the rank-sum
    test in general).

    `effect_size` is interpreted as a standardised mean shift between two
    otherwise-identical Beta-distributed per-project-rate populations
    (proportions live in [0, 1], so a normal location-shift model is a
    poor fit); using a paired Monte Carlo simulation avoids assuming
    normality of the per-project EFSR rates that Section III-I's
    non-parametric test is chosen specifically to avoid.
    """
    if not (0 < power_target < 1):
        raise ValueError("power_target must be in (0, 1)")
    rng = np.random.default_rng(random_state)

    def _simulated_power(n: int) -> float:
        rejections = 0
        for _ in range(n_simulations):
            a = rng.beta(2, 2, size=n)
            b = np.clip(rng.beta(2, 2, size=n) + effect_size, 0.0, 1.0)
            _, p_value = scipy_stats.mannwhitneyu(a, b, alternative="two-sided")
            if p_value < alpha:
                rejections += 1
        return rejections / n_simulations

    for n in range(2, max_n_per_group + 1):
        if _simulated_power(n) >= power_target:
            return ComparisonPowerResult(effect_size, power_target, alpha, n)
    raise ValueError(
        f"target power {power_target} not reached by n={max_n_per_group} per group "
        f"at effect_size={effect_size}; increase max_n_per_group or reduce the target."
    )
