"""CLI for Config Template Engine: render / validate / list."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import click
import yaml
from rich.console import Console
from rich.table import Table

from . import __version__
from .engine import ConfigRenderer, TemplateEngine, default_templates_dir
from .validator import SchemaValidator, default_schemas_dir

console = Console(stderr=True)


def _parse_var(value: str) -> tuple[str, Any]:
    if "=" not in value:
        raise click.BadParameter(f"Expected KEY=VALUE, got: {value}")
    key, raw = value.split("=", 1)
    key = key.strip()
    raw = raw.strip()
    if not key:
        raise click.BadParameter(f"Empty key in: {value}")
    # try json literal, then yaml, else plain string
    try:
        return key, json.loads(raw)
    except json.JSONDecodeError:
        pass
    try:
        parsed = yaml.safe_load(raw)
        return key, parsed
    except Exception:
        return key, raw


def _build_context(
    context_file: Optional[Path],
    vars_: tuple[str, ...],
) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {}
    if context_file:
        ctx.update(ConfigRenderer.load_context(context_file))
    for item in vars_:
        k, v = _parse_var(item)
        ctx[k] = v
    return ctx


@click.group()
@click.version_option(__version__, prog_name="cte")
def main() -> None:
    """Config Template Engine - render and validate YAML/JSON/Markdown configs."""


@main.command("render")
@click.argument("template", type=str)
@click.option(
    "-c",
    "--context",
    "context_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Context variables file (YAML or JSON).",
)
@click.option(
    "-v",
    "--var",
    "vars_",
    multiple=True,
    help="Variable override KEY=VALUE (JSON/YAML literal supported). Repeatable.",
)
@click.option(
    "-o",
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Write rendered result to file instead of stdout.",
)
@click.option(
    "-f",
    "--format",
    "output_format",
    type=click.Choice(["yaml", "yml", "json", "md", "markdown"], case_sensitive=False),
    default=None,
    help="Force output format (default: detect from template/output name).",
)
@click.option(
    "-t",
    "--template-dir",
    "template_dirs",
    multiple=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Extra template search directory. Repeatable.",
)
@click.option(
    "--string/--file",
    "from_string",
    default=False,
    help="Treat TEMPLATE argument as raw Jinja2 source string.",
)
@click.option(
    "--strict/--no-strict",
    default=True,
    help="Strict undefined variables (default: strict).",
)
@click.option(
    "--validate-with",
    "schema_ref",
    default=None,
    help="Optionally validate rendered output against a schema name or path.",
)
def render_cmd(
    template: str,
    context_file: Optional[Path],
    vars_: tuple[str, ...],
    output_path: Optional[Path],
    output_format: Optional[str],
    template_dirs: tuple[Path, ...],
    from_string: bool,
    strict: bool,
    schema_ref: Optional[str],
) -> None:
    """Render a Jinja2 config template with the given context."""
    try:
        engine = TemplateEngine(
            template_dirs=list(template_dirs) if template_dirs else None,
            strict=strict,
        )
        renderer = ConfigRenderer(engine)
        context = _build_context(context_file, vars_)
        result = renderer.render(
            template=template,
            context=context,
            output_format=output_format,
            from_string=from_string,
        )

        if schema_ref:
            validator = SchemaValidator()
            vr = validator.validate(result, schema_ref)
            if not vr.ok:
                console.print("[red]Render succeeded but schema validation failed:[/red]")
                console.print(vr.summary())
                sys.exit(2)

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(result, encoding="utf-8")
            console.print(f"[green]Wrote[/green] {output_path}")
        else:
            # stdout for piping
            sys.stdout.write(result)
            if not result.endswith("\n"):
                sys.stdout.write("\n")
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)


@main.command("validate")
@click.argument("config", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "-s",
    "--schema",
    "schema_ref",
    required=True,
    help="Schema name (from schemas/) or file path.",
)
@click.option(
    "--schema-dir",
    "schema_dirs",
    multiple=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Extra schema search directory. Repeatable.",
)
@click.option(
    "--json-output",
    is_flag=True,
    help="Print machine-readable JSON result.",
)
def validate_cmd(
    config: Path,
    schema_ref: str,
    schema_dirs: tuple[Path, ...],
    json_output: bool,
) -> None:
    """Validate a config file against a JSON Schema."""
    try:
        validator = SchemaValidator(
            schema_dirs=list(schema_dirs) if schema_dirs else None,
        )
        result = validator.validate(config, schema_ref)
        if json_output:
            payload = {
                "ok": result.ok,
                "schema": result.schema_name,
                "issues": [
                    {
                        "path": i.path,
                        "message": i.message,
                        "validator": i.validator,
                    }
                    for i in result.issues
                ],
            }
            sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        else:
            if result.ok:
                console.print(f"[green]OK[/green] {config} matches schema '{result.schema_name}'")
            else:
                console.print(f"[red]FAIL[/red] {config}")
                console.print(result.summary())
        sys.exit(0 if result.ok else 1)
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)


@main.command("list-templates")
@click.option(
    "-t",
    "--template-dir",
    "template_dirs",
    multiple=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Extra template search directory.",
)
def list_templates_cmd(template_dirs: tuple[Path, ...]) -> None:
    """List available templates."""
    engine = TemplateEngine(
        template_dirs=list(template_dirs) if template_dirs else None,
        strict=False,
    )
    names = engine.list_templates()
    table = Table(title="Templates")
    table.add_column("Name", style="cyan")
    table.add_column("Search Paths", style="dim")
    paths = ", ".join(engine.template_dirs)
    if not names:
        console.print(f"No templates found. Paths: {paths}")
        console.print(f"Default templates dir: {default_templates_dir()}")
        return
    for n in names:
        table.add_row(n, paths)
    console.print(table)


@main.command("list-schemas")
@click.option(
    "--schema-dir",
    "schema_dirs",
    multiple=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Extra schema search directory.",
)
def list_schemas_cmd(schema_dirs: tuple[Path, ...]) -> None:
    """List available schemas."""
    validator = SchemaValidator(
        schema_dirs=list(schema_dirs) if schema_dirs else None,
    )
    names = validator.list_schemas()
    table = Table(title="Schemas")
    table.add_column("Name", style="cyan")
    if not names:
        console.print(f"No schemas found. Default: {default_schemas_dir()}")
        return
    for n in names:
        table.add_row(n)
    console.print(table)


if __name__ == "__main__":
    main()