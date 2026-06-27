import java.io.File;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.net.URL;
import java.net.URLClassLoader;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * In-process dual-classloader probe (Stage 7 channel-detail mechanism).
 *
 * Loads the original (P) and modified (P') versions of a class from two
 * independent {@link URLClassLoader}s whose parent is the *platform*
 * classloader only (no application classpath). That parent choice is what
 * gives the isolation the methodology calls out as critical: P and P' may
 * declare identically-named classes/packages, but because neither loader's
 * parent can see either classpath, the two versions can never resolve to
 * the same {@code Class} object in this JVM.
 *
 * Invokes one method (static or instance, no-arg constructor for
 * instances) with the same arguments against both versions and reports,
 * per repetition, the three directly inspectable channels: return value,
 * thrown exception, and post-call object field state. (The fourth channel
 * in the taxonomy -- observable interaction with collaborators -- requires
 * instrumenting the collaborator, which is out of scope for this generic
 * probe; see efsr/difftest/dual_harness.py for how it is combined with the
 * JUnit-suite-level diff that EvoSuite/Randoop-generated tests go through.)
 *
 * Usage:
 *   java -cp dualrunner.jar DualRunner <originalClasspath> <modifiedClasspath> \
 *        <className> <methodName> <argSpec> <repetitions>
 *
 * argSpec is a comma-separated list of TYPE:value tokens (TYPE in
 * I,J,D,F,Z,S for int/long/double/float/boolean/String), or "-" for a
 * no-argument method.
 *
 * Output: one JSON object per line (one per repetition) on stdout.
 */
public final class DualRunner {

    private DualRunner() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 6) {
            System.err.println(
                "Usage: DualRunner <originalClasspath> <modifiedClasspath> <className> "
                + "<methodName> <argSpec> <repetitions>");
            System.exit(2);
        }
        String originalCp = args[0];
        String modifiedCp = args[1];
        String className = args[2];
        String methodName = args[3];
        String argSpec = args[4];
        int repetitions = Integer.parseInt(args[5]);

        URLClassLoader originalLoader = newIsolatedLoader(originalCp);
        URLClassLoader modifiedLoader = newIsolatedLoader(modifiedCp);

        Class<?>[] paramTypes = parseParamTypes(argSpec);
        Object[] argValues = parseArgValues(argSpec);

        for (int rep = 0; rep < repetitions; rep++) {
            Invocation orig = invoke(originalLoader, className, methodName, paramTypes, argValues);
            Invocation mod = invoke(modifiedLoader, className, methodName, paramTypes, argValues);
            System.out.println(toJson(rep, orig, mod));
        }
    }

    private static URLClassLoader newIsolatedLoader(String classpath) throws Exception {
        String[] parts = classpath.split(File.pathSeparator);
        URL[] urls = new URL[parts.length];
        for (int i = 0; i < parts.length; i++) {
            urls[i] = new File(parts[i]).toURI().toURL();
        }
        ClassLoader platformOnly = ClassLoader.getPlatformClassLoader();
        return new URLClassLoader(urls, platformOnly);
    }

    private static Class<?> typeFor(String code) {
        switch (code) {
            case "I": return int.class;
            case "J": return long.class;
            case "D": return double.class;
            case "F": return float.class;
            case "Z": return boolean.class;
            case "S": return String.class;
            default: throw new IllegalArgumentException("unknown arg type code: " + code);
        }
    }

    private static Class<?>[] parseParamTypes(String argSpec) {
        if (argSpec == null || argSpec.isEmpty() || argSpec.equals("-")) {
            return new Class<?>[0];
        }
        String[] tokens = argSpec.split(",");
        Class<?>[] types = new Class<?>[tokens.length];
        for (int i = 0; i < tokens.length; i++) {
            types[i] = typeFor(tokens[i].split(":", 2)[0]);
        }
        return types;
    }

    private static Object[] parseArgValues(String argSpec) {
        if (argSpec == null || argSpec.isEmpty() || argSpec.equals("-")) {
            return new Object[0];
        }
        String[] tokens = argSpec.split(",");
        Object[] values = new Object[tokens.length];
        for (int i = 0; i < tokens.length; i++) {
            String[] kv = tokens[i].split(":", 2);
            String type = kv[0];
            String raw = kv.length > 1 ? kv[1] : "";
            switch (type) {
                case "I": values[i] = Integer.parseInt(raw); break;
                case "J": values[i] = Long.parseLong(raw); break;
                case "D": values[i] = Double.parseDouble(raw); break;
                case "F": values[i] = Float.parseFloat(raw); break;
                case "Z": values[i] = Boolean.parseBoolean(raw); break;
                case "S": values[i] = raw; break;
                default: throw new IllegalArgumentException("unknown arg type code: " + type);
            }
        }
        return values;
    }

    private static final class Invocation {
        String returnRepr;
        String excClass;
        String excMessage;
        String stateRepr;
    }

    private static Invocation invoke(
            ClassLoader loader, String className, String methodName,
            Class<?>[] paramTypes, Object[] argValues) {
        Invocation inv = new Invocation();
        try {
            Class<?> clazz = Class.forName(className, true, loader);
            Method method = clazz.getMethod(methodName, paramTypes);
            Object target = null;
            if (!Modifier.isStatic(method.getModifiers())) {
                Constructor<?> ctor = clazz.getDeclaredConstructor();
                ctor.setAccessible(true);
                target = ctor.newInstance();
            }
            try {
                Object result = method.invoke(target, argValues);
                inv.returnRepr = String.valueOf(result);
            } catch (InvocationTargetException ite) {
                Throwable cause = ite.getCause() != null ? ite.getCause() : ite;
                inv.excClass = cause.getClass().getName();
                inv.excMessage = cause.getMessage();
            }
            if (target != null) {
                inv.stateRepr = dumpFieldState(target);
            }
        } catch (Exception e) {
            inv.excClass = "HARNESS_ERROR:" + e.getClass().getName();
            inv.excMessage = e.getMessage();
        }
        return inv;
    }

    private static String dumpFieldState(Object target) throws IllegalAccessException {
        List<String> parts = new ArrayList<>();
        for (Field f : target.getClass().getDeclaredFields()) {
            if (Modifier.isStatic(f.getModifiers()) || f.isSynthetic()) {
                continue;
            }
            f.setAccessible(true);
            Object value = f.get(target);
            parts.add(f.getName() + "=" + String.valueOf(value));
        }
        Collections.sort(parts);
        return String.join(";", parts);
    }

    private static String toJson(int rep, Invocation orig, Invocation mod) {
        StringBuilder sb = new StringBuilder();
        sb.append("{");
        sb.append("\"rep\":").append(rep).append(",");
        jsonField(sb, "return_orig", orig.returnRepr).append(",");
        jsonField(sb, "return_mod", mod.returnRepr).append(",");
        jsonField(sb, "exc_orig", orig.excClass).append(",");
        jsonField(sb, "exc_orig_msg", orig.excMessage).append(",");
        jsonField(sb, "exc_mod", mod.excClass).append(",");
        jsonField(sb, "exc_mod_msg", mod.excMessage).append(",");
        jsonField(sb, "state_orig", orig.stateRepr).append(",");
        jsonField(sb, "state_mod", mod.stateRepr);
        sb.append("}");
        return sb.toString();
    }

    private static StringBuilder jsonField(StringBuilder sb, String key, String value) {
        sb.append("\"").append(key).append("\":");
        if (value == null) {
            sb.append("null");
        } else {
            sb.append("\"").append(jsonEscape(value)).append("\"");
        }
        return sb;
    }

    private static String jsonEscape(String s) {
        StringBuilder sb = new StringBuilder(s.length());
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"': sb.append("\\\""); break;
                case '\\': sb.append("\\\\"); break;
                case '\n': sb.append("\\n"); break;
                case '\r': sb.append("\\r"); break;
                case '\t': sb.append("\\t"); break;
                default:
                    if (c < 0x20) {
                        sb.append(String.format("\\u%04x", (int) c));
                    } else {
                        sb.append(c);
                    }
            }
        }
        return sb.toString();
    }
}
