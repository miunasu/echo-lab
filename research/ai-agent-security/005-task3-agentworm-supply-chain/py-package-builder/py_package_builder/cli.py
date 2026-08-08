"""Command-line interface for py-package-builder."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .commands import init_cmd, build_cmd, verify_cmd


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="py-package-builder",
        description=(
            "Automated Python package scaffolding and wheel builder.\n"
            "Commands: init (scaffold), build (bdist_wheel), verify (structure check)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  py-package-builder init -n demo_pkg -a Alice -o ./demo_pkg\n"
            "  py-package-builder build -p ./demo_pkg\n"
            "  py-package-builder verify -p ./demo_pkg\n"
            "  py-package-builder init -c examples/sample.package.builder.toml -o ./from_cfg\n"
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    init_cmd.add_parser(sub)
    build_cmd.add_parser(sub)
    verify_cmd.add_parser(sub)
    return parser


def main(argv: list | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 2
    try:
        return int(func(args))
    except KeyboardInterrupt:
        print("\n[aborted]")
        return 130


if __name__ == "__main__":
    sys.exit(main())