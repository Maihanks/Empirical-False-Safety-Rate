"""Stage 1-2: compile check and existing test-suite check, via Maven.

These two stages run the project's *own* build and test suite against the
candidate transformation P'. They are intentionally dumb wrappers around
`mvn` plus a Surefire-report parser: the point of the research is that this
check is weak, not that it should be reimplemented cleverly.
"""
from __future__ import annotations

import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from efsr.config import PipelineConfig, DEFAULT_CONFIG


@dataclass
class CompileResult:
    passed: bool
    log: str = ""


@dataclass
class TestResult:
    passed: bool
    total: int = 0
    failures: int = 0
    errors: int = 0
    skipped: int = 0
    failed_test_names: list[str] = field(default_factory=list)
    log: str = ""


class MavenRunner:
    """Wraps the project's standard Maven build for one module/project dir."""

    def __init__(self, project_dir: Path, config: PipelineConfig = DEFAULT_CONFIG):
        self.project_dir = Path(project_dir)
        self.config = config

    def _run(self, args: list[str], timeout: int) -> subprocess.CompletedProcess:
        return subprocess.run(
            [self.config.maven_binary, *args],
            cwd=self.project_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def compile(self) -> CompileResult:
        """Stage 1: `mvn -q compile`. Record-then-stop on failure."""
        try:
            proc = self._run(["-q", "compile"], timeout=self.config.maven_timeout_seconds)
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            return CompileResult(passed=False, log=f"compile invocation failed: {exc}")
        passed = proc.returncode == 0
        return CompileResult(passed=passed, log=proc.stdout + proc.stderr)

    def run_tests(self) -> TestResult:
        """Stage 2: `mvn -q test`, then parse Surefire XML reports.

        This runs the project's pre-existing, human-written suite -- the
        very check the article's central claim says is insufficient on its
        own. Differential testing (Stage 6-8) is what probes beyond it.
        """
        try:
            proc = self._run(["-q", "test"], timeout=self.config.maven_timeout_seconds)
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            return TestResult(passed=False, log=f"test invocation failed: {exc}")

        report_result = self._parse_surefire_reports()
        log = proc.stdout + proc.stderr
        if report_result is None:
            # No surefire-reports directory found at all; fall back to the
            # Maven exit code (still better than asserting PASS blindly).
            return TestResult(passed=proc.returncode == 0, log=log)
        report_result.log = log
        return report_result

    def _parse_surefire_reports(self) -> TestResult | None:
        reports_dir = self.project_dir / "target" / "surefire-reports"
        if not reports_dir.is_dir():
            return None
        xml_files = sorted(reports_dir.glob("TEST-*.xml"))
        if not xml_files:
            return None

        total = failures = errors = skipped = 0
        failed_names: list[str] = []
        for xml_file in xml_files:
            try:
                root = ET.parse(xml_file).getroot()
            except ET.ParseError:
                continue
            total += int(root.attrib.get("tests", 0))
            failures += int(root.attrib.get("failures", 0))
            errors += int(root.attrib.get("errors", 0))
            skipped += int(root.attrib.get("skipped", 0))
            for testcase in root.findall("testcase"):
                if testcase.find("failure") is not None or testcase.find("error") is not None:
                    classname = testcase.attrib.get("classname", "")
                    name = testcase.attrib.get("name", "")
                    failed_names.append(f"{classname}#{name}")

        passed = (failures == 0) and (errors == 0)
        return TestResult(
            passed=passed,
            total=total,
            failures=failures,
            errors=errors,
            skipped=skipped,
            failed_test_names=failed_names,
        )
