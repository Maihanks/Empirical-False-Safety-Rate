#!/usr/bin/env python3
"""Pilot validation: confirm the dual-classloader oracle distinguishes a
known-equivalent pair from a known-divergent pair before trusting any
numbers from the full pipeline (the "sensible build order" step in the
methodology).

Compiles each fixture pair under fixtures/pilot/<case>/{original,modified}
into separate classes directories with javac, then runs the
dual-classloader probe (Stage 7, channel-detail path) against both and
checks the verdict matches what the fixture is named for.

Usage: uv run python scripts/run_pilot_validation.py
Requires: a JDK with `javac` on PATH (or EFSR_JAVAC_BIN set), and
efsr/difftest/harness/dist/dualrunner.jar built (see harness/build.sh).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from efsr.config import DEFAULT_CONFIG
from efsr.difftest.dual_harness import run_dual_probe
from efsr.replay import confirm_channel_diffs
from efsr.taxonomy import classify_channel_diff

FIXTURES_DIR = REPO_ROOT / "fixtures" / "pilot"

CASES = [
    dict(
        name="known_equivalent",
        class_name="fixtures.pilot.known_equivalent.Range",
        expect_diverge=False,
        probe_values=[("I:0,I:10,I:5", "interior value"), ("I:0,I:10,I:15", "above-range value")],
    ),
    dict(
        name="known_divergent",
        class_name="fixtures.pilot.known_divergent.Range",
        expect_diverge=True,
        probe_values=[("I:0,I:10,I:15", "above-range value (exposes the off-by-one bug)")],
    ),
]


def compile_fixture(source_root: Path, classes_dir: Path) -> None:
    classes_dir.mkdir(parents=True, exist_ok=True)
    java_files = sorted(source_root.rglob("*.java"))
    if not java_files:
        raise FileNotFoundError(f"no .java sources under {source_root}")
    cmd = [DEFAULT_CONFIG.javac_binary, "-d", str(classes_dir), *map(str, java_files)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"javac failed for {source_root}:\n{proc.stdout}\n{proc.stderr}")


def main() -> int:
    if not shutil.which(DEFAULT_CONFIG.javac_binary):
        print(f"javac not found ({DEFAULT_CONFIG.javac_binary}); cannot compile pilot fixtures.", file=sys.stderr)
        return 2
    if not Path(DEFAULT_CONFIG.dualrunner_jar).is_file():
        print(
            f"dualrunner.jar not found at {DEFAULT_CONFIG.dualrunner_jar}.\n"
            f"Build it first: efsr/difftest/harness/build.sh",
            file=sys.stderr,
        )
        return 2

    all_passed = True
    for case in CASES:
        case_dir = FIXTURES_DIR / case["name"]
        original_classes = case_dir / "original" / "classes"
        modified_classes = case_dir / "modified" / "classes"
        compile_fixture(case_dir / "original", original_classes)
        compile_fixture(case_dir / "modified", modified_classes)

        print(f"\n=== {case['name']} (expect_diverge={case['expect_diverge']}) ===")
        case_diverged = False
        for arg_spec, description in case["probe_values"]:
            diffs = run_dual_probe(
                str(original_classes), str(modified_classes), case["class_name"],
                "clamp", arg_spec, DEFAULT_CONFIG.replay_repetitions, DEFAULT_CONFIG,
            )
            confirmed = confirm_channel_diffs(diffs)
            label = "DIVERGE" if confirmed else "NO_DIFFERENCE"
            extra = ""
            if confirmed:
                category, channel = classify_channel_diff(diffs[0])
                extra = f" (category={category.value}, channel={channel})"
            print(f"  probe[{description}] arg_spec={arg_spec!r} -> {label}{extra}")
            case_diverged = case_diverged or confirmed

        expected = case["expect_diverge"]
        ok = case_diverged == expected
        print(f"  result: {'PASS' if ok else 'FAIL'} "
              f"(observed_diverge={case_diverged}, expected_diverge={expected})")
        all_passed = all_passed and ok

    print(f"\nPilot validation: {'PASSED' if all_passed else 'FAILED'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
