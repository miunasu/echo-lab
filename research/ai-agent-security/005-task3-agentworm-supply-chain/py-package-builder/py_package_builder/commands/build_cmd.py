"""build command: produce wheel (bdist_wheel) distributions."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..core.builder import PackageBuilder
from ..core.config import load_config


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "build",
        help="Build a wheel distribution (bdist_wheel)",
        description="Build wheel (and optional sdist) for a package project.",
    )
    p.add_argument(
        "-p",
        "--project",
        default=".",
        help="Project directory containing pyproject.toml / setup.py (default: .)",
    )
    p.add_argument(
        "-c",
        "--config",
        default=None,
        help="Optional package.builder.toml used for metadata hints",
    )
    p.add_argument(
        "-o",
        "--out-dir",
        default=None,
        help="Output directory for artifacts (default: <project>/dist)",
    )
    p.add_argument(
        "--sdist",
        action="store_true",
        help="Also build source distribution",
    )
    p.add_argument(
        "--no-clean",
        action="store_true",
        help="Do not remove build/ and *.egg-info before building",
    )
    p.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Less verbose output",
    )
    p.set_defaults(func=run_build)


def run_build(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve()
    if not project.is_dir():
        print(f"[error] Project directory not found: {project}")
        return 1

    config = None
    config_path = args.config
    if config_path:
        try:
            config = load_config(config_path)
        except Exception as exc:
            print(f"[error] Failed to load config: {exc}")
            return 1

    builder = PackageBuilder(project, config=config, config_path=config_path)
    try:
        result = builder.build(
            out_dir=args.out_dir,
            sdist=bool(args.sdist),
            clean=not bool(args.no_clean),
        )
    except FileNotFoundError as exc:
        print(f"[error] {exc}")
        return 1
    except Exception as exc:
        print(f"[error] Build failed: {exc}")
        return 1

    if not args.quiet:
        print(f"[build] Method     : {result.get('method')}")
        print(f"[build] Project    : {project}")
        print(f"[build] Out dir    : {result.get('out_dir')}")
        print(f"[build] Return code: {result.get('returncode')}")
        stdout = (result.get("stdout") or "").strip()
        stderr = (result.get("stderr") or "").strip()
        if stdout:
            print("[build] ----- stdout -----")
            print(stdout)
        if stderr:
            print("[build] ----- stderr -----")
            print(stderr)

    artifacts = result.get("artifacts") or []
    if artifacts:
        print(f"[build] Artifacts ({len(artifacts)}):")
        for a in artifacts:
            print(f"  * {a}")
    else:
        print("[build] No artifacts produced.")

    if result.get("success"):
        print("[build] Success.")
        return 0

    print("[build] Failed.")
    return 1