import pytest

from efsr.metrics.types import StructuralMetrics
from efsr.protocol import ProtocolResult, RefactoringType
from efsr.results import CheckStatus
from efsr.selection import (
    SelectionCandidate,
    select_retained_output,
    target_metric_value,
    textual_diff_size,
)


def _result(admitted: bool, cc=None, wmc=None, ce=None) -> ProtocolResult:
    return ProtocolResult(
        compile_status=CheckStatus.PASS, tests_status=CheckStatus.PASS,
        metric_status=CheckStatus.PASS if admitted else CheckStatus.FAIL,
        admitted=admitted,
        post_metrics=StructuralMetrics(cc=cc, wmc=wmc, ce=ce) if admitted else None,
    )


def test_target_metric_value_method_level_uses_cc():
    assert target_metric_value(StructuralMetrics(cc=4), RefactoringType.EXTRACT_METHOD) == 4


def test_target_metric_value_class_level_uses_wmc():
    assert target_metric_value(StructuralMetrics(wmc=12), RefactoringType.EXTRACT_CLASS) == 12


def test_target_metric_value_missing_field_raises():
    with pytest.raises(ValueError):
        target_metric_value(StructuralMetrics(cc=None), RefactoringType.EXTRACT_METHOD)


def test_textual_diff_size_counts_changed_lines():
    original = "a\nb\nc\n"
    modified = "a\nX\nc\nd\n"
    # "b" removed, "X" and "d" added -> 3 changed lines.
    assert textual_diff_size(original, modified) == 3


def test_textual_diff_size_identical_text_is_zero():
    assert textual_diff_size("a\nb\n", "a\nb\n") == 0


def test_select_retained_output_picks_lowest_metric():
    candidates = [
        SelectionCandidate(0, "class A { void m() { /* v0 */ } }", _result(True, cc=5)),
        SelectionCandidate(1, "class A { void m() { /* v1 */ } }", _result(True, cc=2)),
        SelectionCandidate(2, "class A { void m() { /* v2 */ } }", _result(True, cc=8)),
    ]
    retained = select_retained_output(candidates, RefactoringType.EXTRACT_METHOD, "class A {}")
    assert retained.generation_index == 1


def test_select_retained_output_ties_broken_by_smallest_diff():
    original = "class A {\n  void m() {}\n}\n"
    candidates = [
        SelectionCandidate(0, "class A {\n  void m() {}\n  void n() {}\n  void o() {}\n}\n", _result(True, cc=3)),
        SelectionCandidate(1, "class A {\n  void m() {}\n  void n() {}\n}\n", _result(True, cc=3)),
    ]
    retained = select_retained_output(candidates, RefactoringType.EXTRACT_METHOD, original)
    assert retained.generation_index == 1  # smaller diff wins the tie


def test_select_retained_output_ignores_protocol_failing_candidates():
    candidates = [
        SelectionCandidate(0, "class A { /* failed */ }", _result(False)),
        SelectionCandidate(1, "class A { /* passed */ }", _result(True, cc=3)),
    ]
    retained = select_retained_output(candidates, RefactoringType.EXTRACT_METHOD, "class A {}")
    assert retained.generation_index == 1


def test_select_retained_output_returns_none_when_all_fail_protocol():
    candidates = [
        SelectionCandidate(0, "class A {}", _result(False)),
        SelectionCandidate(1, "class A {}", _result(False)),
    ]
    assert select_retained_output(candidates, RefactoringType.EXTRACT_METHOD, "class A {}") is None
