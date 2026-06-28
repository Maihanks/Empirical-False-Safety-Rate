package fixtures.pilot.known_interaction_divergent;

/** Collaborator interface; DualRunner proxies fields of this shape to
 * record the Interface/API channel (Section III-G). */
public interface Logger {
    void log(String message);
}
