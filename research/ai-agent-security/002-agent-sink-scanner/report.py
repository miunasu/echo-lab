"""
report.py
=========
Output formatting for agent-sink-scanner findings.

Supports three output modes:
  terminal  : colored human-readable output (default)
  json      : machine-readable JSON array
  markdown  : Markdown document suitable for GitHub / reports
"""

import json
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Colorama: optional dependency for terminal colors.
# If not installed, fall back to plain text.
# ---------------------------------------------------------------------------
try:
    import colorama
    from colorama import Fore, Style
    colorama.init(autoreset=True)
    _COLOR_AVAILABLE = True
except ImportError:
    _COLOR_AVAILABLE = False

    class _NoColor:
        """Stub that returns empty strings for any attribute."""
        def __getattr__(self, _: str) -> str:
            return ""

    Fore = _NoColor()   # type: ignore[assignment]
    Style = _NoColor()  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Severity styling
# ---------------------------------------------------------------------------

SEVERITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "INFO": 2}

_SEVERITY_COLOR = {
    "HIGH":   Fore.RED,
    "MEDIUM": Fore.YELLOW,
    "INFO":   Fore.CYAN,
}

_SEVERITY_SYMBOL = {
    "HIGH":   "!",
    "MEDIUM": "*",
    "INFO":   "i",
}


def _sev_label(severity: str) -> str:
    color = _SEVERITY_COLOR.get(severity, "")
    reset = Style.RESET_ALL if _COLOR_AVAILABLE else ""
    sym = _SEVERITY_SYMBOL.get(severity, "-")
    return f"{color}[{sym}] {severity}{reset}"


# ---------------------------------------------------------------------------
# Terminal format
# ---------------------------------------------------------------------------

def _format_terminal(findings: list[dict[str, Any]], show_taint: bool = True) -> str:
    if not findings:
        return f"{Fore.GREEN}No findings.{Style.RESET_ALL}\n"

    lines: list[str] = []
    for f in findings:
        sev = f.get("severity", "INFO")
        label = _sev_label(sev)
        title = f.get("title", "")
        filename = f.get("filename", "")
        line = f.get("line", 0)
        pattern = f.get("pattern", "")
        suggestion = f.get("suggestion", "")
        context = f.get("context", "").strip()
        tainted = f.get("tainted")

        lines.append(f"{label} {title}")
        lines.append(f"  File: {filename}, line {line}")
        lines.append(f"  Pattern: {pattern}")

        if show_taint and tainted is not None:
            taint_str = "yes (parameter taint)" if tainted else "no (conservative)"
            lines.append(f"  Tainted input: {taint_str}")

        if context:
            dim = Style.DIM if _COLOR_AVAILABLE else ""
            reset = Style.RESET_ALL if _COLOR_AVAILABLE else ""
            lines.append(f"  Code: {dim}{context}{reset}")

        lines.append(f"  Suggestion: {suggestion}")
        lines.append("")

    return "\n".join(lines)


def _format_summary_terminal(
    findings: list[dict[str, Any]],
    files_scanned: int,
    errors: list[str],
) -> str:
    high = sum(1 for f in findings if f.get("severity") == "HIGH")
    medium = sum(1 for f in findings if f.get("severity") == "MEDIUM")
    info = sum(1 for f in findings if f.get("severity") == "INFO")
    total = len(findings)

    bold = Style.BRIGHT if _COLOR_AVAILABLE else ""
    reset = Style.RESET_ALL if _COLOR_AVAILABLE else ""

    parts = [
        f"{bold}--- Summary ---{reset}",
        f"Files scanned : {files_scanned}",
        f"Total findings: {total}",
        f"  {_SEVERITY_COLOR.get('HIGH', '')}HIGH  : {high}{Style.RESET_ALL if _COLOR_AVAILABLE else ''}",
        f"  {_SEVERITY_COLOR.get('MEDIUM', '')}MEDIUM: {medium}{Style.RESET_ALL if _COLOR_AVAILABLE else ''}",
        f"  {_SEVERITY_COLOR.get('INFO', '')}INFO  : {info}{Style.RESET_ALL if _COLOR_AVAILABLE else ''}",
    ]
    if errors:
        parts.append(f"Parse errors  : {len(errors)}")
        for err in errors[:5]:
            parts.append(f"  {err}")
        if len(errors) > 5:
            parts.append(f"  ... and {len(errors) - 5} more")

    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# JSON format
# ---------------------------------------------------------------------------

