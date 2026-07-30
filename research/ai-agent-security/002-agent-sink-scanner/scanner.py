"""
scanner.py
==========
agent-sink-scanner: main entry point.

Detects dangerous execution paths in Python Agent framework code.

Usage:
  python scanner.py path/to/dir
  python scanner.py path/to/file.py
  python scanner.py path/to/dir --format json
  python scanner.py path/to/dir --format markdown --output report.md
  python scanner.py path/to/dir --framework semantic-kernel
  python scanner.py path/to/dir --severity HIGH
  python scanner.py path/to/dir --no-taint
"""

import argparse
import os
import sys
from typing import Any

from ast_analyzer import analyze_file, ParseError
from dataflow import annotate_findings_with_taint
import ast
from report import print_render


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

SKIP_DIRS = {
    "__pycache__", ".git", ".hg", ".svn", ".tox",
    ".venv", "venv", "env", ".env",
    "node_modules", ".mypy_cache", ".pytest_cache",
    "dist", "build", "*.egg-info",
}


def _collect_python_files(path: str) -> list[str]:
    """
    Recursively collect all .py files under `path`.
    Skips common non-source directories.
    """
    if os.path.isfile(path):
        if path.endswith(".py"):
            return [path]
        print(f"Warning: {path} is not a Python file.", file=sys.stderr)
        return []

    py_files: list[str] = []
    for root, dirs, files in os.walk(path):
        # Prune skip directories in-place
        dirs[:] = [
            d for d in dirs
            if d not in SKIP_DIRS and not d.endswith(".egg-info")
        ]
        for fname in files:
            if fname.endswith(".py"):
                py_files.append(os.path.join(root, fname))

    return sorted(py_files)


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

def scan(
    target: str,
    framework: str | None = None,
    severity_filter: str | None = None,
    enable_taint: bool = True,
) -> tuple[list[dict[str, Any]], int, list[str]]:
    """
    Scan a file or directory and return (findings, files_scanned, errors).

    Parameters
    ----------
    target          : path to file or directory
    framework       : optional framework hint
    severity_filter : if set, only return findings at this severity or higher
    enable_taint    : whether to run taint annotation pass

    Returns
    -------
    (findings, files_scanned, parse_errors)
    """
    py_files = _collect_python_files(target)
    if not py_files:
        print(f"No Python files found under: {target}", file=sys.stderr)
        return [], 0, []

    all_findings: list[dict[str, Any]] = []
    errors: list[str] = []

    for filepath in py_files:
        try:
            findings = analyze_file(filepath, framework=framework)
        except ParseError as exc:
            errors.append(str(exc))
            continue

        if enable_taint and findings:
            try:
                with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
                    source = fh.read()
                tree = ast.parse(source, filename=filepath)
                findings = annotate_findings_with_taint(findings, tree)
            except Exception:
                pass  # Taint annotation is best-effort; don't fail the scan

        all_findings.extend(findings)

    # Apply severity filter
    if severity_filter:
        order = {"HIGH": 0, "MEDIUM": 1, "INFO": 2}
        max_level = order.get(severity_filter.upper(), 2)
        all_findings = [
            f for f in all_findings
            if order.get(f.get("severity", "INFO"), 2) <= max_level
        ]

    return all_findings, len(py_files), errors


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scanner",
        description=(
            "agent-sink-scanner: detect dangerous execution paths in Python "
            "Agent framework code (eval/exec sinks, type-traversal, format-string "
            "injection, framework annotation auditing)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python scanner.py .
  python scanner.py src/
  python scanner.py plugin.py --format json
  python scanner.py . --format markdown --output report.md
  python scanner.py . --framework semantic-kernel
  python scanner.py . --severity HIGH
  python scanner.py . --no-taint
""",
    )

    parser.add_argument(
        "target",
        metavar="PATH",
        help="Python file or directory to scan",
    )
    parser.add_argument(
        "--format",
        choices=["terminal", "json", "markdown"],
        default="terminal",
        dest="fmt",
        help="Output format (default: terminal)",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        default=None,
        help="Write report to FILE instead of stdout",
    )
    parser.add_argument(
        "--framework",
        metavar="NAME",
        default=None,
        help="Framework hint: semantic-kernel | langchain | custom",
    )
    parser.add_argument(
        "--severity",
        metavar="LEVEL",
        default=None,
        choices=["HIGH", "MEDIUM", "INFO"],
        help="Only report findings at this severity level or higher",
    )
    parser.add_argument(
        "--no-taint",
        action="store_true",
        default=False,
        help="Disable taint propagation annotation pass",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="agent-sink-scanner 0.1.0",
    )

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    target = os.path.abspath(args.target)
    if not os.path.exists(target):
        print(f"Error: path does not exist: {target}", file=sys.stderr)
        return 2

    findings, files_scanned, errors = scan(
        target=target,
        framework=args.framework,
        severity_filter=args.severity,
        enable_taint=not args.no_taint,
    )

    print_render(
        findings=findings,
        files_scanned=files_scanned,
        errors=errors,
        fmt=args.fmt,
        output_file=args.output,
    )

    # Exit code: 1 if any HIGH findings, 0 otherwise
    has_high = any(f.get("severity") == "HIGH" for f in findings)
    return 1 if has_high else 0


if __name__ == "__main__":
    sys.exit(main())