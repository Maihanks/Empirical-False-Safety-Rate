package fixtures.pilot.known_interaction_divergent;

/** Pilot fixture: pre-transformation version (P). Return value and field
 * state are unaffected by what message is logged -- only the recorded
 * Interface/API channel can distinguish this from the modified version. */
public class Notifier {
    private Logger logger = new Logger() {
        @Override
        public void log(String message) {
            // no-op default collaborator
        }
    };

    public int notify(int code) {
        logger.log("notify:" + code);
        return code;
    }
}
