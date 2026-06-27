from pathlib import Path

import pytest

import efsr.protocol as protocol_module
from efsr.build_runner import CompileResult, TestResult as MavenTestResult
from efsr.metrics.types import StructuralMetrics
from efsr.protocol import (
    RefactoringType,
    ThreeCheckProtocol,
    TransformationSpec,
    evaluate_metric,
)
from efsr.results import CheckStatus


# ---- evaluate_metric (Stage 3 / Section III-B) -----------------------------

def test_extract_method_metric_requires_strict_cc_reduction():
    pre = StructuralMetrics(cc=10)
    assert evaluate_metric(pre, StructuralMetrics(cc=5), RefactoringType.EXTRACT_METHOD) is True
    assert evaluate_metric(pre, StructuralMetrics(cc=10), RefactoringType.EXTRACT_METHOD) is False
    assert evaluate_metric(pre, StructuralMetrics(cc=11), RefactoringType.EXTRACT_METHOD) is False


def test_extract_method_metric_requires_cc_present():
    with pytest.raises(ValueError):
        evaluate_metric(StructuralMetrics(cc=None), StructuralMetrics(cc=5), RefactoringType.EXTRACT_METHOD)


def test_extract_class_metric_requires_wmc_decrease_and_ce_non_increase():
    pre = StructuralMetrics(wmc=20, ce=5)
    assert evaluate_metric(pre, StructuralMetrics(wmc=15, ce=5), RefactoringType.EXTRACT_CLASS) is True
    assert evaluate_metric(pre, StructuralMetrics(wmc=15, ce=4), RefactoringType.EXTRACT_CLASS) is True
    assert evaluate_metric(pre, StructuralMetrics(wmc=15, ce=6), RefactoringType.EXTRACT_CLASS) is False
    assert evaluate_metric(pre, StructuralMetrics(wmc=20, ce=5), RefactoringType.EXTRACT_CLASS) is False


def test_unknown_refactoring_type_raises():
    with pytest.raises(ValueError):
        evaluate_metric(StructuralMetrics(cc=1), StructuralMetrics(cc=1), "NotARealType")


# ---- TransformationSpec convenience properties -----------------------------

def test_transformation_spec_classpaths_and_simple_name(tmp_path):
    spec = TransformationSpec(
        process="LLM-A", target_id="t", refactoring_type=RefactoringType.EXTRACT_METHOD,
        original_project_dir=tmp_path / "orig", modified_project_dir=tmp_path / "mod",
        original_source_file=tmp_path / "orig" / "A.java", modified_source_file=tmp_path / "mod" / "A.java",
        class_name="org.example.Foo", method_name="bar",
    )
    assert spec.original_classpath == str(tmp_path / "orig" / "target" / "classes")
    assert spec.modified_classpath == str(tmp_path / "mod" / "target" / "classes")
    assert spec.simple_class_name == "Foo"


# ---- ThreeCheckProtocol.run (Stage 1-4) ------------------------------------

class _FakeMavenRunner:
    def __init__(self, project_dir, config=None, compile_passed=True, tests_passed=True):
        self._compile_passed = compile_passed
        self._tests_passed = tests_passed

    def compile(self):
        return CompileResult(passed=self._compile_passed, log="compile log")

    def run_tests(self):
        return MavenTestResult(passed=self._tests_passed, total=1,
                                failures=0 if self._tests_passed else 1, log="test log")


def _spec(tmp_path, refactoring_type=RefactoringType.EXTRACT_METHOD):
    return TransformationSpec(
        process="LLM-A", target_id="t", refactoring_type=refactoring_type,
        original_project_dir=tmp_path / "orig", modified_project_dir=tmp_path / "mod",
        original_source_file=tmp_path / "orig" / "A.java", modified_source_file=tmp_path / "mod" / "A.java",
        class_name="org.example.Foo", method_name="bar",
    )


def test_protocol_stops_at_compile_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(
        protocol_module, "MavenRunner",
        lambda project_dir, config: _FakeMavenRunner(project_dir, config, compile_passed=False),
    )
    result = ThreeCheckProtocol().run(_spec(tmp_path), StructuralMetrics(cc=10), StructuralMetrics(cc=5))
    assert result.compile_status == CheckStatus.FAIL
    assert result.tests_status == CheckStatus.SKIP
    assert result.metric_status == CheckStatus.SKIP
    assert result.admitted is False


def test_protocol_stops_at_test_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(
        protocol_module, "MavenRunner",
        lambda project_dir, config: _FakeMavenRunner(project_dir, config, tests_passed=False),
    )
    result = ThreeCheckProtocol().run(_spec(tmp_path), StructuralMetrics(cc=10), StructuralMetrics(cc=5))
    assert result.compile_status == CheckStatus.PASS
    assert result.tests_status == CheckStatus.FAIL
    assert result.metric_status == CheckStatus.SKIP
    assert result.admitted is False


def test_protocol_stops_at_metric_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(protocol_module, "MavenRunner", lambda project_dir, config: _FakeMavenRunner(project_dir, config))
    # post.cc == pre.cc -> metric(T) fails (no strict reduction).
    result = ThreeCheckProtocol().run(_spec(tmp_path), StructuralMetrics(cc=10), StructuralMetrics(cc=10))
    assert result.compile_status == CheckStatus.PASS
    assert result.tests_status == CheckStatus.PASS
    assert result.metric_status == CheckStatus.FAIL
    assert result.admitted is False


def test_protocol_admits_when_all_three_checks_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(protocol_module, "MavenRunner", lambda project_dir, config: _FakeMavenRunner(project_dir, config))
    result = ThreeCheckProtocol().run(_spec(tmp_path), StructuralMetrics(cc=10), StructuralMetrics(cc=5))
    assert result.compile_status == CheckStatus.PASS
    assert result.tests_status == CheckStatus.PASS
    assert result.metric_status == CheckStatus.PASS
    assert result.admitted is True
    assert result.pre_metrics.cc == 10
    assert result.post_metrics.cc == 5
