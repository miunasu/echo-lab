"""
patterns/framework_audit.py
============================
Categories 4 & 5: Framework-specific annotation auditing and AST blocklist detection.

Category 4 - Framework annotation audit:
  Detects methods decorated with @kernel_function / @KernelFunction
  (Semantic Kernel) and checks whether their parameters flow directly into
  dangerous sink calls (eval, exec, os.system, subprocess.*, open-write).

Category 5 - AST blocklist vulnerability:
  Detects the pattern:
    ast.parse(...)  ->  blocklist check  ->  eval/exec
  and flags it as a weak defense. Allowlist-based validation should be used
  instead. Detection heuristic: a function that calls both ast.parse (or
  compile) AND eval/exec AND contains at least one comparison or membership
  test (the blocklist check).
"""

import ast
from typing import Any


KERNEL_DECORATORS = {"kernel_function", "KernelFunction", "kernel_function_context_parameter"}

DIRECT_SINKS = {"eval", "exec"}

ATTR_SINKS: dict[str, set[str]] = {
    "os": {"system", "popen"},
    "subprocess": {"run", "call", "Popen", "check_output", "check_call", "getoutput", "getstatusoutput"},
}

WRITE_MODES = {"w", "wb", "a", "ab", "x", "xb", "wt", "at", "xt"}


def _get_source_line(source_lines: list[str], lineno: int) -> str:
    if 1 <= lineno <= len(source_lines):
        return source_lines[lineno - 1].rstrip()
    return ""


