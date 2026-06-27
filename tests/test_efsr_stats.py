import pytest

from efsr.stats.efsr import compute_efsr, compute_efsr_from_rows, wilson_interval


def test_wilson_interval_matches_worked_example():
    # Section: "A worked example" -- EFSR=9/60=0.15, 95% CI roughly 8%-26%.
    lo, hi = wilson_interval(0.15, 60)
    assert lo == pytest.approx(0.0810, abs=1e-3)
    assert hi == pytest.approx(0.2611, abs=1e-3)


def test_wilson_interval_zero_n_is_maximally_wide():
    assert wilson_interval(0.0, 0) == (0.0, 1.0)


def test_wilson_interval_rejects_out_of_range_p_hat():
    with pytest.raises(ValueError):
        wilson_interval(1.5, 10)


def test_compute_efsr_worked_example():
    result = compute_efsr(9, 60, process="LLM-A")
    assert result.p_hat == pytest.approx(0.15)
    assert result.diverge_count == 9
    assert result.denom == 60
    assert result.ci_low < 0.15 < result.ci_high


def test_compute_efsr_zero_denominator():
    result = compute_efsr(0, 0)
    assert result.p_hat == 0.0
    assert result.ci_low == 0.0
    assert result.ci_high == 1.0


def test_compute_efsr_rejects_diverge_greater_than_denom():
    with pytest.raises(ValueError):
        compute_efsr(10, 5)


def test_compute_efsr_rejects_negative_counts():
    with pytest.raises(ValueError):
        compute_efsr(-1, 5)


def _row(process, admitted, excluded, verdict):
    return {
        "process": process,
        "admitted": str(admitted),
        "excluded_nondeterministic": str(excluded),
        "verdict": verdict,
    }


def test_compute_efsr_from_rows_basic_partition():
    rows = [
        _row("LLM-A", True, False, "DIVERGE"),
        _row("LLM-A", True, False, "DIVERGE"),
        _row("LLM-A", True, False, "NO_DIFFERENCE"),
        _row("LLM-A", True, False, "NO_DIFFERENCE"),
        _row("LLM-A", False, False, "NOT_ADMITTED"),  # not in Pi(S)
        _row("LLM-A", True, True, "DIVERGE"),  # excluded a priori, not in Pi(S)
        _row("LLM-B", True, False, "DIVERGE"),  # different process, ignored
    ]
    result = compute_efsr_from_rows(rows, "LLM-A")
    assert result.denom == 4
    assert result.diverge_count == 2
    assert result.p_hat == pytest.approx(0.5)


def test_compute_efsr_from_rows_excludes_error_verdicts_with_warning():
    rows = [
        _row("LLM-A", True, False, "DIVERGE"),
        _row("LLM-A", True, False, "ERROR"),
    ]
    with pytest.warns(UserWarning, match="verdict=ERROR"):
        result = compute_efsr_from_rows(rows, "LLM-A")
    assert result.denom == 1
    assert result.diverge_count == 1
