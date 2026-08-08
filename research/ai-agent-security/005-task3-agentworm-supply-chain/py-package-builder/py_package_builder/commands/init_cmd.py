"""init command: scaffold a new Python package project."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..core.config import (
    PackageConfig,
    default_config,
    load_config,
    save_config,
    ModuleSpec,
    EntryPoint,
)
from ..core.generator import PackageGenerator


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "init",
        help="Generate a standard Python package project structure",
        description=(
            "Create setup.py / pyproject.toml / __init__.py and optional custom modules "
            "from CLI flags or a config file."
        ),
    )
    p.add_argument("-n", "--name", default=None, help="Package name (default: my_package)")
    p.add_argument("-v", "--version", default="0.1.0", help="Package version")
    p.add_argument("-a", "--author", default="Unknown", help="Author name")
    p.add_argument("--email", default="", help="Author email")
    p.add_argument("-d", "--description", default=None, help="Short description")
    p.add_argument(
        "-o",
        "--output",
        default=".",
        help="Output directory for the new project (default: current directory)",
    )
    p.add_argument(
        "-c",
        "--config",
        default=None,
        help="Path to package.builder.toml / .json config (overrides other flags when set)",
    )
    p.add_argument(
        "--dep",
        action="append",
        default=[],
        dest="deps",
        help="Dependency requirement (repeatable), e.g. --dep 'requests>=2.0'",
    )
    p.add_argument(
        "--module",
        action="append",
        default=[],
        dest="modules",
        help="Extra module name under the package (repeatable)",
    )
    p.add_argument(
        "--entry",
        action="append",
        default=[],
        dest="entries",
        help="Console entry point name=module:attr (repeatable)",
    )
    p.add_argument("--license", default="MIT", dest="license", help="License identifier")
    p.add_argument("--no-setup-py", action="store_true", help="Do not generate setup.py")
    p.add_argument("--no-pyproject", action="store_true", help="Do not generate pyproject.toml")
    p.add_argument("--force", action="store_true", help="Overwrite existing files")
    p.add_argument(
        "--save-config",
        default=None,
        help="Also write resolved config to this path (default: <output>/package.builder.toml)",
    )
    p.set_defaults(func=run_init)


def _parse_entry(spec: str) -> EntryPoint:
    if "=" not in spec:
        raise ValueError(f"Invalid --entry '{spec}', expected name=module:attr")
    name, rest = spec.split("=", 1)
    if ":" in rest:
        module, attr = rest.rsplit(":", 1)
    else:
        module, attr = rest, "main"
    return EntryPoint(name=name.strip(), module=module.strip(), attr=attr.strip())


def _build_config_from_args(args: argparse.Namespace) -> PackageConfig:
    if args.config:
        return load_config(args.config)

    name = args.name or "my_package"
    cfg = default_config(name=name, version=args.version, author=args.author)
    cfg.author_email = args.email or ""
    cfg.license = args.license
    if args.description:
        cfg.description = args.description
    if args.deps:
        cfg.dependencies = list(args.deps)
    if args.modules:
        existing = {m.name for m in cfg.modules}
        for m in args.modules:
            if m not in existing:
                cfg.modules.append(
                    ModuleSpec(name=m, content=f'"""{m} module for {name}."""\n')
                )
    if args.entries:
        cfg.entry_points = [_parse_entry(e) for e in args.entries]
    cfg.use_setup_py = not args.no_setup_py
    cfg.use_pyproject = not args.no_pyproject
    if not cfg.use_setup_py and not cfg.use_pyproject:
        raise ValueError("At least one of setup.py or pyproject.toml must be enabled")
    return cfg


def run_init(args: argparse.Namespace) -> int:
    try:
        cfg = _build_config_from_args(args)
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"[error] {exc}")
        return 1

    errors = cfg.validate()
    if errors:
        print("[error] Invalid configuration:")
        for e in errors:
            print(f"  - {e}")
        return 1

    project_dir = Path(args.output).resolve()
    project_dir.mkdir(parents=True, exist_ok=True)

    generator = PackageGenerator(cfg, project_dir)
    result = generator.generate(force=bool(args.force))

    config_path = Path(args.save_config) if args.save_config else project_dir / "package.builder.toml"
    save_config(cfg, config_path)

    print(f"[init] Package '{cfg.name}' v{cfg.version}")
    print(f"[init] Project dir : {project_dir}")
    print(f"[init] Config saved: {config_path}")
    if result["created"]:
        print(f"[init] Created ({len(result['created'])}):")
        for p in result["created"]:
            print(f"  + {p}")
    if result["updated"]:
        print(f"[init] Updated ({len(result['updated'])}):")
        for p in result["updated"]:
            print(f"  ~ {p}")
    if result["skipped"]:
        print(f"[init] Skipped existing ({len(result['skipped'])}) -- use --force to overwrite:")
        for p in result["skipped"]:
            print(f"  = {p}")

    print("[init] Done. Next: py-package-builder build -p <project_dir>")
    return 0