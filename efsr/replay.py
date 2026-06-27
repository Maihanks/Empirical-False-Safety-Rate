"""Stage 8 (replay half): keep only deterministic candidate divergences.

A candidate divergence is confirmed as DIVERGE only if it reproduces on
every one of N replays. This is the second line of defence against
non-determinism, after the a priori exclusion in Stage 5 -- it catches
sources of flakiness the source-level screener could not see (e.g.
iteration order that happens to be stable on most runs, JIT-dependent
timing artefacts, etc.).
"""
from __future__ import annotations

from efsr.config import PipelineConfig, DEFAULT_CONFIG
from efsr.difftest.dual_harness import ChannelDiff
from efsr.difftest.junit_diff import (
    CandidateDivergence,
    diff_results,
    run_junit_suite,
)


def confirm_channel_diffs(diffs: list[ChannelDiff]) -> bool:
    """True iff every repetition of a dual-probe run shows the same divergence.

    `diffs` is the full list of per-repetition results for one probe (one
    call site), as returned by `run_dual_probe(..., repetitions=N)`. All N
    repetitions must show *some* divergence, and the set of differing
    channels must be identical across repetitions, for the candidate to be
    confirmed.
    """
    if not diffs:
        return False
    if not all(d.any_differs for d in diffs):
        return False
    first_channels = set(diffs[0].differing_channels)
    return all(set(d.differing_channels) == first_channels for d in diffs[1:])


def confirm_junit_candidate(
    candidate: CandidateDivergence,
    original_classpath: str,
    modified_classpath: str,
    test_class: str,
    repetitions: int,
    config: PipelineConfig = DEFAULT_CONFIG,
) -> bool:
    """Re-run the generated suite N times against both classpaths and check
    that this specific test's disagreement reproduces every time.
    """
    for _ in range(repetitions):
        orig_run = run_junit_suite(original_classpath, test_class, config)
        mod_run = run_junit_suite(modified_classpath, test_class, config)
        candidates = {c.test_key: c for c in diff_results(orig_run, mod_run)}
        if candidate.test_key not in candidates:
            return False
    return True
