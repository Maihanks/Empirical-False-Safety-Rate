"""Section III-C: refactoring targets and corpus construction.

Targets are classes that (a) carry a Long Method or large-class smell
detected by a static analyser, and (b) are covered by an existing test
suite whose line coverage exceeds a fixed threshold measured with JaCoCo.
This module implements both halves of that gate over a local Java project
checkout (Defects4J / Commons / Guava / Spring-style layout assumed, but
nothing here is project-specific beyond "a tree of .java files plus a
JaCoCo XML report").

Smell detection is the same source-level approximation used as the
metrics fallback in efsr.metrics.pure_python (CC, WMC, NOM, LOC computed
via javalang), not a separate static-analysis tool -- the corpus only
needs *candidate* targets; the precise pre/post metrics used to decide
metric(T) are recomputed later, on the actual transformation pair, by
whichever extractor is configured (ckjm or pure-Python).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import javalang

from efsr.config import PipelineConfig, DEFAULT_CONFIG
from efsr.metrics.pure_python import _count_loc, _find_class, _method_cyclomatic_complexity
from efsr.protocol import RefactoringType


@dataclass
class SmellCandidate:
    source_file: Path
    class_name: str            # fully-qualified, derived from package + simple name
    refactoring_type: RefactoringType
    method_name: Optional[str] = None   # set for method-level smells (Long Method)
    cc: Optional[float] = None
    loc: Optional[float] = None
    wmc: Optional[float] = None
    nom: Optional[float] = None
    line_coverage: Optional[float] = None


def _package_name(tree) -> str:
    return tree.package.name if tree.package else ""


def _fully_qualified_name(tree, simple_name: str) -> str:
    package = _package_name(tree)
    return f"{package}.{simple_name}" if package else simple_name


def _method_loc(source_lines: list[str], method_node) -> int:
    """Approximate a method's source-line span by brace counting from its
    declaration line, then reusing the same non-blank/non-comment count as
    the class-level LOC approximation.
    """
    start = method_node.position.line - 1  # 0-indexed
    depth = 0
    started = False
    end = start
    for i in range(start, len(source_lines)):
        for ch in source_lines[i]:
            if ch == "{":
                depth += 1
                started = True
            elif ch == "}":
                depth -= 1
        end = i
        if started and depth <= 0:
            break
    span = source_lines[start: end + 1]
    return _count_loc("\n".join(span), method_node)


def detect_long_method_smells(java_file: Path, config: PipelineConfig = DEFAULT_CONFIG) -> list[SmellCandidate]:
    """Flag methods whose CC or LOC exceeds the configured Long Method thresholds."""
    source = Path(java_file).read_text()
    source_lines = source.splitlines()
    tree = javalang.parse.parse(source)

    candidates = []
    for _, class_node in tree.filter(javalang.tree.ClassDeclaration):
        fqcn = _fully_qualified_name(tree, class_node.name)
        for method in class_node.methods:
            cc = _method_cyclomatic_complexity(method)
            loc = _method_loc(source_lines, method)
            if cc > config.long_method_cc_threshold or loc > config.long_method_loc_threshold:
                candidates.append(SmellCandidate(
                    source_file=Path(java_file), class_name=fqcn,
                    refactoring_type=RefactoringType.LONG_METHOD,
                    method_name=method.name, cc=float(cc), loc=float(loc),
                ))
    return candidates


def detect_large_class_smells(java_file: Path, config: PipelineConfig = DEFAULT_CONFIG) -> list[SmellCandidate]:
    """Flag classes whose WMC, method count, or LOC exceeds the configured
    Large Class ("Blob") thresholds. Any one threshold being exceeded is
    sufficient, matching common Large Class smell-detection practice.
    """
    source = Path(java_file).read_text()
    tree = javalang.parse.parse(source)

    candidates = []
    for _, class_node in tree.filter(javalang.tree.ClassDeclaration):
        fqcn = _fully_qualified_name(tree, class_node.name)
        wmc = sum(_method_cyclomatic_complexity(m) for m in class_node.methods)
        nom = len(class_node.methods)
        loc = _count_loc(source, class_node)
        if (wmc > config.large_class_wmc_threshold
                or nom > config.large_class_nom_threshold
                or loc > config.large_class_loc_threshold):
            candidates.append(SmellCandidate(
                source_file=Path(java_file), class_name=fqcn,
                refactoring_type=RefactoringType.LARGE_CLASS,
                wmc=float(wmc), nom=float(nom), loc=float(loc),
            ))
    return candidates


# --- JaCoCo coverage gate ---------------------------------------------------

def parse_jacoco_line_coverage(jacoco_xml_path: Path) -> dict[str, float]:
    """Map fully-qualified class name -> line coverage ratio (0..1) from a
    standard JaCoCo XML report (`<report><package><class><counter
    type="LINE" missed=".." covered=".."/></class></package></report>`).
    """
    tree = ET.parse(jacoco_xml_path)
    coverage: dict[str, float] = {}
    for class_el in tree.getroot().iter("class"):
        raw_name = class_el.attrib.get("name", "")
        fqcn = raw_name.replace("/", ".")
        line_counter = next(
            (c for c in class_el.findall("counter") if c.attrib.get("type") == "LINE"), None
        )
        if line_counter is None:
            continue
        missed = int(line_counter.attrib.get("missed", 0))
        covered = int(line_counter.attrib.get("covered", 0))
        total = missed + covered
        coverage[fqcn] = (covered / total) if total else 0.0
    return coverage


def build_corpus(
    project_dir: Path,
    jacoco_xml_path: Path,
    config: PipelineConfig = DEFAULT_CONFIG,
    source_glob: str = "**/*.java",
    exclude_test_dirs: bool = True,
) -> list[SmellCandidate]:
    """Walk `project_dir` for smell-carrying classes, then keep only those
    whose JaCoCo line coverage exceeds `config.min_line_coverage`.

    Classes with no entry in the JaCoCo report are excluded (treated as
    uncovered) rather than silently admitted -- "covered by an existing
    test suite whose line coverage exceeds a fixed threshold" is a hard
    requirement of the corpus definition, not a default-on one.
    """
    coverage = parse_jacoco_line_coverage(jacoco_xml_path)

    candidates: list[SmellCandidate] = []
    for java_file in sorted(Path(project_dir).glob(source_glob)):
        if exclude_test_dirs and _is_test_path(java_file):
            continue
        try:
            candidates.extend(detect_long_method_smells(java_file, config))
            candidates.extend(detect_large_class_smells(java_file, config))
        except (javalang.parser.JavaSyntaxError, javalang.tokenizer.LexerError, OSError):
            continue

    admitted = []
    for candidate in candidates:
        line_cov = coverage.get(candidate.class_name)
        if line_cov is None or line_cov < config.min_line_coverage:
            continue
        candidate.line_coverage = line_cov
        admitted.append(candidate)
    return admitted


def _is_test_path(java_file: Path) -> bool:
    parts = {p.lower() for p in java_file.parts}
    return bool(parts & {"test", "tests", "src-test"})
