"""Stage 6: difference-revealing test generation via EvoSuite's regression mode.

    java -jar evosuite.jar -regressionSuite \
        -projectCP <original_classpath> \
        -Dregressioncp=<modified_classpath> \
        -class <fully.qualified.TargetClass> \
        -Dsearch_budget=<seconds> -Dseed=<seed> -Dtest_dir=<output_dir>

The seed and search budget are fixed and recorded for reproducibility
(Section III-F). EvoSuiteR performs its own P/P' comparison internally;
the JUnit suite it emits under `-Dtest_dir` is what Stage 7 executes
against both classpaths via `efsr.difftest.junit_diff`.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from efsr.config import PipelineConfig, DEFAULT_CONFIG


class EvoSuiteUnavailable(RuntimeError):
    pass


@dataclass
class EvoSuiteResult:
    returncode: int
    generated_test_count: int
    test_dir: Path
    log: str


def run_regression_suite(
    original_classpath: str,
    modified_classpath: str,
    target_class: str,
    output_dir: Path,
    config: PipelineConfig = DEFAULT_CONFIG,
) -> EvoSuiteResult:
    if not (config.evosuite_jar and Path(config.evosuite_jar).is_file()):
        raise EvoSuiteUnavailable(
            "EvoSuite jar not configured/found (set EFSR_EVOSUITE_JAR)."
        )
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        config.java_binary, "-jar", str(config.evosuite_jar),
        "-regressionSuite",
        "-projectCP", original_classpath,
        f"-Dregressioncp={modified_classpath}",
        "-class", target_class,
        f"-Dsearch_budget={config.search_budget_seconds}",
        f"-Dseed={config.generation_seed}",
        f"-Dtest_dir={output_dir}",
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=config.evosuite_timeout_seconds
        )
    except subprocess.TimeoutExpired as exc:
        return EvoSuiteResult(returncode=-1, generated_test_count=0, test_dir=output_dir,
                               log=f"EvoSuite timed out after {config.evosuite_timeout_seconds}s: {exc}")

    log = proc.stdout + proc.stderr
    count = _count_generated_tests(output_dir)
    return EvoSuiteResult(returncode=proc.returncode, generated_test_count=count, test_dir=output_dir, log=log)


def _count_generated_tests(test_dir: Path) -> int:
    if not test_dir.is_dir():
        return 0
    count = 0
    test_method_pattern = re.compile(r"@Test\b")
    for java_file in test_dir.rglob("*.java"):
        try:
            count += len(test_method_pattern.findall(java_file.read_text()))
        except OSError:
            continue
    return count
