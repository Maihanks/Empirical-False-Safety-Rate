package fixtures.pilot.known_divergent;

/** Pilot fixture: post-transformation version (P'). Extract Method applied
 * to clamp(), but with a deliberately introduced off-by-one bug: any value
 * above the range is clamped to `high - 1` instead of `high`. Used to
 * confirm the oracle correctly reports DIVERGE (e.g. clamp(0, 10, 15)
 * returns 10 in P and 9 in P'). */
public class Range {

    public static int clamp(int low, int high, int value) {
        if (isBelowRange(low, value)) {
            return low;
        }
        if (isAboveRange(high, value)) {
            return high - 1; // BUG: should be `high`.
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
