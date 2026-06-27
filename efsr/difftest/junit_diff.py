"""Stage 7 (primary path): run a generated JUnit suite against both versions.

EvoSuite's regression mode and Randoop both emit ordinary JUnit test
classes. The most general way to compare P and P' against an arbitrary
generated suite is to compile and run that suite twice -- once with the
target's compiled classes on the classpath from the original build, once
from the modified build -- and diff the per-test outcomes. Running each
side as its own JVM process, via JUnitTextRunner, gives classpath
isolation for free: each process's classpath contains exactly one version
of the class under test, so there is no possibility of P and P' classes
colliding (unlike a single JVM that tried to load both at once without
care). This is the mechanism used for the bulk of the corpus; the
in-process dual-classloader probe in dual_harness.py is reserved for
fine-grained, single-call channel inspection (pilot validation, manual
inspection of a flagged candidate).
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from efsr.config import PipelineConfig, DEFAULT_CONFIG

_PACKAGE_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)
_PUBLIC_CLASS_RE = re.compile(r"\bpublic\s+class\s+(\w+)")


def discover_test_classes(test_dir: Path) -> list[str]:
    """Best-effort scan for fully-qualified generated JUnit test class names.

    EvoSuite and Randoop both emit plain .java files; the test class name
    is not known ahead of generation, so callers that need to *run* what
    was generated (Stage 7) discover it from the emitted source instead of
    hard-coding a naming convention.
    """
    fqcns: list[str] = []
    for java_file in sorted(Path(test_dir).rglob("*.java")):
        try:
            source = java_file.read_text()
        except OSError:
            continue
        class_match = _PUBLIC_CLASS_RE.search(source)
        if not class_match:
            continue
        package_match = _PACKAGE_RE.search(source)
        package = package_match.group(1) if package_match else ""
        fqcn = f"{package}.{class_match.group(1)}" if package else class_match.group(1)
        fqcns.append(fqcn)
    return fqcns


@dataclass
class PerTestOutcome:
    class_name: str
    method_name: str
    passed: bool
    exception_class: str = ""
    message: str = ""


@dataclass
class JUnitRunResult:
    outcomes: dict[str, PerTestOutcome] = field(default_factory=dict)
    returncode: int = 0
    log: str = ""


@dataclass
class CandidateDivergence:
    test_key: str
    reason: str
    orig: Optional[PerTestOutcome]
    mod: Optional[PerTestOutcome]


def run_junit_suite(
    classpath: str,
    test_class: str,
    config: PipelineConfig = DEFAULT_CONFIG,
) -> JUnitRunResult:
    if not (config.junit_jar and config.junit_jar.is_file()):
        raise RuntimeError("JUnit jar not configured/found (set EFSR_JUNIT_JAR).")
    harness_cp = str(config.dualrunner_jar)
    full_cp = os.pathsep.join(
        [str(config.junit_jar), str(config.hamcrest_jar or ""), harness_cp, classpath]
    )
    cmd = [config.java_binary, "-cp", full_cp, "JUnitTextRunner", test_class]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=config.junit_run_timeout_seconds
        )
    except subprocess.TimeoutExpired as exc:
        return JUnitRunResult(returncode=-1, log=f"JUnit run timed out: {exc}")

    outcomes: dict[str, PerTestOutcome] = {}
    for line in proc.stdout.splitlines():
        if not line.startswith("TEST|"):
            continue
        _, class_name, method_name, status, exc_class, message = (line + "||||").split("|")[:6]
        key = f"{class_name}#{method_name}"
        outcomes[key] = PerTestOutcome(
            class_name=class_name, method_name=method_name,
            passed=(status == "PASS"), exception_class=exc_class, message=message,
        )
    return JUnitRunResult(outcomes=outcomes, returncode=proc.returncode, log=proc.stdout + proc.stderr)


def diff_results(orig: JUnitRunResult, mod: JUnitRunResult) -> list[CandidateDivergence]:
    """Stage 7 diff: a test that disagrees between P and P' is a candidate divergence.

    Disagreement includes: pass on one side and fail on the other, or fail
    on both sides with a different exception type (an Exceptional-category
    signal even though neither run is a "clean pass").
    """
    candidates: list[CandidateDivergence] = []
    keys = set(orig.outcomes) | set(mod.outcomes)
    for key in sorted(keys):
        o = orig.outcomes.get(key)
        m = mod.outcomes.get(key)
        if o is None or m is None:
            candidates.append(CandidateDivergence(
                test_key=key, reason="test present on only one side", orig=o, mod=m,
            ))
            continue
        if o.passed != m.passed:
            candidates.append(CandidateDivergence(
                test_key=key, reason="pass/fail disagreement", orig=o, mod=m,
            ))
        elif (not o.passed) and (not m.passed) and o.exception_class != m.exception_class:
            candidates.append(CandidateDivergence(
                test_key=key, reason="different exception on failure", orig=o, mod=m,
            ))
    return candidates
