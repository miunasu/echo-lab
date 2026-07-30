"""
patterns package: individual detection pattern modules for agent-sink-scanner.

Each module exposes a single function:
    analyze(tree: ast.AST, source_lines: list[str], filename: str) -> list[Finding]

A Finding is a dict with keys:
    severity   : "HIGH" | "MEDIUM" | "INFO"
    title      : str
    filename   : str
    line       : int
    pattern    : str
    suggestion : str
    context    : str   (source line snippet)
"""

from .direct_sink import analyze as analyze_direct_sink
from .type_traversal import analyze as analyze_type_traversal
from .format_eval import analyze as analyze_format_eval
from .framework_audit import analyze as analyze_framework_audit

__all__ = [
    "analyze_direct_sink",
    "analyze_type_traversal",
    "analyze_format_eval",
    "analyze_framework_audit",
]