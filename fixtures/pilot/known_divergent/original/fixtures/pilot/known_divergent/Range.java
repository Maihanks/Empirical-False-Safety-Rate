package fixtures.pilot.known_divergent;

/** Pilot fixture: pre-transformation version (P). Identical in structure
 * to the known_equivalent fixture's original, in a separate package so the
 * two pilot pairs never share a classpath. */
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
