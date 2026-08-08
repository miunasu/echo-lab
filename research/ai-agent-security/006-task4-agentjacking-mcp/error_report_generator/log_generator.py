#!/usr/bin/env python3
"""CLI tool to generate formatted error reports via Jinja2 templates.

Usage examples:
  python log_generator.py --type runtime_error --message "Null pointer"
  python log_generator.py --type api_call_failure --format text
  python log_generator.py --type database_error --context '{"db_host":"db1"}' --field env=staging
  python log_generator.py --list-types
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from error_types import ERROR_TYPES, get_error_definition, list_error_types

ROOT_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = ROOT_DIR / "templates"
DEFAULT_CONFIG_PATH = ROOT_DIR / "config" / "default.json"

TEMPLATE_MAP = {
    "json": "error_report.json.j2",
    "text": "error_report.text.j2",
}


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load optional JSON config; missing file yields empty dict."""
    path = config_path or DEFAULT_CONFIG_PATH
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Config root must be an object: {path}")
    return data


def parse_json_object(raw: str | None, label: str) -> dict[str, Any]:
    """Parse a JSON object string; None/empty returns {}."""
    if raw is None or str(raw).strip() == "":
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON for {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def parse_field_overrides(items: list[str] | None) -> dict[str, Any]:
    """Parse repeated --field key=value into a dict (JSON values preferred)."""
    result: dict[str, Any] = {}
    if not items:
        return result
    for item in items:
        if "=" not in item:
            raise ValueError(f"Invalid --field '{item}', expected key=value")
        key, raw_value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Invalid --field '{item}', empty key")
        raw_value = raw_value.strip()
        try:
            result[key] = json.loads(raw_value)
        except json.JSONDecodeError:
            result[key] = raw_value
    return result


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Shallow-friendly merge: nested dicts merge, other values replace."""
    merged = dict(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def build_timestamp(value: str | None) -> str:
    if value:
        return value
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_report_data(
    error_type: str,
    message: str | None = None,
    stack_trace: str | None = None,
    context: dict[str, Any] | None = None,
    custom_fields: dict[str, Any] | None = None,
    timestamp: str | None = None,
    severity: str | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble report payload from type defaults, config, and CLI overrides."""
    definition = get_error_definition(error_type)
    cfg = config or {}

    type_defaults = cfg.get("type_defaults", {}).get(error_type, {})
    global_context = cfg.get("default_context", {})
    global_custom = cfg.get("default_custom_fields", {})

    ctx = deep_merge(definition.get("default_context", {}), global_context)
    ctx = deep_merge(ctx, type_defaults.get("context", {}))
    ctx = deep_merge(ctx, context or {})

    customs = deep_merge(global_custom, type_defaults.get("custom_fields", {}))
    customs = deep_merge(customs, custom_fields or {})

    data: dict[str, Any] = {
        "timestamp": build_timestamp(
            timestamp or type_defaults.get("timestamp") or cfg.get("timestamp")
        ),
        "error_type": error_type,
        "severity": (
            severity
            or type_defaults.get("severity")
            or cfg.get("default_severity")
            or definition.get("severity", "error")
        ),
        "message": (
            message
            or type_defaults.get("message")
            or definition.get("default_message", "")
        ),
        "stack_trace": (
            stack_trace
            or type_defaults.get("stack_trace")
            or definition.get("default_stack_trace", "")
        ),
        "context": ctx,
        "custom_fields": customs,
    }
    return data


def render_report(data: dict[str, Any], output_format: str = "json") -> str:
    """Render report data with the selected Jinja2 template."""
    if output_format not in TEMPLATE_MAP:
        supported = ", ".join(sorted(TEMPLATE_MAP))
        raise ValueError(f"Unsupported format '{output_format}'. Supported: {supported}")

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    template = env.get_template(TEMPLATE_MAP[output_format])
    rendered = template.render(**data)

    if output_format == "json":
        # Normalize to compact-valid pretty JSON for downstream tools
        parsed = json.loads(rendered)
        return json.dumps(parsed, indent=2, ensure_ascii=False) + "\n"
    return rendered


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="log_generator.py",
        description="Generate formatted error reports for log/monitoring system testing.",
    )
    parser.add_argument(
        "--type",
        "-t",
        dest="error_type",
        help="Error type key (see --list-types)",
    )
    parser.add_argument(
        "--message",
        "-m",
        help="Override error message",
    )
    parser.add_argument(
        "--stack-trace",
        help="Override stack trace text",
    )
    parser.add_argument(
        "--context",
        "-c",
        help='Context JSON object, e.g. \'{"user_id": 123}\'',
    )
    parser.add_argument(
        "--field",
        action="append",
        default=[],
        help="Custom field as key=value (repeatable). Value may be JSON.",
    )
    parser.add_argument(
        "--custom-fields",
        help='Custom fields JSON object, e.g. \'{"trace_id":"abc"}\'',
    )
    parser.add_argument(
        "--timestamp",
        help="ISO-8601 timestamp override (default: now UTC)",
    )
    parser.add_argument(
        "--severity",
        choices=["debug", "info", "warning", "error", "critical"],
        help="Severity override",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=sorted(TEMPLATE_MAP.keys()),
        default=None,
        help="Output format (default: json or config.default_format)",
    )
    parser.add_argument(
        "--config",
        help=f"Path to JSON config (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Write report to file instead of stdout",
    )
    parser.add_argument(
        "--list-types",
        action="store_true",
        help="List supported error types and exit",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Generate N reports (appends index to context when N>1)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.list_types:
        for name in list_error_types():
            meta = ERROR_TYPES[name]
            print(f"{name:20} [{meta.get('severity', 'error')}] {meta.get('description', '')}")
        return 0

    if not args.error_type:
        parser.error("--type is required unless --list-types is used")

    if args.count < 1:
        parser.error("--count must be >= 1")

    try:
        config_path = Path(args.config) if args.config else None
        config = load_config(config_path)
        context = parse_json_object(args.context, "--context")
        custom_from_json = parse_json_object(args.custom_fields, "--custom-fields")
        custom_from_fields = parse_field_overrides(args.field)
        custom_fields = deep_merge(custom_from_json, custom_from_fields)

        output_format = args.format or config.get("default_format", "json")
        reports: list[str] = []

        for index in range(args.count):
            ctx = dict(context)
            if args.count > 1:
                ctx = deep_merge(ctx, {"report_index": index + 1, "report_total": args.count})
            data = build_report_data(
                error_type=args.error_type,
                message=args.message,
                stack_trace=args.stack_trace,
                context=ctx,
                custom_fields=custom_fields,
                timestamp=args.timestamp,
                severity=args.severity,
                config=config,
            )
            reports.append(render_report(data, output_format=output_format))

        if output_format == "json" and args.count > 1:
            # Emit a JSON array when generating multiple JSON reports
            payload = [json.loads(item) for item in reports]
            output_text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        else:
            separator = "\n" if output_format == "text" else ""
            output_text = separator.join(reports)

        if args.output:
            out_path = Path(args.output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(output_text, encoding="utf-8")
            print(f"Wrote {args.count} report(s) to {out_path}", file=sys.stderr)
        else:
            sys.stdout.write(output_text)
        return 0
    except KeyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())