def _format_json(
    findings: list[dict[str, Any]],
    files_scanned: int,
    errors: list[str],
) -> str:
    output = {
        "summary": {
            "files_scanned": files_scanned,
            "total": len(findings),
            "high": sum(1 for f in findings if f.get("severity") == "HIGH"),
            "medium": sum(1 for f in findings if f.get("severity") == "MEDIUM"),
            "info": sum(1 for f in findings if f.get("severity") == "INFO"),
            "parse_errors": len(errors),
        },
        "findings": findings,
        "errors": errors,
    }
    return json.dumps(output, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Markdown format
# ---------------------------------------------------------------------------

def _md_escape(text: str) -> str:
    for ch in ("\\", "`", "*", "_", "{", "}", "[", "]", "(", ")", "#", "+", "-", ".", "!"):
        text = text.replace(ch, "\\" + ch)
    return text


def _format_markdown(
    findings: list[dict[str, Any]],
    files_scanned: int,
    errors: list[str],
) -> str:
    high = sum(1 for f in findings if f.get("severity") == "HIGH")
    medium = sum(1 for f in findings if f.get("severity") == "MEDIUM")
    info = sum(1 for f in findings if f.get("severity") == "INFO")

    lines: list[str] = [
        "# agent-sink-scanner Report",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Files scanned | {files_scanned} |",
        f"| HIGH findings | {high} |",
        f"| MEDIUM findings | {medium} |",
        f"| INFO findings | {info} |",
        f"| Parse errors | {len(errors)} |",
        "",
    ]

    if not findings:
        lines.append("No findings detected.")
        return "\n".join(lines)

    lines.append("## Findings")
    lines.append("")

    severity_groups = {"HIGH": [], "MEDIUM": [], "INFO": []}
    for f in findings:
        sev = f.get("severity", "INFO")
        severity_groups.setdefault(sev, []).append(f)

    for sev in ("HIGH", "MEDIUM", "INFO"):
        group = severity_groups.get(sev, [])
        if not group:
            continue
        lines.append(f"### {sev}")
        lines.append("")
        for i, f in enumerate(group, 1):
            title = f.get("title", "")
            filename = f.get("filename", "")
            line = f.get("line", 0)
            pattern = f.get("pattern", "")
            suggestion = f.get("suggestion", "")
            context = f.get("context", "").strip()

            lines.append(f"#### {i}. {_md_escape(title)}")
            lines.append("")
            lines.append(f"- **File:** `{filename}`, line {line}")
            lines.append(f"- **Pattern:** `{pattern}`")
            if context:
                lines.append(f"- **Code:**")
                lines.append(f"  ```python")
                lines.append(f"  {context}")
                lines.append(f"  ```")
            lines.append(f"- **Suggestion:** {_md_escape(suggestion)}")
            lines.append("")

    if errors:
        lines.append("## Parse Errors")
        lines.append("")
        for err in errors:
            lines.append(f"- `{_md_escape(err)}`")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render(
    findings: list[dict[str, Any]],
    files_scanned: int = 0,
    errors: list[str] | None = None,
    fmt: str = "terminal",
    output_file: str | None = None,
) -> str:
    """
    Render findings to a string in the requested format.

    Parameters
    ----------
    findings      : list of finding dicts from ast_analyzer
    files_scanned : number of Python files analyzed
    errors        : list of parse error messages
    fmt           : 'terminal', 'json', or 'markdown'
    output_file   : if provided, write result to this path

    Returns
    -------
    Rendered string (also written to output_file if specified).
    """
    errors = errors or []
    findings_sorted = sorted(
        findings,
        key=lambda f: (SEVERITY_ORDER.get(f.get("severity", "INFO"), 99), f.get("filename", ""), f.get("line", 0)),
    )

    if fmt == "json":
        result = _format_json(findings_sorted, files_scanned, errors)
    elif fmt == "markdown":
        result = _format_markdown(findings_sorted, files_scanned, errors)
    else:
        result = _format_terminal(findings_sorted)
        result += "\n" + _format_summary_terminal(findings_sorted, files_scanned, errors)

    if output_file:
        with open(output_file, "w", encoding="utf-8") as fh:
            fh.write(result)

    return result


def print_render(
    findings: list[dict[str, Any]],
    files_scanned: int = 0,
    errors: list[str] | None = None,
    fmt: str = "terminal",
    output_file: str | None = None,
) -> None:
    """Render and print to stdout (or write to file if output_file given)."""
    result = render(findings, files_scanned, errors, fmt, output_file)
    if output_file:
        print(f"Report written to: {output_file}", file=sys.stderr)
    else:
        print(result)