from textwrap import dedent

import pytest

from efsr.config import PipelineConfig
from efsr.corpus import (
    build_corpus,
    detect_large_class_smells,
    detect_long_method_smells,
    parse_jacoco_line_coverage,
)
from efsr.protocol import RefactoringType

LONG_METHOD_SOURCE = dedent("""
    package org.example;

    public class Calculator {
        public int shortMethod(int x) {
            return x + 1;
        }

        public int longMethod(int x) {
            int total = 0;
            for (int i = 0; i < x; i++) {
                if (i % 2 == 0) {
                    total += i;
                } else if (i % 3 == 0) {
                    total -= i;
                } else {
                    total *= 2;
                }
                if (total > 1000) {
                    total = 1000;
                }
            }
            return total;
        }
    }
""")

LARGE_CLASS_SOURCE = "package org.example;\npublic class Blob {\n" + "".join(
    f"    public void m{i}() {{ int x = {i}; }}\n" for i in range(30)
) + "}\n"


def test_detect_long_method_smells_flags_high_cc_method(tmp_path):
    java_file = tmp_path / "Calculator.java"
    java_file.write_text(LONG_METHOD_SOURCE)
    config = PipelineConfig(long_method_cc_threshold=3, long_method_loc_threshold=1000)

    candidates = detect_long_method_smells(java_file, config)

    names = {c.method_name for c in candidates}
    assert "longMethod" in names
    assert "shortMethod" not in names
    flagged = next(c for c in candidates if c.method_name == "longMethod")
    assert flagged.refactoring_type == RefactoringType.LONG_METHOD
    assert flagged.class_name == "org.example.Calculator"
    assert flagged.cc > 3


def test_detect_long_method_smells_respects_loc_threshold_too(tmp_path):
    java_file = tmp_path / "Calculator.java"
    java_file.write_text(LONG_METHOD_SOURCE)
    # CC threshold high enough to not trip, LOC threshold low enough to trip.
    config = PipelineConfig(long_method_cc_threshold=1000, long_method_loc_threshold=3)

    candidates = detect_long_method_smells(java_file, config)
    assert any(c.method_name == "longMethod" for c in candidates)


def test_detect_large_class_smells_flags_high_method_count(tmp_path):
    java_file = tmp_path / "Blob.java"
    java_file.write_text(LARGE_CLASS_SOURCE)
    config = PipelineConfig(large_class_nom_threshold=10, large_class_wmc_threshold=1000, large_class_loc_threshold=1000)

    candidates = detect_large_class_smells(java_file, config)
    assert len(candidates) == 1
    assert candidates[0].class_name == "org.example.Blob"
    assert candidates[0].refactoring_type == RefactoringType.LARGE_CLASS
    assert candidates[0].nom == 30


def test_detect_large_class_smells_below_thresholds_is_empty(tmp_path):
    java_file = tmp_path / "Blob.java"
    java_file.write_text(LARGE_CLASS_SOURCE)
    config = PipelineConfig(large_class_nom_threshold=1000, large_class_wmc_threshold=1000, large_class_loc_threshold=1000)
    assert detect_large_class_smells(java_file, config) == []


JACOCO_XML = """<?xml version="1.0" encoding="UTF-8"?>
<report name="example">
  <package name="org/example">
    <class name="org/example/Calculator">
      <counter type="LINE" missed="2" covered="18"/>
      <counter type="INSTRUCTION" missed="5" covered="95"/>
    </class>
    <class name="org/example/Blob">
      <counter type="LINE" missed="25" covered="5"/>
    </class>
  </package>
</report>
"""


def test_parse_jacoco_line_coverage(tmp_path):
    xml_path = tmp_path / "jacoco.xml"
    xml_path.write_text(JACOCO_XML)
    coverage = parse_jacoco_line_coverage(xml_path)
    assert coverage["org.example.Calculator"] == pytest.approx(0.9)
    assert coverage["org.example.Blob"] == pytest.approx(5 / 30)


def test_build_corpus_filters_by_coverage_threshold(tmp_path):
    (tmp_path / "Calculator.java").write_text(LONG_METHOD_SOURCE)
    (tmp_path / "Blob.java").write_text(LARGE_CLASS_SOURCE)
    jacoco_path = tmp_path / "jacoco.xml"
    jacoco_path.write_text(JACOCO_XML)

    config = PipelineConfig(
        long_method_cc_threshold=3, long_method_loc_threshold=1000,
        large_class_nom_threshold=10, large_class_wmc_threshold=1000, large_class_loc_threshold=1000,
        min_line_coverage=0.6,
    )
    corpus = build_corpus(tmp_path, jacoco_path, config)

    classes = {c.class_name for c in corpus}
    # Calculator has 90% coverage (>=0.6) -> admitted; Blob has ~17% (<0.6) -> excluded.
    assert "org.example.Calculator" in classes
    assert "org.example.Blob" not in classes


def test_build_corpus_excludes_classes_missing_from_jacoco_report(tmp_path):
    (tmp_path / "Untested.java").write_text(LONG_METHOD_SOURCE.replace("Calculator", "Untested"))
    jacoco_path = tmp_path / "jacoco.xml"
    jacoco_path.write_text("<report name='empty'></report>")

    config = PipelineConfig(long_method_cc_threshold=3, long_method_loc_threshold=1000)
    corpus = build_corpus(tmp_path, jacoco_path, config)
    assert corpus == []


def test_build_corpus_excludes_test_directories(tmp_path):
    test_dir = tmp_path / "src" / "test" / "java"
    test_dir.mkdir(parents=True)
    (test_dir / "Calculator.java").write_text(LONG_METHOD_SOURCE)
    jacoco_path = tmp_path / "jacoco.xml"
    jacoco_path.write_text(JACOCO_XML)

    config = PipelineConfig(long_method_cc_threshold=3, long_method_loc_threshold=1000)
    corpus = build_corpus(tmp_path, jacoco_path, config)
    assert corpus == []
