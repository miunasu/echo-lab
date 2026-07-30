"""
patterns/type_traversal.py
==========================
Category 2: Python type-system traversal attributes near eval/exec context.

Detects the presence of dangerous dunder/special attributes within the same
function body as an eval/exec call, within a configurable line window.

Dangerous attributes that enable sandbox escape via the MRO chain:
  __class__, __bases__, __subclasses__, __mro__,
  __globals__, __builtins__, __dict__,
  load_module, BuiltinImporter

If any of these appear within PROXIMITY_LINES of an eval/exec call inside the
same function, the finding is emitted.
"""

import ast
from typing import Any

PROXIMITY_LINES = 50

TRAVERSAL_ATTRS = {
    "__class__", "__bases__", "__subclasses__", "__mro__",
    "__globals__", "__builtins__", "__dict__",
    "load_module", "BuiltinImporter",
}

EXEC_SINKS = {"eval", "exec"}


def _get_source_line(source_lines: list[str], lineno: int) -> str:
    if 1 <= lineno <= len(source_lines):
        return source_lines[lineno - 1].rstrip()
    return ""


def _collect_eval_lines(func_node: ast.AST) -> list[int]:
    """Return line numbers of eval/exec calls within a function."""
    lines = []
    for node in ast.walk(func_node):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in EXEC_SINKS:
                lines.append(node.lineno)
            elif isinstance(func, ast.Attribute) and func.attr in EXEC_SINKS:
                lines.append(node.lineno)
    return lines


def _collect_traversal_uses(func_node: ast.AST) -> list[tuple[int, str]]:
    """Return (lineno, attr_name) for each traversal attribute use in the function."""
    uses = []
    for node in ast.walk(func_node):
        # attribute access: x.__class__, x.__subclasses__()
        if isinstance(node, ast.Attribute) and node.attr in TRAVERSAL_ATTRS:
            uses.append((node.lineno, node.attr))
        # name reference: BuiltinImporter used as a bare name
        elif isinstance(node, ast.Name) and node.id in TRAVERSAL_ATTRS:
            uses.append((node.lineno, node.id))
        # string constants that name traversal attrs (used in getattr calls)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and node.value in TRAVERSAL_ATTRS:
            uses.append((node.lineno, node.value))
    return uses


def analyze(tree: ast.AST, source_lines: list[str], filename: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    emitted: set[tuple[int, str]] = set()

    # Walk top-level and nested function/async function definitions
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        eval_lines = _collect_eval_lines(node)
        if not eval_lines:
            continue

        traversal_uses = _collect_traversal_uses(node)
        if not traversal_uses:
            continue

        for trav_line, attr_name in traversal_uses:
            for eval_line in eval_lines:
                distance = abs(trav_line - eval_line)
                if distance <= PROXIMITY_LINES:
                    key = (trav_line, attr_name)
                    if key in emitted:
                        break
                    emitted.add(key)
                    findings.append({
                        "severity": "MEDIUM",
                        "title": f"Type traversal attribute '{attr_name}' near eval/exec (distance={distance} lines)",
                        "filename": filename,
                        "line": trav_line,
                        "pattern": "type-traversal: dunder-attr near eval",
                        "suggestion": (
                            "Audit whether eval/exec context allows access to type-system attributes; "
                            "consider restricting __globals__ and __builtins__ passed to eval(), "
                            "or replacing eval/exec with a safe interpreter"
                        ),
                        "context": _get_source_line(source_lines, trav_line),
                    })
                    break

    return findings