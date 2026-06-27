import org.junit.runner.JUnitCore;
import org.junit.runner.Request;
import org.junit.runner.Result;
import org.junit.runner.notification.Failure;

/**
 * Runs one JUnit test class and prints one structured line per test method,
 * so that {@code efsr.difftest.junit_diff} can run the same generated suite
 * against the original and modified classpaths in two separate JVM
 * processes and diff the per-test outcomes (Stage 7).
 *
 * Process-level separation is the simplest form of classpath isolation:
 * each invocation's classpath contains exactly one version of the target
 * class, so there is no possibility of P and P' colliding in the same JVM.
 *
 * Usage: java -cp <junit.jar>:<hamcrest.jar>:<classpath under test>:<test class's own classpath> \
 *            JUnitTextRunner <fully.qualified.TestClassName>
 *
 * Output: one line per test, "TEST|<className>|<methodName>|<PASS|FAIL>|<exceptionClass>|<message>"
 */
public final class JUnitTextRunner {

    private JUnitTextRunner() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            System.err.println("Usage: JUnitTextRunner <fully.qualified.TestClassName>");
            System.exit(2);
        }
        String testClassName = args[0];
        Class<?> testClass = Class.forName(testClassName);

        JUnitCore core = new JUnitCore();
        Result result = core.run(Request.aClass(testClass));

        java.util.Set<String> failedKeys = new java.util.HashSet<>();
        java.util.Map<String, Failure> failureByKey = new java.util.HashMap<>();
        for (Failure failure : result.getFailures()) {
            String key = failure.getDescription().getClassName() + "#" + failure.getDescription().getMethodName();
            failedKeys.add(key);
            failureByKey.put(key, failure);
        }

        for (org.junit.runner.Description child : descriptionLeaves(Request.aClass(testClass).getRunner().getDescription())) {
            String className = child.getClassName();
            String methodName = child.getMethodName();
            if (methodName == null) {
                continue;
            }
            String key = className + "#" + methodName;
            if (failedKeys.contains(key)) {
                Failure failure = failureByKey.get(key);
                Throwable exc = failure.getException();
                String excClass = exc != null ? exc.getClass().getName() : "";
                String message = exc != null && exc.getMessage() != null ? exc.getMessage().replace("\n", " ") : "";
                System.out.println("TEST|" + className + "|" + methodName + "|FAIL|" + excClass + "|" + message);
            } else {
                System.out.println("TEST|" + className + "|" + methodName + "|PASS||");
            }
        }
    }

    private static java.util.List<org.junit.runner.Description> descriptionLeaves(org.junit.runner.Description root) {
        java.util.List<org.junit.runner.Description> leaves = new java.util.ArrayList<>();
        collectLeaves(root, leaves);
        return leaves;
    }

    private static void collectLeaves(org.junit.runner.Description node, java.util.List<org.junit.runner.Description> out) {
        if (node.getChildren().isEmpty() && node.getMethodName() != null) {
            out.add(node);
            return;
        }
        for (org.junit.runner.Description child : node.getChildren()) {
            collectLeaves(child, out);
        }
    }
}
