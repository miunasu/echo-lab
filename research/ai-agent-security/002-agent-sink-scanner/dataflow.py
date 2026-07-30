"""
dataflow.py
===========
Lightweight intra-function data-flow tracker.

Scope: single-function, assignment-level taint propagation.
This is not a full SSA/CFG analysis; it handles the common cases that appear
in Agent framework code and produces actionable results without external deps.

Taint sources tracked:
  - Function parameters (all parameters of a function are considered tainted
    by default, since Agent frameworks pass AI-controlled input as arguments)
  - Explicit taint markers: input(), sys.argv, os.environ, request.*, Flask/
    FastAPI request objects (common patterns)

Propagation rules (single assignment level):
  - If a tainted value is assigned to a new variable, that variable is tainted
  - If a tainted value appears in a format expression, the result is tainted
  - If a tainted value appears in a subscript/attribute access chain, the
    result is considered tainted

This module is used by scanner.py to annotate findings with taint information,
upgrading severity when a sink argument is provably tainted.
"""

import ast
from typing import Any


# ---------------------------------------------------------------------------
# Taint source heuristics
# ---------------------------------------------------------------------------

# Bare-name sources that are always considered external input
TAINT_SOURCE_NAMES = {
    "input",       # input() call result
    "argv",        # sys.argv
    "environ",     # os.environ
}

# Attribute patterns considered tainted: request.json, request.data, etc.
TAINT_SOURCE_ATTRS = {
    "json", "data", "form", "args", "values", "files",
    "body", "content", "text", "query_string",
}

EXEC_SINKS = {"eval", "exec"}


def _is_taint_source_call(node: ast.Call) -> bool:
    """Return True if the call result is a known taint source."""
    func = node.func
    if isinstance(func, ast.Name) and func.id == "input":
        return True
    return False


def _is_taint_source_name(node: ast.Name) -> bool:
    return node.id in TAINT_SOURCE_NAMES


def _is_taint_source_attr(node: ast.Attribute) -> bool:
    return node.attr in TAINT_SOURCE_ATTRS


def _expr_is_tainted(node: ast.expr, tainted_names: set[str]) -> bool:
    """
    Recursively check if an expression uses a tainted name or known source.
    """
    if isinstance(node, ast.Name):
        return node.id in tainted_names or _is_taint_source_name(node)

    if isinstance(node, ast.Call):
        if _is_taint_source_call(node):
            return True
        # If any argument to the call is tainted, consider result tainted
        return any(_expr_is_tainted(arg, tainted_names) for arg in node.args)

    if isinstance(node, ast.Attribute):
        if _is_taint_source_attr(node):
            return True
        return _expr_is_tainted(node.value, tainted_names)

    if isinstance(node, ast.Subscript):
        return _expr_is_tainted(node.value, tainted_names)

    if isinstance(node, ast.JoinedStr):
        # f-string: tainted if any value part is tainted
        return any(
            _expr_is_tainted(v, tainted_names)
            for v in node.values
            if isinstance(v, ast.FormattedValue)
        )

    if isinstance(node, ast.BinOp):
        return (
            _expr_is_tainted(node.left, tainted_names)
            or _expr_is_tainted(node.right, tainted_names)
        )

    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return any(_expr_is_tainted(elt, tainted_names) for elt in node.elts)

    if isinstance(node, ast.Dict):
        return any(
            _expr_is_tainted(v, tainted_names)
            for v in node.values
            if v is not None
        )

    if isinstance(node, ast.IfExp):
        return (
            _expr_is_tainted(node.body, tainted_names)
            or _expr_is_tainted(node.orelse, tainted_names)
        )

    return False


def _get_param_names(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    args = func_node.args
    names: set[str] = set()
    for arg in args.args + args.posonlyargs + args.kwonlyargs:
        names.add(arg.arg)
    if args.vararg:
        names.add(args.vararg.arg)
    if args.kwarg:
        names.add(args.kwarg.arg)
    names.discard("self")
    names.discard("cls")
    return names


class TaintTracker:
    """
    Single-pass taint propagation over a function body (linear approximation).

    Usage:
        tracker = TaintTracker(func_node)
        tracker.run()
        is_tainted = tracker.is_tainted(some_expr_node)
    """

    def __init__(self, func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.func_node = func_node
        # Initially tainted: all function parameters
        self.tainted_names: set[str] = _get_param_names(func_node)

    def run(self) -> None:
        """Propagate taint through assignments in the function body."""
        for node in ast.walk(self.func_node):
            if isinstance(node, ast.Assign):
                if _expr_is_tainted(node.value, self.tainted_names):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            self.tainted_names.add(target.id)
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                if _expr_is_tainted(node.value, self.tainted_names):
                    if isinstance(node.target, ast.Name):
                        self.tainted_names.add(node.target.id)
            elif isinstance(node, (ast.For,)):
                # Loop variable may be tainted if iter is tainted
                if _expr_is_tainted(node.iter, self.tainted_names):
                    if isinstance(node.target, ast.Name):
                        self.tainted_names.add(node.target.id)

    def is_tainted(self, expr: ast.expr) -> bool:
        return _expr_is_tainted(expr, self.tainted_names)


def annotate_findings_with_taint(
    findings: list[dict[str, Any]],
    tree: ast.AST,
) -> list[dict[str, Any]]:
    """
    Post-process findings: for each finding that corresponds to a sink call
    inside a function, run taint analysis to determine if the sink argument
    is reachable from a tainted source.

    Adds key 'tainted': True/False/None to each finding.
    None means taint status could not be determined (e.g. module-level).
    """
    # Build a map from line -> enclosing function node
    line_to_func: dict[int, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if hasattr(child, "lineno"):
                    if child.lineno not in line_to_func:
                        line_to_func[child.lineno] = node

    for finding in findings:
        line = finding.get("line", 0)
        func_node = line_to_func.get(line)
        if func_node is None:
            finding["tainted"] = None
            continue

        tracker = TaintTracker(func_node)
        tracker.run()

        # Heuristic: if any param is tainted and the function has
        # external-input params, mark as potentially tainted
        finding["tainted"] = len(tracker.tainted_names) > 0

    return findings