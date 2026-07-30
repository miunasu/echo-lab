"""
patterns/format_eval.py
=======================
Category 3: Format-string + eval/exec data-flow combination.

Detects patterns where a string is built via:
  - f-string (ast.JoinedStr)
  - str.format() call
  - % string formatting (ast.BinOp with ast.Mod on a str)
  - string concatenation (ast.BinOp with ast.Add)

...and the result is then directly passed to eval() or exec(), or assigned
to a variable that is subsequently passed to eval/exec within the same
function scope (single-level local variable tracking).

This is the root cause pattern of CVE-2026-26030:
    template = f"lambda x: x.field == '{user_input}'"
    eval(template)
"""

import ast
from typing import Any


EXEC_SINKS = {"eval", "exec"}


def _get_source_line(source_lines: list[str], lineno: int) -> str:
    if 1 <= lineno <= len(source_lines):
        return source_lines[lineno - 1].rstrip()
    return ""


def _is_format_expr(node: ast.expr) -> tuple[bool, str]:
    """
    Return (True, description) if the node is a format-string expression.
    Covers:
      - f-strings (JoinedStr)
      - "...".format(...) calls
      - "..." % ... (BinOp Mod)
      - str + str concatenation (BinOp Add, at least one side is non-constant)
    """
    if isinstance(node, ast.JoinedStr):
        return True, "f-string"

    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "format":
            return True, "str.format()"

    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Mod):
            # Only flag if left side looks like a string
            if isinstance(node.left, (ast.Constant, ast.JoinedStr)):
                return True, "%-format"
        if isinstance(node.op, ast.Add):
            # String concatenation: flag if either side is non-trivial
            left_const = isinstance(node.left, ast.Constant) and isinstance(node.left.value, str)
            right_const = isinstance(node.right, ast.Constant) and isinstance(node.right.value, str)
            if not (left_const and right_const):
                return True, "string concatenation"

    return False, ""


def _is_eval_call(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Name) and func.id in EXEC_SINKS:
        return True
    if isinstance(func, ast.Attribute) and func.attr in EXEC_SINKS:
        return True
    return False


def _get_call_first_arg(node: ast.Call) -> ast.expr | None:
    if node.args:
        return node.args[0]
    for kw in node.keywords:
        if kw.arg in ("source", "expression", None):
            return kw.value
    return None


def _analyze_function(
    func_node: ast.AST,
    source_lines: list[str],
    filename: str,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    # Map: variable name -> (lineno, format_description)
    # Tracks simple assignments like:  varname = <format-expr>
    assigned_format_vars: dict[str, tuple[int, str]] = {}

    # First pass: collect assignments of format expressions to names
    for node in ast.walk(func_node):
        if isinstance(node, ast.Assign):
            is_fmt, fmt_desc = _is_format_expr(node.value)
            if is_fmt:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assigned_format_vars[target.id] = (node.lineno, fmt_desc)

        elif isinstance(node, (ast.AnnAssign,)):
            if node.value is not None:
                is_fmt, fmt_desc = _is_format_expr(node.value)
                if is_fmt and isinstance(node.target, ast.Name):
                    assigned_format_vars[node.target.id] = (node.lineno, fmt_desc)

    # Second pass: find eval/exec calls
    for node in ast.walk(func_node):
        if not isinstance(node, ast.Call):
            continue
        if not _is_eval_call(node):
            continue

        arg = _get_call_first_arg(node)
        if arg is None:
            continue

        sink_name = (
            node.func.id if isinstance(node.func, ast.Name)
            else node.func.attr
        )

        # Case A: format expression directly passed to eval/exec
        is_fmt, fmt_desc = _is_format_expr(arg)
        if is_fmt:
            findings.append({
                "severity": "HIGH",
                "title": f"{fmt_desc} result passed directly to {sink_name}()",
                "filename": filename,
                "line": node.lineno,
                "pattern": f"format-string -> {sink_name}",
                "suggestion": (
                    f"Replace {sink_name}() with an AST allowlist + safe interpreter; "
                    "never pass user-controlled or dynamically-built strings to eval/exec"
                ),
                "context": _get_source_line(source_lines, node.lineno),
            })
            continue

        # Case B: variable holding a format expression passed to eval/exec
        if isinstance(arg, ast.Name) and arg.id in assigned_format_vars:
            assign_line, fmt_desc = assigned_format_vars[arg.id]
            findings.append({
                "severity": "HIGH",
                "title": f"Variable built via {fmt_desc} flows into {sink_name}()",
                "filename": filename,
                "line": node.lineno,
                "pattern": f"format-string -> variable -> {sink_name}",
                "suggestion": (
                    f"Replace {sink_name}() with an AST allowlist + safe interpreter; "
                    f"variable assigned at line {assign_line} is built from a format expression"
                ),
                "context": _get_source_line(source_lines, node.lineno),
            })

    return findings


def analyze(tree: ast.AST, source_lines: list[str], filename: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    # Analyze each function scope independently for variable tracking
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            findings.extend(_analyze_function(node, source_lines, filename))

    # Also check module-level statements (outside any function)
    findings.extend(_analyze_function(tree, source_lines, filename))

    # Deduplicate by (filename, line, pattern)
    seen: set[tuple[str, int, str]] = set()
    deduped = []
    for f in findings:
        key = (f["filename"], f["line"], f["pattern"])
        if key not in seen:
            seen.add(key)
            deduped.append(f)

    return deduped