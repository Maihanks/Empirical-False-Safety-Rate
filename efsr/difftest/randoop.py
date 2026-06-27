"""Stage 6 (corroborating generator): Randoop, run independently of EvoSuite.

Randoop is feedback-directed and has different generation biases than
EvoSuite's search-based approach (Section III-F: "so you're not relying on
a single tool's biases"). We run it once against the original version to
obtain a regression-style suite capturing P's behaviour, which Stage 7
then also executes against P' to look for disagreements.

    java -cp randoop.jar:<classpath> randoop.main.Main gentests \
        --testclass=<fully.qualified.TargetClass> \
        --time-limit=<seconds> \
        --junit-output-dir=<output_dir> \
        --regression-test-basename=RandoopRegression
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from efsr.config import PipelineConfig, DEFAULT_CONFIG


class RandoopUnavailable(RuntimeError):
    pass


@dataclass
class RandoopResult:
    returncode: int
    generated_test_count: int
    test_dir: Path
    log: str


def run_randoop(
    classpath: str,
    target_class: str,
    output_dir: Path,
    config: PipelineConfig = DEFAULT_CONFIG,
    test_basename: str = "RandoopRegression",
) -> RandoopResult:
    if not (config.randoop_jar and Path(config.randoop_jar).is_file()):
        raise RandoopUnavailable(
            "Randoop jar not configured/found (set EFSR_RANDOOP_JAR)."
        )
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    full_cp = f"{config.randoop_jar}{os.pathsep}{classpath}"
    cmd = [
        config.java_binary, "-cp", full_cp, "randoop.main.Main", "gentests",
        f"--testclass={target_class}",
        f"--time-limit={config.randoop_time_limit_seconds}",
        f"--junit-output-dir={output_dir}",
        f"--regression-test-basename={test_basename}",
        f"--randomseed={config.generation_seed}",
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=config.randoop_timeout_seconds, cwd=output_dir
        )
    except subprocess.TimeoutExpired as exc:
        return RandoopResult(returncode=-1, generated_test_count=0, test_dir=output_dir,
                              log=f"Randoop timed out after {config.randoop_timeout_seconds}s: {exc}")

    log = proc.stdout + proc.stderr
    count = _count_generated_tests(output_dir)
    return RandoopResult(returncode=proc.returncode, generated_test_count=count, test_dir=output_dir, log=log)


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
