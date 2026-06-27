package fixtures.pilot.known_equivalent;

/** Pilot fixture: pre-transformation version (P). A Long Method candidate
 * for Extract Method refactoring. Stateless/static so the dual-classloader
 * probe (DualRunner) can invoke it without needing constructor arguments. */
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
