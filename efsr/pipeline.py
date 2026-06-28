"""Stage 0-9 driver: orchestrates one transformation end-to-end.

This is the function the CLI scripts call once per (process, target,
generated-transformation) triple, looping over the whole corpus. Each
stage is delegated to its own module; this file only sequences them and
is responsible for translating outcomes into the one CSV row (Stage 9)
that `efsr.results.ResultsStore` persists.

Stage map:
  0    TransformationSpec construction (caller-provided)
  1-2  ThreeCheckProtocol.compile()/run_tests()   -> efsr.build_runner / efsr.protocol
  3-4  metric(T) + admission to Pi(S)              -> efsr.protocol
  5    non-determinism a priori exclusion          -> efsr.nondeterminism
  6    EvoSuiteR + Randoop generation               -> efsr.difftest.evosuite/randoop
  7    run generated suite(s) against both versions -> efsr.difftest.junit_diff
  8    replay, confirm, classify                    -> efsr.replay / efsr.taxonomy
  9    aggregate into one ResultRow                 -> efsr.results

`run_pipeline_for_transformation` runs Stage 0-9 for one already-decided
transformation (rule-based tool output, a mined human refactoring, or a
single already-selected LLM generation). `run_llm_strategy_for_target`
sits one level above it: it drives an LLM strategy's Section III-D
sampling (admit up to `llm_samples_per_target` generations, apply the
retained-output selection rule, continue Stage 5-9 only for the winner).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from efsr.config import PipelineConfig, DEFAULT_CONFIG
from efsr.corpus import SmellCandidate
from efsr.difftest import junit_diff
from efsr.difftest.evosuite import EvoSuiteUnavailable, run_regression_suite
from efsr.difftest.randoop import RandoopUnavailable, run_randoop
from efsr.generation import GeneratedTransformation, materialize_project_copy
from efsr.metrics.adapter import extract_metrics
from efsr.metrics.types import StructuralMetrics
from efsr.nondeterminism import screen_file
from efsr.protocol import ProtocolResult, ThreeCheckProtocol, TransformationSpec
from efsr.replay import confirm_junit_candidate
from efsr.results import CheckStatus, ResultRow, ResultsStore, TaxonomyCategory, Verdict
from efsr.selection import SelectionCandidate, select_retained_output
from efsr.taxonomy import classify_junit_candidate

logger = logging.getLogger(__name__)


@dataclass
class AdmissionOutcome:
    spec: TransformationSpec
    result: Optional[ProtocolResult]
    pre_metrics: Optional[StructuralMetrics]
    error: Optional[str]


def admit_transformation(spec: TransformationSpec, config: PipelineConfig = DEFAULT_CONFIG) -> AdmissionOutcome:
    """Stage 1-4 only: structural metrics + the three-check protocol.

    Split out from `run_pipeline_for_transformation` so the LLM-strategy
    orchestrator can run admission on several candidate generations of the
    same target before deciding (via efsr.selection) which one continues
    to Stage 5-9.
    """
    try:
        pre_metrics = extract_metrics(
            spec.original_source_file, Path(spec.original_project_dir) / "target" / "classes",
            spec.class_name, spec.method_name, config,
        )
        post_metrics = extract_metrics(
            spec.modified_source_file, Path(spec.modified_project_dir) / "target" / "classes",
            spec.class_name, spec.method_name, config,
        )
    except Exception as exc:  # metrics extraction failure blocks the whole admission decision
        return AdmissionOutcome(spec=spec, result=None, pre_metrics=None, error=f"metrics extraction failed: {exc}")

    protocol = ThreeCheckProtocol(config)
    result = protocol.run(spec, pre_metrics, post_metrics)
    return AdmissionOutcome(spec=spec, result=result, pre_metrics=pre_metrics, error=None)


def run_pipeline_for_transformation(
    spec: TransformationSpec,
    config: PipelineConfig = DEFAULT_CONFIG,
    store: Optional[ResultsStore] = None,
) -> ResultRow:
    outcome = admit_transformation(spec, config)

    if outcome.error:
        row = ResultRow(
            process=spec.process, target_id=spec.target_id,
            refactoring_type=spec.refactoring_type.value, generation_index=spec.generation_index,
            compile_status=CheckStatus.ERROR.value, tests_status=CheckStatus.SKIP.value,
            metric_status=CheckStatus.ERROR.value, admitted=False, retained=False,
            verdict=Verdict.ERROR.value, notes=outcome.error,
        )
        _store(store, row, config)
        return row

    result = outcome.result
    if not result.admitted:
        row = _not_admitted_row(spec, result, outcome.pre_metrics)
        _store(store, row, config)
        return row

    row = _continue_from_admitted(spec, config, outcome.pre_metrics, result, retained=True)
    _store(store, row, config)
    return row


def run_llm_strategy_for_target(
    generator,
    target: SmellCandidate,
    original_source: str,
    original_project_dir: Path,
    target_relative_path: str,
    process_target_id: str,
    work_dir: Path,
    config: PipelineConfig = DEFAULT_CONFIG,
    store: Optional[ResultsStore] = None,
) -> list[ResultRow]:
    """Section III-D: sample an LLM strategy `config.llm_samples_per_target`
    times, admit each candidate (Stage 1-4), select the retained output,
    and run Stage 5-9 only for it.

    Returns every row written: the admitted-but-not-retained siblings
    (verdict=NOT_RETAINED), any protocol-failing siblings
    (verdict=NOT_ADMITTED), and the retained generation's full Stage 0-9
    result. Only the last of these is eligible for Pi(S) -- the others are
    `retained=False` and excluded from EFSR by `efsr.stats.efsr`.
    """
    store = store or ResultsStore(config.results_csv)
    samples: list[GeneratedTransformation] = generator.generate_samples(
        target, original_source, n=config.llm_samples_per_target,
    )

    outcomes: dict[int, AdmissionOutcome] = {}
    selection_candidates: list[SelectionCandidate] = []
    rows: list[ResultRow] = []

    for sample in samples:
        project_copy = materialize_project_copy(
            original_project_dir, target_relative_path, sample.modified_source, work_dir,
        )
        spec = TransformationSpec(
            process=sample.process, target_id=process_target_id,
            refactoring_type=target.refactoring_type,
            original_project_dir=Path(original_project_dir), modified_project_dir=project_copy,
            original_source_file=Path(original_project_dir) / target_relative_path,
            modified_source_file=project_copy / target_relative_path,
            class_name=target.class_name, method_name=target.method_name,
            generation_index=sample.generation_index,
        )
        outcome = admit_transformation(spec, config)
        outcomes[sample.generation_index] = outcome

        if outcome.error:
            rows.append(ResultRow(
                process=spec.process, target_id=spec.target_id,
                refactoring_type=spec.refactoring_type.value, generation_index=spec.generation_index,
                compile_status=CheckStatus.ERROR.value, tests_status=CheckStatus.SKIP.value,
                metric_status=CheckStatus.ERROR.value, admitted=False, retained=False,
                verdict=Verdict.ERROR.value, notes=outcome.error,
            ))
            continue
        if not outcome.result.admitted:
            rows.append(_not_admitted_row(spec, outcome.result, outcome.pre_metrics, retained=False))
            continue
        selection_candidates.append(SelectionCandidate(
            generation_index=sample.generation_index, modified_source=sample.modified_source,
            protocol_result=outcome.result,
        ))

    retained = select_retained_output(selection_candidates, target.refactoring_type, original_source)

    for candidate in selection_candidates:
        if retained is not None and candidate.generation_index == retained.generation_index:
            continue
        outcome = outcomes[candidate.generation_index]
        rows.append(ResultRow(
            process=outcome.spec.process, target_id=outcome.spec.target_id,
            refactoring_type=outcome.spec.refactoring_type.value, generation_index=outcome.spec.generation_index,
            compile_status=outcome.result.compile_status.value, tests_status=outcome.result.tests_status.value,
            metric_status=outcome.result.metric_status.value, admitted=True, retained=False,
            **_metrics_kwargs(outcome.pre_metrics),
            verdict=Verdict.NOT_RETAINED.value,
            notes="protocol-passing but not selected (Section III-D retained-output rule).",
        ))

    if retained is not None:
        outcome = outcomes[retained.generation_index]
        rows.append(_continue_from_admitted(outcome.spec, config, outcome.pre_metrics, outcome.result, retained=True))

    for row in rows:
        store.append(row)
    return rows


def _metrics_kwargs(metrics: Optional[StructuralMetrics]) -> dict:
    if metrics is None:
        return {}
    return dict(cc=metrics.cc, wmc=metrics.wmc, ce=metrics.ce, cbo=metrics.cbo,
                rfc=metrics.rfc, lcom=metrics.lcom, dit=metrics.dit, loc=metrics.loc)


def _not_admitted_row(
    spec: TransformationSpec, result: ProtocolResult, pre_metrics: Optional[StructuralMetrics],
    retained: bool = False,
) -> ResultRow:
    return ResultRow(
        process=spec.process, target_id=spec.target_id,
        refactoring_type=spec.refactoring_type.value, generation_index=spec.generation_index,
        compile_status=result.compile_status.value, tests_status=result.tests_status.value,
        metric_status=result.metric_status.value, admitted=False, retained=retained,
        **_metrics_kwargs(pre_metrics),
        verdict=Verdict.NOT_ADMITTED.value, notes=result.notes,
    )


def _continue_from_admitted(
    spec: TransformationSpec,
    config: PipelineConfig,
    pre_metrics: StructuralMetrics,
    result: ProtocolResult,
    retained: bool,
) -> ResultRow:
    """Stage 5-9 for a transformation already admitted to Pi(S)."""
    notes: list[str] = [result.notes]
    base_row_kwargs = dict(
        process=spec.process, target_id=spec.target_id,
        refactoring_type=spec.refactoring_type.value, generation_index=spec.generation_index,
        compile_status=result.compile_status.value, tests_status=result.tests_status.value,
        metric_status=result.metric_status.value, admitted=True, retained=retained,
        **_metrics_kwargs(pre_metrics),
        generation_budget_seconds=config.search_budget_seconds, generation_seed=config.generation_seed,
        replay_repetitions=config.replay_repetitions,
    )

    # --- Stage 5: a priori non-determinism exclusion ----------------------
    ndr = screen_file(spec.original_source_file)
    if ndr.is_nondeterministic:
        return ResultRow(
            **base_row_kwargs,
            excluded_nondeterministic=True, exclusion_reason=ndr.reason_text(),
            verdict=Verdict.EXCLUDED.value,
            notes="; ".join(notes + [f"excluded a priori: {ndr.reason_text()}"]),
        )

    # --- Stage 6: differential test generation -----------------------------
    test_dirs: list[Path] = []
    evosuite_count = randoop_count = 0
    tool_errors: list[str] = []

    evosuite_dir = Path(spec.modified_project_dir) / "efsr-diff-tests" / "evosuite"
    try:
        evo_result = run_regression_suite(
            spec.original_classpath, spec.modified_classpath, spec.class_name, evosuite_dir, config,
        )
        evosuite_count = evo_result.generated_test_count
        test_dirs.append(evo_result.test_dir)
    except EvoSuiteUnavailable as exc:
        tool_errors.append(str(exc))

    randoop_dir = Path(spec.modified_project_dir) / "efsr-diff-tests" / "randoop"
    try:
        rand_result = run_randoop(spec.modified_classpath, spec.class_name, randoop_dir, config)
        randoop_count = rand_result.generated_test_count
        test_dirs.append(rand_result.test_dir)
    except RandoopUnavailable as exc:
        tool_errors.append(str(exc))

    if not test_dirs:
        return ResultRow(
            **base_row_kwargs,
            evosuite_candidates=0, randoop_candidates=0,
            verdict=Verdict.ERROR.value,
            notes="; ".join(notes + ["no differential generator available: " + "; ".join(tool_errors)]),
        )

    # --- Stage 7-8: run generated suites against both versions, replay,
    #     confirm, classify -------------------------------------------------
    confirmed_category = TaxonomyCategory.NONE
    confirmed_channel = ""
    candidate_count = 0

    for test_dir in test_dirs:
        for test_class in junit_diff.discover_test_classes(test_dir):
            try:
                orig_run = junit_diff.run_junit_suite(spec.original_classpath, test_class, config)
                mod_run = junit_diff.run_junit_suite(spec.modified_classpath, test_class, config)
            except RuntimeError as exc:
                tool_errors.append(str(exc))
                continue
            candidates = junit_diff.diff_results(orig_run, mod_run)
            candidate_count += len(candidates)
            for candidate in candidates:
                if confirmed_category != TaxonomyCategory.NONE:
                    break
                if confirm_junit_candidate(
                    candidate, spec.original_classpath, spec.modified_classpath,
                    test_class, config.replay_repetitions, config,
                ):
                    confirmed_category, confirmed_channel = classify_junit_candidate(candidate)

    if confirmed_category != TaxonomyCategory.NONE:
        verdict = Verdict.DIVERGE
    elif tool_errors:
        verdict = Verdict.ERROR
    else:
        verdict = Verdict.NO_DIFFERENCE

    return ResultRow(
        **base_row_kwargs,
        evosuite_candidates=evosuite_count, randoop_candidates=randoop_count,
        candidate_divergences=candidate_count,
        verdict=verdict.value,
        taxonomy_category=confirmed_category.value,
        divergence_channel=confirmed_channel,
        notes="; ".join(notes + tool_errors),
    )


def _store(store: Optional[ResultsStore], row: ResultRow, config: PipelineConfig) -> None:
    (store or ResultsStore(config.results_csv)).append(row)
