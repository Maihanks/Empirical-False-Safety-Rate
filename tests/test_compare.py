import pytest

from efsr.stats.compare import cliffs_delta, compare_processes, per_project_rates


def test_cliffs_delta_identical_distributions_is_zero():
    assert cliffs_delta([1, 2, 3], [1, 2, 3]) == pytest.approx(0.0)


def test_cliffs_delta_a_always_greater_is_one():
    assert cliffs_delta([10, 11, 12], [1, 2, 3]) == pytest.approx(1.0)


def test_cliffs_delta_a_always_less_is_minus_one():
    assert cliffs_delta([1, 2, 3], [10, 11, 12]) == pytest.approx(-1.0)


def _row(process, target_id, admitted, excluded, verdict):
    return {
        "process": process, "target_id": target_id,
        "admitted": str(admitted), "excluded_nondeterministic": str(excluded),
        "verdict": verdict,
    }


def test_per_project_rates_groups_by_project_prefix():
    rows = [
        _row("LLM-A", "proj1:Foo#a", True, False, "DIVERGE"),
        _row("LLM-A", "proj1:Bar#b", True, False, "NO_DIFFERENCE"),
        _row("LLM-A", "proj2:Baz#c", True, False, "DIVERGE"),
    ]
    rates = per_project_rates(rows, "LLM-A")
    assert rates["proj1"] == pytest.approx(0.5)
    assert rates["proj2"] == pytest.approx(1.0)


def test_compare_processes_returns_one_entry_per_pair():
    rows = []
    for proj in ("p1", "p2", "p3"):
        rows.append(_row("LLM-A", f"{proj}:X#a", True, False, "DIVERGE"))
        rows.append(_row("LLM-A", f"{proj}:Y#b", True, False, "NO_DIFFERENCE"))
        rows.append(_row("JDeodorant", f"{proj}:X#a", True, False, "NO_DIFFERENCE"))
        rows.append(_row("JDeodorant", f"{proj}:Y#b", True, False, "NO_DIFFERENCE"))
    comparisons = compare_processes(rows, ["LLM-A", "JDeodorant"])
    assert len(comparisons) == 1
    comp = comparisons[0]
    assert {comp.process_a, comp.process_b} == {"LLM-A", "JDeodorant"}
    assert 0.0 <= comp.p_value_bonferroni <= 1.0


def test_compare_processes_handles_empty_process_gracefully():
    rows = [_row("LLM-A", "p1:X#a", True, False, "DIVERGE")]
    comparisons = compare_processes(rows, ["LLM-A", "JDeodorant"])
    assert len(comparisons) == 1
    assert comparisons[0].significant is False
