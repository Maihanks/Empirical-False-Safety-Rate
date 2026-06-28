"""Stage 8 (classification half): map a confirmed divergence to the
four-category taxonomy of Section III-G.

    Functional     -- different return value for the same input.
    Exceptional    -- an exception added/removed/changed relative to P.
    State          -- different post-call field/observable state.
    Interface/API  -- different observable interaction with collaborators.

This module gives an automatic, best-effort first pass; the methodology
treats the actual category assignment as a judgement call that benefits
from a human reviewer looking only at the handful of tool-flagged
candidates (never searching by hand). Disagreement with this heuristic
should be resolved manually and recorded in the `notes` field of the
corresponding ResultRow.

Precedence when multiple channels differ in the same probe: exception
differences are reported first (a thrown/missing exception is the
strongest, least ambiguous signal), then return value, then interaction,
then state. The Interface/API category is produced automatically by the
dual-classloader probe (`efsr.difftest.dual_harness`) for collaborator
fields whose declared type is an interface -- DualRunner.java proxies
those fields to record each call made through them (Section III-G); a
collaborator held in a concrete-typed field is not instrumented and any
resulting behavioural difference is only visible via the State channel
instead. The JUnit-suite diff path (EvoSuite/Randoop-generated tests) has
no equivalent instrumentation, so Interface/API divergences are only
detected there if a human reviewer reclassifies a flagged candidate.
"""
from __future__ import annotations

from efsr.difftest.dual_harness import ChannelDiff
from efsr.difftest.junit_diff import CandidateDivergence
from efsr.results import TaxonomyCategory

_PRECEDENCE = ("exception", "return_value", "interaction", "state")
_CATEGORY_BY_CHANNEL = {
    "exception": TaxonomyCategory.EXCEPTIONAL,
    "return_value": TaxonomyCategory.FUNCTIONAL,
    "interaction": TaxonomyCategory.INTERFACE_API,
    "state": TaxonomyCategory.STATE,
}


def classify_channel_diff(diff: ChannelDiff) -> tuple[TaxonomyCategory, str]:
    """Classify a confirmed ChannelDiff (from the dual-classloader probe)."""
    channels = set(diff.differing_channels)
    for channel in _PRECEDENCE:
        if channel in channels:
            return _CATEGORY_BY_CHANNEL[channel], "+".join(diff.differing_channels)
    return TaxonomyCategory.OUT_OF_TAXONOMY, ""


def classify_junit_candidate(candidate: CandidateDivergence) -> tuple[TaxonomyCategory, str]:
    """Classify a confirmed CandidateDivergence (from the JUnit-suite diff path).

    Heuristic: a failure carrying java.lang.AssertionError (the standard
    JUnit assertion failure) on exactly one side is read as a functional
    (return-value) divergence, since the generated test's assertion is
    itself a comparison of expected vs. actual output. Any other exception
    type appearing on one side but not the other (or differing between two
    failing sides) is read as exceptional. A test present on only one side
    is reported out-of-taxonomy, since it indicates a generation/compile
    mismatch rather than a behavioural divergence proper, and is flagged
    for manual review.
    """
    if candidate.orig is None or candidate.mod is None:
        return TaxonomyCategory.OUT_OF_TAXONOMY, "test present on only one side"

    orig, mod = candidate.orig, candidate.mod
    if orig.passed != mod.passed:
        failing = mod if orig.passed else orig
        if failing.exception_class.endswith("AssertionError") or not failing.exception_class:
            return TaxonomyCategory.FUNCTIONAL, "pass/fail disagreement (assertion)"
        return TaxonomyCategory.EXCEPTIONAL, f"pass/fail disagreement ({failing.exception_class})"

    if orig.exception_class != mod.exception_class:
        return TaxonomyCategory.EXCEPTIONAL, f"{orig.exception_class} vs {mod.exception_class}"

    return TaxonomyCategory.OUT_OF_TAXONOMY, "unclassified disagreement"
