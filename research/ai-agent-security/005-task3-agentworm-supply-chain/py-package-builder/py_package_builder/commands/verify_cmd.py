"""verify command: validate package structure and wheel integrity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..core.config import load_config
from ..core.verifier import PackageVerifier


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "verify",
        help="Verify package structure integrity (and optional wheel)",
        description=(
            "Check that the project has required metadata files, package layout, "
            "custom modules, entry points, and optionally validate a built wheel."
        ),
    )
    p.add_argument(
        "-p",
        "--project",
        default=".",
        help="Project directory to verify (default: .)",
    )
    p.add_argument(
        "-c",
        "--config",
        default=None,
        help="Optional package.builder.toml for expected modules/entry points",
    )
    p.add_argument(
        "-w",
        "--wheel",
        default=None,
        help="Specific wheel path to validate (default: latest in <project>/dist)",
    )
    p.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Print machine-readable JSON report",
    )
    p.set_defaults(func=run_verify)


def run_verify(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve()
    if not project.is_dir():
        print(f"[error] Project directory not found: {project}")
        return 1

    config = None
    if args.config:
        try:
            config = load_config(args.config)
        except Exception as exc:
            print(f"[error] Failed to load config: {exc}")
            return 1

    verifier = PackageVerifier(project, config=config, config_path=args.config)
    report = verifier.verify(wheel_path=args.wheel)

    if args.as_json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(f"[verify] Project: {project}")
        print("[verify] Checks:")
        for c in report.checks:
            mark = "OK" if c.ok else "FAIL"
            print(f"  [{mark}] {c.name}: {c.message}")
        if report.warnings:
            print("[verify] Warnings:")
            for w in report.warnings:
                print(f"  ! {w}")
        if report.errors:
            print("[verify] Errors:")
            for e in report.errors:
                print(f"  x {e}")
        print(f"[verify] Result: {'PASS' if report.ok else 'FAIL'}")

    return 0 if report.ok else 1