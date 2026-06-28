"""Bridges the two metrics backends' different inputs to one call shape.

CkjmExtractor.extract(classes_dir, fully_qualified_class_name) operates on
compiled bytecode; PureJavaSourceExtractor.extract(java_file, class_name,
method_name) operates on source. The pipeline orchestrator only knows
about a TransformationSpec, so this adapter resolves whichever shape the
configured backend expects.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

from efsr.config import PipelineConfig, DEFAULT_CONFIG
from efsr.metrics.ckjm import CkjmExtractor
from efsr.metrics.extractor import get_extractor
from efsr.metrics.pure_python import PureJavaSourceExtractor, count_declared_methods
from efsr.metrics.types import StructuralMetrics


def extract_metrics(
    java_file: Path,
    classes_dir: Path,
    fully_qualified_class_name: str,
    method_name: str | None,
    config: PipelineConfig = DEFAULT_CONFIG,
) -> StructuralMetrics:
    backend = get_extractor(config)
    simple_name = fully_qualified_class_name.rsplit(".", 1)[-1]

    if isinstance(backend, CkjmExtractor):
        metrics = backend.extract(classes_dir, fully_qualified_class_name)
    elif isinstance(backend, PureJavaSourceExtractor):
        metrics = backend.extract(java_file, class_name=simple_name, method_name=method_name)
    else:
        raise TypeError(f"unrecognised metrics backend: {type(backend)!r}")

    if metrics.nom is None:
        # ckjm's standard column set has no total-method-count column;
        # source it independently so metric(T)'s method-count gate works
        # regardless of which backend computed the rest of the panel.
        metrics = dataclasses.replace(metrics, nom=float(count_declared_methods(java_file, simple_name)))
    return metrics
