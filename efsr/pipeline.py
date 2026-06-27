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
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from efsr.config import PipelineConfig, DEFAULT_CONFIG
from efsr.difftest import junit_diff
from efsr.difftest.evosuite import EvoSuiteUnavailable, run_regression_suite
from efsr.difftest.randoop import RandoopUnavailable, run_randoop
from efsr.metrics.adapter import extract_metrics
from efsr.nondeterminism import screen_file
from efsr.protocol import ThreeCheckProtocol, TransformationSpec
from efsr.replay import confirm_junit_candidate
from efsr.results import CheckStatus, ResultRow, ResultsStore, TaxonomyCategory, Verdict
from efsr.taxonomy import classify_junit_candidate

logger = logging.getLogger(__name__)


@dataclass
class PipelineOutcome:
    row: ResultRow
    notes: list[str]


def run_pipeline_for_transformation(
    spec: TransformationSpec,
    config: PipelineConfig = DEFAULT_CONFIG,
    store: ResultsStore | None = None,
) -> ResultRow:
    notes: list[str] = []

    # --- Stage 3 inputs: structural metrics on pre/post versions ---------
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
        row = ResultRow(
            process=spec.process, target_id=spec.target_id,
            refactoring_type=spec.refactoring_type.value, generation_index=spec.generation_index,
            compile_status=CheckStatus.ERROR.value, tests_status=CheckStatus.SKIP.value,
            metric_status=CheckStatus.ERROR.value, admitted=False,
            verdict=Verdict.ERROR.value, notes=f"metrics extraction failed: {exc}",
        )
        _store(store, row, config)
        return row

    # --- Stage 1-4: three-check protocol + admission to Pi(S) ------------
    protocol = ThreeCheckProtocol(config)
    result = protocol.run(spec, pre_metrics, post_metrics)
    notes.append(result.notes)

    if not result.admitted:
        row = ResultRow(
            process=spec.process, target_id=spec.target_id,
            refactoring_type=spec.refactoring_type.value, generation_index=spec.generation_index,
            compile_status=result.compile_status.value, tests_status=result.tests_status.value,
            metric_status=result.metric_status.value, admitted=False,
            cc=pre_metrics.cc, wmc=pre_metrics.wmc, ce=pre_metrics.ce, cbo=pre_metrics.cbo,
            rfc=pre_metrics.rfc, lcom=pre_metrics.lcom, dit=pre_metrics.dit, loc=pre_metrics.loc,
            verdict=Verdict.NOT_ADMITTED.value, notes="; ".join(notes),
        )
        _store(store, row, config)
        return row

    base_row_kwargs = dict(
        process=spec.process, target_id=spec.target_id,
        refactoring_type=spec.refactoring_type.value, generation_index=spec.generation_index,
        compile_status=result.compile_status.value, tests_status=result.tests_status.value,
        metric_status=result.metric_status.value, admitted=True,
        cc=pre_metrics.cc, wmc=pre_metrics.wmc, ce=pre_metrics.ce, cbo=pre_metrics.cbo,
        rfc=pre_metrics.rfc, lcom=pre_metrics.lcom, dit=pre_metrics.dit, loc=pre_metrics.loc,
        generation_budget_seconds=config.search_budget_seconds, generation_seed=config.generation_seed,
        replay_repetitions=config.replay_repetitions,
    )

    # --- Stage 5: a priori non-determinism exclusion ----------------------
    ndr = screen_file(spec.original_source_file)
    if ndr.is_nondeterministic:
        row = ResultRow(
            **base_row_kwargs,
            excluded_nondeterministic=True, exclusion_reason=ndr.reason_text(),
            verdict=Verdict.EXCLUDED.value,
            notes="; ".join(notes + [f"excluded a priori: {ndr.reason_text()}"]),
        )
        _store(store, row, config)
        return row

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
        row = ResultRow(
            **base_row_kwargs,
            evosuite_candidates=0, randoop_candidates=0,
            verdict=Verdict.ERROR.value,
            notes="; ".join(notes + ["no differential generator available: " + "; ".join(tool_errors)]),
        )
        _store(store, row, config)
        return row

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

    row = ResultRow(
        **base_row_kwargs,
        evosuite_candidates=evosuite_count, randoop_candidates=randoop_count,
        candidate_divergences=candidate_count,
        verdict=verdict.value,
        taxonomy_category=confirmed_category.value,
        divergence_channel=confirmed_channel,
        notes="; ".join(notes + tool_errors),
    )
    _store(store, row, config)
    return row


def _store(store: ResultsStore | None, row: ResultRow, config: PipelineConfig) -> None:
    (store or ResultsStore(config.results_csv)).append(row)
