from efsr.difftest.dual_harness import ChannelDiff
from efsr.difftest.junit_diff import CandidateDivergence, PerTestOutcome
from efsr.results import TaxonomyCategory
from efsr.taxonomy import classify_channel_diff, classify_junit_candidate


def _diff(return_d=False, exc_d=False, state_d=False, interaction_d=False):
    return ChannelDiff(
        rep=0, return_differs=return_d, exception_differs=exc_d, state_differs=state_d,
        interaction_differs=interaction_d,
        return_orig="a", return_mod="b" if return_d else "a",
        exc_orig=None, exc_mod="X" if exc_d else None,
        state_orig="s1", state_mod="s2" if state_d else "s1",
        interaction_orig="log(a)", interaction_mod="log(b)" if interaction_d else "log(a)",
    )


def test_classify_channel_diff_return_value_only():
    category, channel = classify_channel_diff(_diff(return_d=True))
    assert category == TaxonomyCategory.FUNCTIONAL
    assert channel == "return_value"


def test_classify_channel_diff_exception_takes_precedence_over_return_value():
    category, _ = classify_channel_diff(_diff(return_d=True, exc_d=True))
    assert category == TaxonomyCategory.EXCEPTIONAL


def test_classify_channel_diff_state_only():
    category, channel = classify_channel_diff(_diff(state_d=True))
    assert category == TaxonomyCategory.STATE
    assert channel == "state"


def test_classify_channel_diff_interaction_only():
    category, channel = classify_channel_diff(_diff(interaction_d=True))
    assert category == TaxonomyCategory.INTERFACE_API
    assert channel == "interaction"


def test_classify_channel_diff_interaction_takes_precedence_over_state():
    category, _ = classify_channel_diff(_diff(state_d=True, interaction_d=True))
    assert category == TaxonomyCategory.INTERFACE_API


def test_classify_channel_diff_return_value_takes_precedence_over_interaction():
    category, _ = classify_channel_diff(_diff(return_d=True, interaction_d=True))
    assert category == TaxonomyCategory.FUNCTIONAL


def test_classify_channel_diff_no_differences_is_out_of_taxonomy():
    category, channel = classify_channel_diff(_diff())
    assert category == TaxonomyCategory.OUT_OF_TAXONOMY
    assert channel == ""


def _outcome(passed, exc="", message=""):
    return PerTestOutcome(class_name="C", method_name="m", passed=passed, exception_class=exc, message=message)


def test_classify_junit_candidate_assertion_failure_is_functional():
    candidate = CandidateDivergence(
        test_key="C#m", reason="pass/fail disagreement",
        orig=_outcome(True), mod=_outcome(False, exc="java.lang.AssertionError"),
    )
    category, _ = classify_junit_candidate(candidate)
    assert category == TaxonomyCategory.FUNCTIONAL


def test_classify_junit_candidate_other_exception_is_exceptional():
    candidate = CandidateDivergence(
        test_key="C#m", reason="pass/fail disagreement",
        orig=_outcome(True), mod=_outcome(False, exc="java.lang.NullPointerException"),
    )
    category, _ = classify_junit_candidate(candidate)
    assert category == TaxonomyCategory.EXCEPTIONAL


def test_classify_junit_candidate_different_exceptions_on_both_failing_sides():
    candidate = CandidateDivergence(
        test_key="C#m", reason="different exception on failure",
        orig=_outcome(False, exc="java.lang.IllegalArgumentException"),
        mod=_outcome(False, exc="java.lang.NullPointerException"),
    )
    category, _ = classify_junit_candidate(candidate)
    assert category == TaxonomyCategory.EXCEPTIONAL


def test_classify_junit_candidate_one_sided_test_is_out_of_taxonomy():
    candidate = CandidateDivergence(test_key="C#m", reason="only one side", orig=_outcome(True), mod=None)
    category, reason = classify_junit_candidate(candidate)
    assert category == TaxonomyCategory.OUT_OF_TAXONOMY
    assert "only one side" in reason
