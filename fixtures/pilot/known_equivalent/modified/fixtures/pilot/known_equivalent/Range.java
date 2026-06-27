package fixtures.pilot.known_equivalent;

/** Pilot fixture: post-transformation version (P'). Extract Method applied
 * to the two boundary checks in clamp(); behaviour-preserving (correct
 * boundary semantics retained). Used to confirm the oracle correctly
 * reports NO-DIFFERENCE for a genuinely equivalent transformation. */
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
