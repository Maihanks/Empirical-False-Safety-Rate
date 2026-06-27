"""ckjm-backed structural metrics extractor.

ckjm (Chidamber & Kemerer Java Metrics) computes WMC, DIT, NOC, CBO, RFC,
LCOM, Ca, Ce, NPM, LCOM3, LOC, DAM, MOA, MFA, CAM, IC, CBM, AMC, and a
max(CC) column, from compiled .class files. Invocation form:

    java -cp ckjm.jar:<classes_dir> CkjmMain <list-of-.class-files>

This wrapper assumes that column layout (the tool's documented default
output, one whitespace-separated row per class: name, then the 19 metrics
in the order above). If a local ckjm build uses a different column order,
adjust `_COLUMNS` to match -- the parser is otherwise generic.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from efsr.config import PipelineConfig, DEFAULT_CONFIG
from efsr.metrics.types import StructuralMetrics

_COLUMNS = [
    "wmc", "dit", "noc", "cbo", "rfc", "lcom", "ca", "ce",
    "npm", "lcom3", "loc", "dam", "moa", "mfa", "cam", "ic", "cbm", "amc", "max_cc",
]


class CkjmUnavailable(RuntimeError):
    pass


class CkjmExtractor:
    def __init__(self, config: PipelineConfig = DEFAULT_CONFIG):
        self.config = config
        if not (self.config.ckjm_jar and Path(self.config.ckjm_jar).is_file()):
            raise CkjmUnavailable(
                "ckjm jar not configured/found (set EFSR_CKJM_JAR to a valid ckjm.jar path)."
            )

    def extract(self, classes_dir: Path, fully_qualified_class_name: str) -> StructuralMetrics:
        class_rel = fully_qualified_class_name.replace(".", "/") + ".class"
        class_file = Path(classes_dir) / class_rel
        if not class_file.is_file():
            raise FileNotFoundError(f"compiled class not found: {class_file}")

        cmd = [
            self.config.java_binary,
            "-cp", f"{self.config.ckjm_jar}{_classpath_sep()}{classes_dir}",
            "CkjmMain",
            str(class_file),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            raise RuntimeError(f"ckjm invocation failed: {proc.stderr}")
        return self._parse(proc.stdout, fully_qualified_class_name)

    def _parse(self, stdout: str, fqcn: str) -> StructuralMetrics:
        for line in stdout.splitlines():
            parts = line.split()
            if not parts:
                continue
            name, values = parts[0], parts[1:]
            if name != fqcn or len(values) < len(_COLUMNS):
                continue
            row = dict(zip(_COLUMNS, (float(v) for v in values[: len(_COLUMNS)])))
            return StructuralMetrics(
                cc=row["max_cc"],
                wmc=row["wmc"],
                ce=row["ce"],
                cbo=row["cbo"],
                rfc=row["rfc"],
                lcom=row["lcom"],
                dit=row["dit"],
                loc=row["loc"],
            )
        raise RuntimeError(f"ckjm output did not contain a row for {fqcn}:\n{stdout}")


def _classpath_sep() -> str:
    import os

    return os.pathsep