def _decorator_names(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Extract simple decorator names from a function definition."""
    names = []
    for dec in func_node.decorator_list:
        if isinstance(dec, ast.Name):
            names.append(dec.id)
        elif isinstance(dec, ast.Attribute):
            names.append(dec.attr)
        elif isinstance(dec, ast.Call):
            inner = dec.func
            if isinstance(inner, ast.Name):
                names.append(inner.id)
            elif isinstance(inner, ast.Attribute):
                names.append(inner.attr)
    return names


def _get_param_names(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    args = func_node.args
    names: set[str] = set()
    for arg in args.args + args.posonlyargs + args.kwonlyargs:
        names.add(arg.arg)
    if args.vararg:
        names.add(args.vararg.arg)
    if args.kwarg:
        names.add(args.kwarg.arg)
    return names


def _call_uses_name(call_node: ast.Call, param_names: set[str]) -> bool:
    """Return True if any argument of the call references one of the param names."""
    for arg in ast.walk(call_node):
        if isinstance(arg, ast.Name) and arg.id in param_names:
            return True
    return False


def _is_sink_call(node: ast.Call) -> tuple[bool, str]:
    """Return (True, sink_description) if the call is a dangerous sink."""
    func = node.func
    if isinstance(func, ast.Name) and func.id in DIRECT_SINKS:
        return True, func.id
    if isinstance(func, ast.Attribute):
        if func.attr in DIRECT_SINKS:
            return True, func.attr
        obj = func.value
        if isinstance(obj, ast.Name) and obj.id in ATTR_SINKS:
            if func.attr in ATTR_SINKS[obj.id]:
                return True, f"{obj.id}.{func.attr}"
    # open() write mode
    if isinstance(func, ast.Name) and func.id == "open":
        for i, arg in enumerate(node.args):
            if i == 1 and isinstance(arg, ast.Constant) and arg.value in WRITE_MODES:
                return True, "open(write)"
        for kw in node.keywords:
            if kw.arg == "mode" and isinstance(kw.value, ast.Constant) and kw.value.value in WRITE_MODES:
                return True, "open(write)"
    return False, ""


# ---------------------------------------------------------------------------
# Category 4
# ---------------------------------------------------------------------------

def _audit_kernel_function(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    source_lines: list[str],
    filename: str,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    dec_names = _decorator_names(func_node)
    has_kernel_decorator = any(d in KERNEL_DECORATORS for d in dec_names)

    if not has_kernel_decorator:
        return findings

    # Always emit an INFO finding for the annotation itself
    findings.append({
        "severity": "INFO",
        "title": f"@kernel_function annotation on method '{func_node.name}'",
        "filename": filename,
        "line": func_node.lineno,
        "pattern": "framework-audit: kernel-function annotation",
        "suggestion": (
            "Verify this method should be AI-callable. "
            "Ensure all parameters are validated before use. "
            "CVE-2026-25592: mis-annotated methods expose internal operations to AI callers."
        ),
        "context": _get_source_line(source_lines, func_node.lineno),
    })

    param_names = _get_param_names(func_node)
    param_names.discard("self")
    param_names.discard("cls")

    if not param_names:
        return findings

    # Check if any parameter flows into a sink
    for node in ast.walk(func_node):
        if not isinstance(node, ast.Call):
            continue
        is_sink, sink_desc = _is_sink_call(node)
        if not is_sink:
            continue
        if _call_uses_name(node, param_names):
            findings.append({
                "severity": "HIGH",
                "title": (
                    f"@kernel_function method '{func_node.name}': "
                    f"parameter flows into {sink_desc}()"
                ),
                "filename": filename,
                "line": node.lineno,
                "pattern": "framework-audit: kernel-function-param -> sink",
                "suggestion": (
                    f"Method '{func_node.name}' is AI-callable via @kernel_function. "
                    f"Parameter passed to {sink_desc}() must be strictly validated or this "
                    "method should not be exposed to AI input."
                ),
                "context": _get_source_line(source_lines, node.lineno),
            })

    return findings


# ---------------------------------------------------------------------------
# Category 5
# ---------------------------------------------------------------------------

def _has_ast_parse_call(func_node: ast.AST) -> bool:
    for node in ast.walk(func_node):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in ("parse", "parse_expr"):
                obj = func.value
                if isinstance(obj, ast.Name) and obj.id == "ast":
                    return True
            # compile() is also used in parse-then-eval patterns
            if isinstance(func, ast.Name) and func.id == "compile":
                return True
    return False


def _has_eval_exec_call(func_node: ast.AST) -> bool:
    for node in ast.walk(func_node):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in DIRECT_SINKS:
                return True
            if isinstance(func, ast.Attribute) and func.attr in DIRECT_SINKS:
                return True
    return False


def _has_blocklist_check(func_node: ast.AST) -> bool:
    """
    Heuristic: function contains a comparison or membership test that looks
    like a blocklist check. We look for:
      - 'in' / 'not in' membership tests against a set/list/tuple/variable
      - string literals that look like attribute names (e.g. '__import__')
    """
    for node in ast.walk(func_node):
        if isinstance(node, ast.Compare):
            for op in node.ops:
                if isinstance(op, (ast.In, ast.NotIn)):
                    return True
        # Also accept any if-statement containing a string check
        if isinstance(node, ast.If):
            for child in ast.walk(node.test):
                if isinstance(child, ast.Constant) and isinstance(child.value, str):
                    if child.value.startswith("__") or child.value in (
                        "import", "eval", "exec", "open", "system"
                    ):
                        return True
    return False


def _find_eval_line(func_node: ast.AST) -> int:
    for node in ast.walk(func_node):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in DIRECT_SINKS:
                return node.lineno
            if isinstance(func, ast.Attribute) and func.attr in DIRECT_SINKS:
                return node.lineno
    return getattr(func_node, "lineno", 0)


def _audit_blocklist_pattern(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    source_lines: list[str],
    filename: str,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    if not (_has_ast_parse_call(func_node) and _has_eval_exec_call(func_node)):
        return findings

    if not _has_blocklist_check(func_node):
        return findings

    eval_line = _find_eval_line(func_node)
    findings.append({
        "severity": "HIGH",
        "title": (
            f"AST blocklist pattern in '{func_node.name}': "
            "ast.parse -> blocklist check -> eval/exec"
        ),
        "filename": filename,
        "line": eval_line,
        "pattern": "framework-audit: ast-blocklist -> eval",
        "suggestion": (
            "Blocklist-based AST validation is inherently fragile in Python "
            "(type traversal, indirect attribute access, __subclasses__ chains). "
            "Replace with an allowlist approach: define exactly which AST node types "
            "and attribute names are permitted, and reject everything else."
        ),
        "context": _get_source_line(source_lines, eval_line),
    })
    return findings


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def analyze(tree: ast.AST, source_lines: list[str], filename: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            findings.extend(_audit_kernel_function(node, source_lines, filename))
            findings.extend(_audit_blocklist_pattern(node, source_lines, filename))

    return findings