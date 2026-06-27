"""Stage 0-4: the three-check protocol and admission to Pi(S).

Pi(S) = { T in T(S) : compile(T) AND tests(T) AND metric(T) }   (eq. 1)

Note (Section III-A / Section III of the article): these are *acceptance*
criteria, not evidence of behaviour preservation. This module only decides
whether a transformation is admitted to the denominator of EFSR; it makes
no claim about behavioural correctness, which is what Stage 5-8
(non-determinism screening + differential testing) probes instead.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from efsr.build_runner import MavenRunner, CompileResult, TestResult
from efsr.config import PipelineConfig, DEFAULT_CONFIG
from efsr.metrics.types import StructuralMetrics
from efsr.results import CheckStatus


class RefactoringType(str, Enum):
    EXTRACT_METHOD = "ExtractMethod"
    LONG_METHOD = "LongMethod"
    EXTRACT_CLASS = "ExtractClass"
    LARGE_CLASS = "LargeClass"


_METHOD_LEVEL_TYPES = {RefactoringType.EXTRACT_METHOD, RefactoringType.LONG_METHOD}
_CLASS_LEVEL_TYPES = {RefactoringType.EXTRACT_CLASS, RefactoringType.LARGE_CLASS}


@dataclass
class TransformationSpec:
    """One generated (or human, or rule-based) refactoring candidate."""

    process: str                     # e.g. "LLM-A", "LLM-A-CoT", "JDeodorant", "Human"
    target_id: str                   # e.g. "commons-lang:org.apache.commons.lang3.StringUtils#join"
    refactoring_type: RefactoringType
    original_project_dir: Path       # Maven project root for P
    modified_project_dir: Path       # Maven project root for P' (the candidate transformation)
    original_source_file: Path       # .java source of the pre-transformation target class
    modified_source_file: Path       # .java source of the post-transformation target class
    class_name: str                  # fully-qualified or simple class name within the source
    method_name: Optional[str] = None  # required for method-level refactoring types
    generation_index: int = 0

    @property
    def original_classpath(self) -> str:
        return str(Path(self.original_project_dir) / "target" / "classes")

    @property
    def modified_classpath(self) -> str:
        return str(Path(self.modified_project_dir) / "target" / "classes")

    @property
    def simple_class_name(self) -> str:
        return self.class_name.rsplit(".", 1)[-1]


@dataclass
class ProtocolResult:
    compile_status: CheckStatus
    tests_status: CheckStatus
    metric_status: CheckStatus
    admitted: bool
    pre_metrics: Optional[StructuralMetrics] = None
    post_metrics: Optional[StructuralMetrics] = None
    compile_log: str = ""
    tests_log: str = ""
    notes: str = ""


def evaluate_metric(
    pre: StructuralMetrics, post: StructuralMetrics, refactoring_type: RefactoringType
) -> bool:
    """metric(T): Section III-B / Stage 3.

    Extract Method / Long Method  -> strict reduction in the originating
        method's cyclomatic complexity (no requirement on method count
        beyond what the extraction itself implies).
    Extract Class / Large Class   -> strict reduction in WMC of the source
        class AND non-increase of its efferent coupling (Ce).
    """
    if refactoring_type in _METHOD_LEVEL_TYPES:
        if pre.cc is None or post.cc is None:
            raise ValueError("cyclomatic complexity (cc) required for method-level metric(T)")
        return post.cc < pre.cc
    if refactoring_type in _CLASS_LEVEL_TYPES:
        if pre.wmc is None or post.wmc is None or pre.ce is None or post.ce is None:
            raise ValueError("wmc and ce required for class-level metric(T)")
        return (post.wmc < pre.wmc) and (post.ce <= pre.ce)
    raise ValueError(f"no metric(T) rule defined for refactoring type {refactoring_type!r}")


class ThreeCheckProtocol:
    """Runs Stage 1 (compile), Stage 2 (tests), Stage 3 (metric), Stage 4 (admit)."""

    def __init__(self, config: PipelineConfig = DEFAULT_CONFIG):
        self.config = config

    def run(
        self,
        spec: TransformationSpec,
        pre_metrics: StructuralMetrics,
        post_metrics: StructuralMetrics,
    ) -> ProtocolResult:
        runner = MavenRunner(spec.modified_project_dir, self.config)

        compile_result: CompileResult = runner.compile()
        if not compile_result.passed:
            return ProtocolResult(
                compile_status=CheckStatus.FAIL,
                tests_status=CheckStatus.SKIP,
                metric_status=CheckStatus.SKIP,
                admitted=False,
                compile_log=compile_result.log,
                notes="compile(T) failed; transformation discarded before tests/metric.",
            )

        tests_result: TestResult = runner.run_tests()
        if not tests_result.passed:
            return ProtocolResult(
                compile_status=CheckStatus.PASS,
                tests_status=CheckStatus.FAIL,
                metric_status=CheckStatus.SKIP,
                admitted=False,
                pre_metrics=pre_metrics,
                post_metrics=post_metrics,
                compile_log=compile_result.log,
                tests_log=tests_result.log,
                notes=f"tests(T) failed ({tests_result.failures} failures, "
                      f"{tests_result.errors} errors): {tests_result.failed_test_names}",
            )

        try:
            metric_passed = evaluate_metric(pre_metrics, post_metrics, spec.refactoring_type)
        except ValueError as exc:
            return ProtocolResult(
                compile_status=CheckStatus.PASS,
                tests_status=CheckStatus.PASS,
                metric_status=CheckStatus.ERROR,
                admitted=False,
                pre_metrics=pre_metrics,
                post_metrics=post_metrics,
                compile_log=compile_result.log,
                tests_log=tests_result.log,
                notes=f"metric(T) could not be evaluated: {exc}",
            )

        if not metric_passed:
            return ProtocolResult(
                compile_status=CheckStatus.PASS,
                tests_status=CheckStatus.PASS,
                metric_status=CheckStatus.FAIL,
                admitted=False,
                pre_metrics=pre_metrics,
                post_metrics=post_metrics,
                compile_log=compile_result.log,
                tests_log=tests_result.log,
                notes="metric(T) did not improve; transformation discarded.",
            )

        # Stage 4: admission to Pi(S).
        return ProtocolResult(
            compile_status=CheckStatus.PASS,
            tests_status=CheckStatus.PASS,
            metric_status=CheckStatus.PASS,
            admitted=True,
            pre_metrics=pre_metrics,
            post_metrics=post_metrics,
            compile_log=compile_result.log,
            tests_log=tests_result.log,
            notes="admitted to Pi(S).",
        )
