"""Unified metrics-extraction interface (Stage 3 / Section III-H input).

Prefers ckjm against compiled bytecode when configured; falls back to the
pure-Python source-level approximation otherwise, with a warning, so the
pipeline can run end-to-end on a machine without the full Java toolchain.
"""
from __future__ import annotations

import warnings
from pathlib import Path
from typing import Protocol

from efsr.config import PipelineConfig, DEFAULT_CONFIG
from efsr.metrics.types import StructuralMetrics


class MetricsExtractor(Protocol):
    def extract(self, *args, **kwargs) -> StructuralMetrics: ...


def get_extractor(config: PipelineConfig = DEFAULT_CONFIG, prefer: str = "auto") -> MetricsExtractor:
    """Return a metrics backend.

    prefer: "ckjm" | "pure_python" | "auto" (ckjm if configured, else
    pure_python with a warning).
    """
    if prefer in ("ckjm", "auto"):
        from efsr.metrics.ckjm import CkjmExtractor, CkjmUnavailable
        try:
            return CkjmExtractor(config)
        except CkjmUnavailable:
            if prefer == "ckjm":
                raise
    from efsr.metrics.pure_python import PureJavaSourceExtractor
    warnings.warn(
        "Falling back to the pure-Python source-level metrics approximation "
        "(ckjm not configured). Treat structural-metric values as "
        "approximate; see efsr/metrics/pure_python.py for scope.",
        stacklevel=2,
    )
    return PureJavaSourceExtractor()
