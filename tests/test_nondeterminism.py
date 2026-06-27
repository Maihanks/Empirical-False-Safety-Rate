from efsr.nondeterminism import screen_source


def test_clean_source_is_not_flagged():
    source = """
    package x;
    public class Range {
        public static int clamp(int low, int high, int value) {
            if (value < low) return low;
            if (value > high) return high;
            return value;
        }
    }
    """
    report = screen_source(source)
    assert report.is_nondeterministic is False
    assert report.matched_reasons == []


def test_unseeded_random_is_flagged():
    source = "class A { void m() { java.util.Random r = new Random(); } }"
    report = screen_source(source)
    assert report.is_nondeterministic is True
    assert any("Random" in r for r in report.matched_reasons)


def test_wall_clock_is_flagged():
    source = "class A { long t = System.currentTimeMillis(); }"
    report = screen_source(source)
    assert report.is_nondeterministic is True


def test_concurrency_is_flagged():
    source = "class A { synchronized void m() { new Thread(() -> {}).start(); } }"
    report = screen_source(source)
    assert report.is_nondeterministic is True
    assert len(report.matched_reasons) >= 1


def test_reason_text_joins_all_matches():
    source = "class A { Random r = new Random(); long t = System.nanoTime(); }"
    report = screen_source(source)
    assert ";" in report.reason_text() or len(report.matched_reasons) == 1
