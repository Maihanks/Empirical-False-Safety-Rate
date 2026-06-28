package fixtures.pilot.known_interaction_divergent;

/** Pilot fixture: post-transformation version (P'). Identical return value
 * and field state to the original, but the message format passed to the
 * logger collaborator has changed -- an Interface/API divergence (Section
 * III-G) invisible to return-value, exception, and state comparison. */
public class Notifier {
    private Logger logger = new Logger() {
        @Override
        public void log(String message) {
            // no-op default collaborator
        }
    };

    public int notify(int code) {
        logger.log("NOTIFY:" + code); // BUG: message format changed (was "notify:").
        return code;
    }
}
