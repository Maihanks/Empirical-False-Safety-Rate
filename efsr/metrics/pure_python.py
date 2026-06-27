"""Source-level approximate structural metrics, as a ckjm fallback.

This backend parses Java *source* (via javalang) rather than compiled
bytecode, so it cannot see inherited members or fully resolve external
types. It exists so that Stage 3 (metric(T)) and the RQ3 predictor panel
can be exercised end-to-end -- including in environments without a
compiled ckjm jar -- but it is intentionally documented as an
approximation. Prefer `CkjmExtractor` against compiled bytecode for the
numbers actually reported in the study.

Approximations, by metric:
  CC   -- McCabe cyclomatic complexity of a named method (decision points + 1).
  WMC  -- sum of CC over all declared methods of the class (unit weighting).
  LOC  -- non-blank, non-comment-only source lines within the class body.
  CBO  -- count of distinct external (non-java.lang) simple type names
          referenced in fields, method signatures, and method bodies.
  CE   -- treated as equal to the CBO estimate above (efferent-only; ckjm
          additionally separates afferent coupling, which is not
          recoverable from a single source file in isolation).
  RFC  -- declared method count + count of distinct method-call names
          appearing in method bodies.
  LCOM -- Henderson-Sellers-style: pairs of methods that do NOT share a
          field access, divided by total method pairs (0 = fully cohesive
          by this proxy, 1 = fully non-cohesive).
  DIT  -- 1 if the class has no `extends` clause (root, below Object), else
          2 (one level of inheritance); deeper chains cannot be resolved
          without the full type hierarchy and are reported as 2 with a
          best-effort flag in the caller's notes.
"""
from __future__ import annotations

from pathlib import Path

import javalang

from efsr.metrics.types import StructuralMetrics

_JAVA_LANG_BUILTINS = {
    "String", "Object", "Integer", "Long", "Double", "Float", "Boolean",
    "Character", "Byte", "Short", "Void", "Math", "System", "Exception",
    "RuntimeException", "Throwable", "Error", "Number", "Comparable",
    "Iterable", "CharSequence", "StringBuilder", "StringBuffer",
    "int", "long", "double", "float", "boolean", "char", "byte", "short", "void",
}

_DECISION_NODE_TYPES = (
    javalang.tree.IfStatement,
    javalang.tree.ForStatement,
    javalang.tree.WhileStatement,
    javalang.tree.DoStatement,
    javalang.tree.CatchClause,
    javalang.tree.SwitchStatementCase,
    javalang.tree.TernaryExpression,
)
_BINARY_SHORT_CIRCUIT_OPS = {"&&", "||"}


def _method_cyclomatic_complexity(method_node) -> int:
    # javalang's Node.filter() only matches a single type (it does not
    # accept a tuple of types), so the decision-node check below is done
    # with a plain isinstance() over one walk of the subtree instead.
    complexity = 1
    for _, node in method_node:
        if isinstance(node, _DECISION_NODE_TYPES):
            complexity += 1
        elif isinstance(node, javalang.tree.BinaryOperation) and node.operator in _BINARY_SHORT_CIRCUIT_OPS:
            complexity += 1
    return complexity


def _count_loc(source: str, class_decl) -> int:
    lines = source.splitlines()
    count = 0
    in_block_comment = False
    for line in lines:
        stripped = line.strip()
        if in_block_comment:
            if "*/" in stripped:
                in_block_comment = False
            continue
        if not stripped:
            continue
        if stripped.startswith("/*"):
            in_block_comment = "*/" not in stripped
            continue
        if stripped.startswith("//"):
            continue
        count += 1
    return count


def _referenced_type_names(class_node) -> set[str]:
    names: set[str] = set()
    for _, node in class_node.filter(javalang.tree.ReferenceType):
        if node.name:
            names.add(node.name)
    for _, node in class_node.filter(javalang.tree.ClassCreator):
        if node.type and node.type.name:
            names.add(node.type.name)
    return {n for n in names if n not in _JAVA_LANG_BUILTINS}


def _method_call_names(method_node) -> set[str]:
    return {node.member for _, node in method_node.filter(javalang.tree.MethodInvocation)}


def _fields_referenced(method_node, field_names: set[str]) -> set[str]:
    refs: set[str] = set()
    for _, node in method_node.filter(javalang.tree.MemberReference):
        if node.member in field_names:
            refs.add(node.member)
    return refs


def _lcom_henderson_sellers(class_node, field_names: set[str]) -> float:
    methods = [m for m in class_node.methods]
    if len(methods) < 2 or not field_names:
        return 0.0
    field_usage = [_fields_referenced(m, field_names) for m in methods]
    total_pairs = 0
    disjoint_pairs = 0
    for i in range(len(methods)):
        for j in range(i + 1, len(methods)):
            total_pairs += 1
            if not (field_usage[i] & field_usage[j]):
                disjoint_pairs += 1
    return disjoint_pairs / total_pairs if total_pairs else 0.0


def _find_class(tree, class_name: str | None):
    classes = [
        node for _, node in tree.filter(javalang.tree.ClassDeclaration)
    ]
    if not classes:
        raise ValueError("no class declaration found in source")
    if class_name is None:
        return classes[0]
    for c in classes:
        if c.name == class_name:
            return c
    raise ValueError(f"class {class_name!r} not found among {[c.name for c in classes]}")


class PureJavaSourceExtractor:
    """Fallback metrics backend operating directly on .java source files."""

    def extract(self, java_file: Path, class_name: str | None = None,
                method_name: str | None = None) -> StructuralMetrics:
        source = Path(java_file).read_text()
        tree = javalang.parse.parse(source)
        class_node = _find_class(tree, class_name)

        field_names = {
            decl.name
            for f in class_node.fields
            for decl in f.declarators
        }

        method_ccs = []
        target_cc = None
        for m in class_node.methods:
            cc = _method_cyclomatic_complexity(m)
            method_ccs.append(cc)
            if method_name is not None and m.name == method_name:
                target_cc = cc
        if method_name is not None and target_cc is None:
            raise ValueError(f"method {method_name!r} not found in class {class_node.name!r}")

        wmc = float(sum(method_ccs)) if method_ccs else 0.0
        cc = float(target_cc) if target_cc is not None else (
            float(max(method_ccs)) if method_ccs else 0.0
        )

        coupling = _referenced_type_names(class_node)
        call_names = set()
        for m in class_node.methods:
            call_names |= _method_call_names(m)
        rfc = float(len(class_node.methods) + len(call_names))

        lcom = _lcom_henderson_sellers(class_node, field_names)
        dit = 1.0 if class_node.extends is None else 2.0
        loc = float(_count_loc(source, class_node))

        return StructuralMetrics(
            cc=cc, wmc=wmc, ce=float(len(coupling)), cbo=float(len(coupling)),
            rfc=rfc, lcom=lcom, dit=dit, loc=loc,
        )
