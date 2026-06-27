#!/usr/bin/env bash
# Compiles DualRunner and JUnitTextRunner into efsr/difftest/harness/dist/.
#
# Usage: ./build.sh <path-to-junit4.jar> <path-to-hamcrest-core.jar>
#
# DualRunner has no compile-time dependency beyond the JDK. JUnitTextRunner
# needs JUnit 4 on the compile classpath. If you only need the
# classloader-isolation probe (pilot validation, fixtures), you can omit
# the jar arguments and ignore the JUnitTextRunner compile error.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JUNIT_JAR="${1:-}"
HAMCREST_JAR="${2:-}"
DIST="$HERE/dist"
mkdir -p "$DIST"

echo "Compiling DualRunner.java ..."
javac -d "$DIST" "$HERE/DualRunner.java"

if [[ -n "$JUNIT_JAR" ]]; then
  echo "Compiling JUnitTextRunner.java ..."
  javac -cp "$JUNIT_JAR:$HAMCREST_JAR" -d "$DIST" "$HERE/JUnitTextRunner.java"
else
  echo "Skipping JUnitTextRunner.java (no JUnit jar supplied)."
fi

echo "Packaging dualrunner.jar ..."
jar --create --file "$DIST/dualrunner.jar" -C "$DIST" DualRunner.class
if [[ -f "$DIST/JUnitTextRunner.class" ]]; then
  jar --update --file "$DIST/dualrunner.jar" -C "$DIST" JUnitTextRunner.class
fi

echo "Built: $DIST/dualrunner.jar"
