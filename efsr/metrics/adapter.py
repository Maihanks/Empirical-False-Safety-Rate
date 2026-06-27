"""Bridges the two metrics backends' different inputs to one call shape.

CkjmExtractor.extract(classes_dir, fully_qualified_class_name) operates on
compiled bytecode; PureJavaSourceExtractor.extract(java_file, class_name,
method_name) operates on source. The pipeline orchestrator only knows
about a TransformationSpec, so this adapter resolves whichever shape the
configured backend expects.
"""
from __future__ import annotations

from pathlib import Path

from efsr.config import PipelineConfig, DEFAULT_CONFIG
from efsr.metrics.ckjm import CkjmExtractor
from efsr.metrics.extractor import get_extractor
from efsr.metrics.pure_python import PureJavaSourceExtractor
from efsr.metrics.types import StructuralMetrics


def extract_metrics(
    java_file: Path,
    classes_dir: Path,
    fully_qualified_class_name: str,
    method_name: str | None,
    config: PipelineConfig = DEFAULT_CONFIG,
) -> StructuralMetrics:
    backend = get_extractor(config)
    if isinstance(backend, CkjmExtractor):
        return backend.extract(classes_dir, fully_qualified_class_name)
    if isinstance(backend, PureJavaSourceExtractor):
        simple_name = fully_qualified_class_name.rsplit(".", 1)[-1]
        return backend.extract(java_file, class_name=simple_name, method_name=method_name)
    raise TypeError(f"unrecognised metrics backend: {type(backend)!r}")
