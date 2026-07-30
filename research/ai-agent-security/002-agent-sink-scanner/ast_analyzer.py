"""
ast_analyzer.py
===============
Core AST analysis engine.

Parses a Python source file and runs all pattern modules against the AST.
Returns a flat list of findings sorted by (filename, line).
"""

import ast
import os
from typing import Any

from patterns import (
    analyze_direct_sink,
    analyze_type_traversal,
    analyze_format_eval,
    analyze_framework_audit,
)


class ParseError(Exception):
    """Raised when a source file cannot be parsed."""


def analyze_file(
    filepath: str,
    framework: str | None = None,
) -> list[dict[str, Any]]:
    """
    Parse `filepath` and run all detectors against it.

    Parameters
    ----------
    filepath  : absolute or relative path to a .py file
    framework : optional framework hint ('semantic-kernel', 'langchain', etc.)
                currently used for display/context; future versions may
                activate framework-specific rules based on this value

    Returns
    -------
    List of finding dicts, each with keys:
        severity, title, filename, line, pattern, suggestion, context
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
            source = fh.read()
    except OSError as exc:
        raise ParseError(f"Cannot read file: {exc}") from exc

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError as exc:
        raise ParseError(f"Syntax error in {filepath}: {exc}") from exc

    source_lines = source.splitlines()
    filename = os.path.normpath(filepath)

    findings: list[dict[str, Any]] = []
    findings.extend(analyze_direct_sink(tree, source_lines, filename))
    findings.extend(analyze_type_traversal(tree, source_lines, filename))
    findings.extend(analyze_format_eval(tree, source_lines, filename))
    findings.extend(analyze_framework_audit(tree, source_lines, filename))

    # Sort by line number for readable output
    findings.sort(key=lambda f: f.get("line", 0))
    return findings


def analyze_source(
    source: str,
    filename: str = "<string>",
    framework: str | None = None,
) -> list[dict[str, Any]]:
    """
    Analyze Python source provided as a string (useful for testing).
    """
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        raise ParseError(f"Syntax error: {exc}") from exc

    source_lines = source.splitlines()

    findings: list[dict[str, Any]] = []
    findings.extend(analyze_direct_sink(tree, source_lines, filename))
    findings.extend(analyze_type_traversal(tree, source_lines, filename))
    findings.extend(analyze_format_eval(tree, source_lines, filename))
    findings.extend(analyze_framework_audit(tree, source_lines, filename))

    findings.sort(key=lambda f: f.get("line", 0))
    return findings