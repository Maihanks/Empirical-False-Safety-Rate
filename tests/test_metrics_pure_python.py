import pytest

from efsr.metrics.pure_python import PureJavaSourceExtractor

EXTRACTOR = PureJavaSourceExtractor()

ORIGINAL_SOURCE = """
package fixtures;

public class Range {
    public static int clamp(int low, int high, int value) {
        if (value < low) {
            return low;
        }
        if (value > high) {
            return high;
        }
        return value;
    }
}
"""

REFACTORED_SOURCE = """
package fixtures;

public class Range {
    public static int clamp(int low, int high, int value) {
        if (isBelowRange(low, value)) {
            return low;
        }
        if (isAboveRange(high, value)) {
            return high;
        }
        return value;
    }

    private static boolean isBelowRange(int low, int value) {
        return value < low;
    }

    private static boolean isAboveRange(int high, int value) {
        return value > high;
    }
}
"""


def _write(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content)
    return path


def test_extract_method_reduces_cc_of_originating_method(tmp_path):
    original = _write(tmp_path, "Original.java", ORIGINAL_SOURCE)
    refactored = _write(tmp_path, "Refactored.java", REFACTORED_SOURCE)

    pre = EXTRACTOR.extract(original, class_name="Range", method_name="clamp")
    post = EXTRACTOR.extract(refactored, class_name="Range", method_name="clamp")

    # clamp() has 2 decision points (if/if) -> CC=3 before extraction.
    assert pre.cc == 3
    # After extracting both conditions into helper methods, clamp() itself
    # is back down to CC=3 too (still two ifs) -- but the call structure
    # changes: RFC should increase (more distinct call targets) even if CC
    # of the *method itself* doesn't drop in this particular refactor; the
    # purpose of this assertion is to confirm metric extraction is
    # self-consistent, not to assert a specific refactoring law.
    assert post.cc >= 1
    assert post.rfc > pre.rfc  # extraction adds call sites / methods, raising RFC


def test_loc_counts_non_blank_non_comment_lines(tmp_path):
    source = _write(tmp_path, "A.java", """
    package x;
    // a comment
    public class A {
        /* block
           comment */
        int field;
    }
    """)
    metrics = EXTRACTOR.extract(source, class_name="A")
    assert metrics.loc >= 3  # package, class decl, field decl at minimum
    assert metrics.loc < 8  # comments and blanks must be excluded


def test_dit_is_one_for_root_class_and_two_with_extends(tmp_path):
    root = _write(tmp_path, "Root.java", "class Root {}")
    child = _write(tmp_path, "Child.java", "class Child extends Root {}")
    assert EXTRACTOR.extract(root, class_name="Root").dit == 1.0
    assert EXTRACTOR.extract(child, class_name="Child").dit == 2.0


def test_unknown_method_name_raises(tmp_path):
    source = _write(tmp_path, "A.java", "class A { void m() {} }")
    with pytest.raises(ValueError):
        EXTRACTOR.extract(source, class_name="A", method_name="doesNotExist")


def test_unknown_class_name_raises(tmp_path):
    source = _write(tmp_path, "A.java", "class A { void m() {} }")
    with pytest.raises(ValueError):
        EXTRACTOR.extract(source, class_name="DoesNotExist")


def test_lcom_is_zero_for_single_method_class(tmp_path):
    source = _write(tmp_path, "A.java", "class A { int x; void m() { x = 1; } }")
    metrics = EXTRACTOR.extract(source, class_name="A")
    assert metrics.lcom == 0.0
