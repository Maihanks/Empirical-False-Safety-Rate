from efsr.difftest.junit_diff import (
    JUnitRunResult,
    PerTestOutcome,
    diff_results,
    discover_test_classes,
)


def test_discover_test_classes_reads_package_and_class_name(tmp_path):
    (tmp_path / "Foo_ESTest.java").write_text(
        "package org.example.gen;\n\npublic class Foo_ESTest {\n    @Test public void test0() {}\n}\n"
    )
    fqcns = discover_test_classes(tmp_path)
    assert fqcns == ["org.example.gen.Foo_ESTest"]


def test_discover_test_classes_handles_default_package(tmp_path):
    (tmp_path / "Bare.java").write_text("public class Bare {}\n")
    assert discover_test_classes(tmp_path) == ["Bare"]


def test_discover_test_classes_skips_files_without_public_class(tmp_path):
    (tmp_path / "Helper.java").write_text("class Helper {}\n")
    assert discover_test_classes(tmp_path) == []


def _outcome(passed, exc="", message=""):
    return PerTestOutcome(class_name="C", method_name="m", passed=passed, exception_class=exc, message=message)


def test_diff_results_flags_pass_fail_disagreement():
    orig = JUnitRunResult(outcomes={"C#m": _outcome(True)})
    mod = JUnitRunResult(outcomes={"C#m": _outcome(False, "java.lang.AssertionError")})
    candidates = diff_results(orig, mod)
    assert len(candidates) == 1
    assert candidates[0].test_key == "C#m"
    assert candidates[0].reason == "pass/fail disagreement"


def test_diff_results_flags_different_exceptions_on_double_failure():
    orig = JUnitRunResult(outcomes={"C#m": _outcome(False, "java.lang.NullPointerException")})
    mod = JUnitRunResult(outcomes={"C#m": _outcome(False, "java.lang.IllegalStateException")})
    candidates = diff_results(orig, mod)
    assert len(candidates) == 1
    assert candidates[0].reason == "different exception on failure"


def test_diff_results_agreement_produces_no_candidates():
    orig = JUnitRunResult(outcomes={"C#m": _outcome(True)})
    mod = JUnitRunResult(outcomes={"C#m": _outcome(True)})
    assert diff_results(orig, mod) == []


def test_diff_results_same_failure_type_is_not_a_candidate():
    orig = JUnitRunResult(outcomes={"C#m": _outcome(False, "java.lang.AssertionError")})
    mod = JUnitRunResult(outcomes={"C#m": _outcome(False, "java.lang.AssertionError")})
    assert diff_results(orig, mod) == []


def test_diff_results_test_present_on_only_one_side():
    orig = JUnitRunResult(outcomes={"C#m": _outcome(True)})
    mod = JUnitRunResult(outcomes={})
    candidates = diff_results(orig, mod)
    assert len(candidates) == 1
    assert candidates[0].mod is None
