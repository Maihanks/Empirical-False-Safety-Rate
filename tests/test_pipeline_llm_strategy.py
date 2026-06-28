"""Tests the Section III-D wiring in efsr.pipeline.run_llm_strategy_for_target:
sample N generations, admit each, apply the retained-output rule, and
continue Stage 5-9 only for the winner. Admission and Stage 5-9 are
monkeypatched so this test exercises the *orchestration*, not Maven/JDK
behaviour already covered by test_protocol.py and the dual-harness tests.
"""
from pathlib import Path

import efsr.pipeline as pipeline_module
from efsr.generation import GeneratedTransformation
from efsr.metrics.types import StructuralMetrics
from efsr.protocol import ProtocolResult, RefactoringType
from efsr.results import CheckStatus, ResultRow, ResultsStore, Verdict
from efsr.corpus import SmellCandidate


class _FakeGenerator:
    process_name = "LLM-A"

    def generate_samples(self, target, original_source, n=3):
        return [
            GeneratedTransformation(process=self.process_name, target=target, generation_index=i,
                                     modified_source=f"class Foo {{ /* gen{i} */ }}")
            for i in range(n)
        ]


def _target():
    return SmellCandidate(
        source_file=Path("Foo.java"), class_name="org.example.Foo",
        refactoring_type=RefactoringType.EXTRACT_METHOD, method_name="longMethod",
    )


def _make_admission_stub(verdicts_by_index):
    """verdicts_by_index: {generation_index: ("admitted", cc) | ("not_admitted", None)}"""

    def fake_admit_transformation(spec, config):
        kind, cc = verdicts_by_index[spec.generation_index]
        if kind == "admitted":
            result = ProtocolResult(
                compile_status=CheckStatus.PASS, tests_status=CheckStatus.PASS, metric_status=CheckStatus.PASS,
                admitted=True, pre_metrics=StructuralMetrics(cc=10), post_metrics=StructuralMetrics(cc=cc),
            )
        else:
            result = ProtocolResult(
                compile_status=CheckStatus.PASS, tests_status=CheckStatus.PASS, metric_status=CheckStatus.FAIL,
                admitted=False,
            )
        return pipeline_module.AdmissionOutcome(
            spec=spec, result=result, pre_metrics=StructuralMetrics(cc=10), error=None,
        )

    return fake_admit_transformation


def test_run_llm_strategy_retains_lowest_metric_and_continues_only_for_it(tmp_path, monkeypatch):
    original_project = tmp_path / "original"
    original_project.mkdir()
    (original_project / "Foo.java").write_text("class Foo { void longMethod() {} }")

    monkeypatch.setattr(
        pipeline_module, "admit_transformation",
        _make_admission_stub({0: ("admitted", 5), 1: ("admitted", 2), 2: ("not_admitted", None)}),
    )

    continue_calls = []

    def fake_continue(spec, config, pre_metrics, result, retained):
        continue_calls.append(spec.generation_index)
        return ResultRow(
            process=spec.process, target_id=spec.target_id, refactoring_type=spec.refactoring_type.value,
            generation_index=spec.generation_index, admitted=True, retained=retained,
            verdict=Verdict.DIVERGE.value,
        )

    monkeypatch.setattr(pipeline_module, "_continue_from_admitted", fake_continue)

    store = ResultsStore(tmp_path / "out.csv")
    rows = pipeline_module.run_llm_strategy_for_target(
        generator=_FakeGenerator(), target=_target(), original_source="class Foo { void longMethod() {} }",
        original_project_dir=original_project, target_relative_path="Foo.java",
        process_target_id="org.example.Foo#longMethod", work_dir=tmp_path / "work",
        store=store,
    )

    assert continue_calls == [1]  # only the retained (lowest-cc) generation continues to Stage 5-9

    by_index = {r.generation_index: r for r in rows}
    assert by_index[0].verdict == Verdict.NOT_RETAINED.value
    assert by_index[0].retained is False
    assert by_index[0].admitted is True

    assert by_index[1].verdict == Verdict.DIVERGE.value
    assert by_index[1].retained is True

    assert by_index[2].verdict == Verdict.NOT_ADMITTED.value
    assert by_index[2].admitted is False

    persisted = store.read_all()
    assert len(persisted) == 3


def test_run_llm_strategy_writes_no_continuation_row_when_all_fail_protocol(tmp_path, monkeypatch):
    original_project = tmp_path / "original"
    original_project.mkdir()
    (original_project / "Foo.java").write_text("class Foo {}")

    monkeypatch.setattr(
        pipeline_module, "admit_transformation",
        _make_admission_stub({0: ("not_admitted", None), 1: ("not_admitted", None), 2: ("not_admitted", None)}),
    )
    continue_calls = []
    monkeypatch.setattr(
        pipeline_module, "_continue_from_admitted",
        lambda *a, **k: continue_calls.append(1),
    )

    store = ResultsStore(tmp_path / "out.csv")
    rows = pipeline_module.run_llm_strategy_for_target(
        generator=_FakeGenerator(), target=_target(), original_source="class Foo {}",
        original_project_dir=original_project, target_relative_path="Foo.java",
        process_target_id="org.example.Foo#longMethod", work_dir=tmp_path / "work",
        store=store,
    )

    assert continue_calls == []
    assert all(r.verdict == Verdict.NOT_ADMITTED.value for r in rows)
    assert len(rows) == 3


def test_run_llm_strategy_materialises_a_distinct_project_copy_per_sample(tmp_path, monkeypatch):
    original_project = tmp_path / "original"
    original_project.mkdir()
    (original_project / "Foo.java").write_text("class Foo {}")

    seen_modified_sources = []

    def fake_admit_transformation(spec, config):
        seen_modified_sources.append(Path(spec.modified_source_file).read_text())
        result = ProtocolResult(
            compile_status=CheckStatus.PASS, tests_status=CheckStatus.PASS, metric_status=CheckStatus.FAIL,
            admitted=False,
        )
        return pipeline_module.AdmissionOutcome(spec=spec, result=result, pre_metrics=StructuralMetrics(cc=1), error=None)

    monkeypatch.setattr(pipeline_module, "admit_transformation", fake_admit_transformation)

    pipeline_module.run_llm_strategy_for_target(
        generator=_FakeGenerator(), target=_target(), original_source="class Foo {}",
        original_project_dir=original_project, target_relative_path="Foo.java",
        process_target_id="org.example.Foo#longMethod", work_dir=tmp_path / "work",
        store=ResultsStore(tmp_path / "out.csv"),
    )

    assert seen_modified_sources == [
        "class Foo { /* gen0 */ }", "class Foo { /* gen1 */ }", "class Foo { /* gen2 */ }",
    ]
