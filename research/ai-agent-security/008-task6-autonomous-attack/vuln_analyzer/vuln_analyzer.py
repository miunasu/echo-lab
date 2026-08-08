#!/usr/bin/env python3
"""CLI entry: vulnerability impact analyzer for asset inventories."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

from analyzer import VulnAnalyzer, write_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vuln_analyzer.py",
        description=(
            "Asset vulnerability impact analyzer. "
            "Reads an asset inventory JSON, queries NVD (or a local CVE DB), "
            "scores impact, and writes a remediation-oriented report."
        ),
    )
    parser.add_argument(
        "--assets",
        required=True,
        help="Path to asset inventory JSON file",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write vulnerabilities report JSON",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use local CVE database only (no NVD network calls)",
    )
    parser.add_argument(
        "--db",
        dest="db_path",
        default=None,
        help="Path to local CVE JSON database (required with --offline)",
    )
    parser.add_argument(
        "--api-key",
        dest="api_key",
        default=None,
        help="NVD API key (or set env NVD_API_KEY). Higher rate limits.",
    )
    parser.add_argument(
        "--hybrid",
        action="store_true",
        help="With --offline/--db, fall back to NVD when local DB has no hits",
    )
    parser.add_argument(
        "--max-cves",
        type=int,
        default=25,
        help="Max CVEs retained per asset (default: 25)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity",
    )
    parser.add_argument(
        "--pretty-print",
        action="store_true",
        help="Also print a short human-readable summary to stdout",
    )
    return parser


def print_summary(report: dict) -> None:
    summary = report.get("summary") or {}
    print("=" * 60)
    print("Vulnerability Impact Analysis Summary")
    print("=" * 60)
    print(f"Mode            : {summary.get('mode', 'n/a')}")
    print(f"Assets analyzed : {summary.get('asset_count', 0)}")
    print(f"Total CVEs      : {summary.get('total_cves', 0)}")
    print(f"Overall priority: {summary.get('overall_priority', 'INFO')}")
    counts = summary.get("priority_counts") or {}
    print(
        "Priority counts : "
        + ", ".join(f"{k}={v}" for k, v in counts.items() if v)
    )
    print("-" * 60)
    for item in report.get("results") or []:
        print(f"[{item.get('priority', 'INFO')}] {item.get('asset')}")
        print(
            f"    CVEs: {item.get('cve_count', 0)} | "
            f"Patch score: {item.get('patch_priority_score', 0)}"
        )
        cves = item.get("cves") or []
        for cve in cves[:5]:
            exploit = " EXPLOIT" if cve.get("exploit_available") else ""
            print(
                f"    - {cve.get('cve_id')}  "
                f"CVSS={cve.get('cvss')}  {cve.get('severity')}{exploit}"
            )
        if len(cves) > 5:
            print(f"    ... {len(cves) - 5} more")
        rem = item.get("remediation") or []
        if rem:
            print(f"    Fix: {rem[0]}")
        print()
    print(f"Full report: see output JSON")


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    assets_path = Path(args.assets)
    if not assets_path.exists():
        logging.error("Assets file not found: %s", assets_path)
        return 2

    if args.offline and not args.db_path:
        logging.error("--offline requires --db <local_cve_db.json>")
        return 2

    if args.db_path and not Path(args.db_path).exists():
        logging.error("Local CVE DB not found: %s", args.db_path)
        return 2

    try:
        analyzer = VulnAnalyzer(
            offline=bool(args.offline or args.db_path),
            offline_db_path=args.db_path,
            api_key=args.api_key,
            max_cves_per_asset=args.max_cves,
            online_fallback=bool(args.hybrid),
        )
        # If user passed only --db without --offline, treat as offline unless hybrid
        if args.db_path and not args.hybrid and not args.offline:
            analyzer.offline = True
            analyzer.nvd = None

        report = analyzer.analyze_file(assets_path)
        write_report(report, args.output)

        if args.pretty_print:
            print_summary(report)
        else:
            # minimal stdout confirmation
            summary = report.get("summary") or {}
            print(
                json.dumps(
                    {
                        "status": "ok",
                        "output": str(Path(args.output).resolve()),
                        "asset_count": summary.get("asset_count", 0),
                        "total_cves": summary.get("total_cves", 0),
                        "overall_priority": summary.get("overall_priority", "INFO"),
                    },
                    ensure_ascii=False,
                )
            )
        return 0
    except Exception as exc:  # noqa: BLE001
        logging.exception("Analysis failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())