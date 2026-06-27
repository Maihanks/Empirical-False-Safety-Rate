"""End-to-end check of the dual-classloader probe against the pilot
fixtures. Requires a JDK (javac) and a built dualrunner.jar; skipped
otherwise (e.g. in a JRE-only sandbox), but should pass on any machine
with the full toolchain described in efsr/difftest/harness/build.sh.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

from efsr.config import DEFAULT_CONFIG
from efsr.difftest.dual_harness import run_dual_probe
from efsr.replay import confirm_channel_diffs
from efsr.taxonomy import classify_channel_diff
from efsr.results import TaxonomyCategory

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "fixtures" / "pilot"

requires_jdk_and_harness = pytest.mark.skipif(
    shutil.which(DEFAULT_CONFIG.javac_binary) is None or not Path(DEFAULT_CONFIG.dualrunner_jar).is_file(),
    reason="requires a JDK (javac) and a built efsr/difftest/harness/dist/dualrunner.jar",
)


def _compile(source_root: Path, classes_dir: Path) -> None:
    classes_dir.mkdir(parents=True, exist_ok=True)
    java_files = sorted(source_root.rglob("*.java"))
    cmd = [DEFAULT_CONFIG.javac_binary, "-d", str(classes_dir), *map(str, java_files)]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


@requires_jdk_and_harness
def test_known_equivalent_fixture_reports_no_difference(tmp_path):
    case_dir = FIXTURES_DIR / "known_equivalent"
    original_classes, modified_classes = tmp_path / "orig", tmp_path / "mod"
    _compile(case_dir / "original", original_classes)
    _compile(case_dir / "modified", modified_classes)

    diffs = run_dual_probe(
        str(original_classes), str(modified_classes), "fixtures.pilot.known_equivalent.Range",
        "clamp", "I:0,I:10,I:15", DEFAULT_CONFIG.replay_repetitions, DEFAULT_CONFIG,
    )
    assert confirm_channel_diffs(diffs) is False


@requires_jdk_and_harness
def test_known_divergent_fixture_reports_diverge_with_functional_category(tmp_path):
    case_dir = FIXTURES_DIR / "known_divergent"
    original_classes, modified_classes = tmp_path / "orig", tmp_path / "mod"
    _compile(case_dir / "original", original_classes)
    _compile(case_dir / "modified", modified_classes)

    diffs = run_dual_probe(
        str(original_classes), str(modified_classes), "fixtures.pilot.known_divergent.Range",
        "clamp", "I:0,I:10,I:15", DEFAULT_CONFIG.replay_repetitions, DEFAULT_CONFIG,
    )
    assert confirm_channel_diffs(diffs) is True
    category, _ = classify_channel_diff(diffs[0])
    assert category == TaxonomyCategory.FUNCTIONAL
