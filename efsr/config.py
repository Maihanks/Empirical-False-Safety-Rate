"""Pipeline configuration: tool paths, generation budget, seeds, thresholds.

Values are resolved in this order: explicit constructor args > environment
variables (EFSR_*) > defaults. Tool paths (Maven, EvoSuite, Randoop, ckjm,
JUnit) are intentionally left unvalidated at construction time -- each
runner module checks for the concrete file/binary it needs and raises a
clear error at the point of use, so that stages which do not need a given
tool (e.g. Stage 1-4 without EvoSuite) can still run on a machine that only
has a subset of the toolchain installed.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_path(name: str, default: str | None) -> Path | None:
    val = os.environ.get(name, default)
    return Path(val) if val else None


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _env_float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


@dataclass
class PipelineConfig:
    # Toolchain
    maven_binary: str = field(default_factory=lambda: os.environ.get("EFSR_MAVEN_BIN", "mvn"))
    java_binary: str = field(default_factory=lambda: os.environ.get("EFSR_JAVA_BIN", "java"))
    javac_binary: str = field(default_factory=lambda: os.environ.get("EFSR_JAVAC_BIN", "javac"))

    evosuite_jar: Path | None = field(default_factory=lambda: _env_path("EFSR_EVOSUITE_JAR", None))
    randoop_jar: Path | None = field(default_factory=lambda: _env_path("EFSR_RANDOOP_JAR", None))
    ckjm_jar: Path | None = field(default_factory=lambda: _env_path("EFSR_CKJM_JAR", None))
    junit_jar: Path | None = field(default_factory=lambda: _env_path("EFSR_JUNIT_JAR", None))
    hamcrest_jar: Path | None = field(default_factory=lambda: _env_path("EFSR_HAMCREST_JAR", None))

    dualrunner_jar: Path = field(
        default_factory=lambda: _env_path(
            "EFSR_DUALRUNNER_JAR",
            str(Path(__file__).resolve().parent / "difftest" / "harness" / "dist" / "dualrunner.jar"),
        )
    )
    jdeodorant_jar: Path | None = field(default_factory=lambda: _env_path("EFSR_JDEODORANT_JAR", None))
    refactoringminer_binary: str = field(
        default_factory=lambda: os.environ.get("EFSR_REFACTORINGMINER_BIN", "RefactoringMiner")
    )

    # Differential test generation budget (Stage 6)
    search_budget_seconds: int = field(default_factory=lambda: _env_int("EFSR_SEARCH_BUDGET_S", 120))
    randoop_time_limit_seconds: int = field(default_factory=lambda: _env_int("EFSR_RANDOOP_TIME_LIMIT_S", 120))
    generation_seed: int = field(default_factory=lambda: _env_int("EFSR_SEED", 42))

    # metric(T) method-count gate (Section III-B): for Extract Method/Long
    # Method, the originating method's CC must strictly drop, and the
    # class's method count may grow by at most this many members -- the
    # paper's qualitative "not beyond the extracted members" bound, made
    # concrete and configurable since the paper does not fix a number.
    max_extracted_methods: int = field(default_factory=lambda: _env_int("EFSR_MAX_EXTRACTED_METHODS", 5))

    # Corpus construction (Section III-C): smell-detection thresholds and
    # the JaCoCo line-coverage gate.
    long_method_cc_threshold: float = field(default_factory=lambda: _env_float("EFSR_LONG_METHOD_CC", 10.0))
    long_method_loc_threshold: float = field(default_factory=lambda: _env_float("EFSR_LONG_METHOD_LOC", 50.0))
    large_class_wmc_threshold: float = field(default_factory=lambda: _env_float("EFSR_LARGE_CLASS_WMC", 47.0))
    large_class_nom_threshold: float = field(default_factory=lambda: _env_float("EFSR_LARGE_CLASS_NOM", 20.0))
    large_class_loc_threshold: float = field(default_factory=lambda: _env_float("EFSR_LARGE_CLASS_LOC", 300.0))
    min_line_coverage: float = field(default_factory=lambda: _env_float("EFSR_MIN_LINE_COVERAGE", 0.6))

    # Generation (Section III-D): LLM strategies are sampled this many
    # times at temperature-zero decoding; the best of the protocol-passing
    # generations is retained (efsr.selection).
    llm_samples_per_target: int = field(default_factory=lambda: _env_int("EFSR_LLM_SAMPLES", 3))
    llm_temperature: float = field(default_factory=lambda: _env_float("EFSR_LLM_TEMPERATURE", 0.0))

    # Replay / confirmation (Stage 8)
    replay_repetitions: int = field(default_factory=lambda: _env_int("EFSR_REPLAY_REPETITIONS", 5))

    # Subprocess timeouts
    maven_timeout_seconds: int = field(default_factory=lambda: _env_int("EFSR_MAVEN_TIMEOUT_S", 600))
    evosuite_timeout_seconds: int = field(default_factory=lambda: _env_int("EFSR_EVOSUITE_TIMEOUT_S", 600))
    randoop_timeout_seconds: int = field(default_factory=lambda: _env_int("EFSR_RANDOOP_TIMEOUT_S", 600))
    junit_run_timeout_seconds: int = field(default_factory=lambda: _env_int("EFSR_JUNIT_RUN_TIMEOUT_S", 300))
    dualrunner_timeout_seconds: int = field(default_factory=lambda: _env_int("EFSR_DUALRUNNER_TIMEOUT_S", 60))

    # Statistics (Section III-I)
    wilson_z: float = field(default_factory=lambda: _env_float("EFSR_WILSON_Z", 1.959963984540054))
    min_events_per_variable: int = field(default_factory=lambda: _env_int("EFSR_MIN_EPV", 10))
    bonferroni_alpha: float = field(default_factory=lambda: _env_float("EFSR_ALPHA", 0.05))

    # Output locations
    results_dir: Path = field(default_factory=lambda: Path(os.environ.get("EFSR_RESULTS_DIR", "results")))
    results_csv: Path = field(init=False)

    def __post_init__(self) -> None:
        self.results_dir = Path(self.results_dir)
        self.results_csv = self.results_dir / "csv" / "transformations.csv"


DEFAULT_CONFIG = PipelineConfig()
