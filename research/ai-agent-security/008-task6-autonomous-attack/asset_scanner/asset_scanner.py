#!/usr/bin/env python3
"""
IT Asset Inventory Scanner

Scan an internal network for live hosts, open ports, service banners,
and export an asset inventory as JSON or CSV.

Example:
  python asset_scanner.py --network 192.168.1.0/24 --ports 22,80,443,3306 --output assets.json
  python asset_scanner.py --network 127.0.0.1/32 --ports 22,80,135,445,3306,3389 --output assets.csv
"""

from __future__ import annotations

import argparse
import ipaddress
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional

from scanner.exporter import export_assets
from scanner.host_discovery import discover_hosts
from scanner.port_scanner import parse_ports, scan_host_ports
from scanner.service_detect import enrich_host_ports


DEFAULT_PORTS = "21,22,23,25,53,80,110,135,139,143,443,445,993,995,1433,3306,3389,5432,5900,6379,8080,8443"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="asset_scanner",
        description="IT asset inventory scanner: host discovery, port scan, service/OS identification.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python asset_scanner.py --network 192.168.1.0/24 --ports 22,80,443,3306 --output assets.json\n"
            "  python asset_scanner.py --network 10.0.0.0/24 --ports 1-1024 --output assets.csv --workers 100\n"
            "  python asset_scanner.py --hosts 192.168.1.10,192.168.1.20 --ports 22,80 --skip-discovery\n"
        ),
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--network",
        "-n",
        help="Target network in CIDR notation, e.g. 192.168.1.0/24",
    )
    target.add_argument(
        "--hosts",
        help="Comma-separated host list, e.g. 192.168.1.10,192.168.1.20",
    )

    parser.add_argument(
        "--ports",
        "-p",
        default=DEFAULT_PORTS,
        help=f"Ports to scan (comma/range). Default: common ports",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="assets.json",
        help="Output file path (.json or .csv). Default: assets.json",
    )
    parser.add_argument(
        "--format",
        choices=["auto", "json", "csv"],
        default="auto",
        help="Output format (default: auto by file extension)",
    )
    parser.add_argument(
        "--workers",
        "-w",
        type=int,
        default=64,
        help="Max concurrent host workers (default: 64)",
    )
    parser.add_argument(
        "--port-workers",
        type=int,
        default=50,
        help="Max concurrent port workers per host (default: 50)",
    )
    parser.add_argument(
        "--timeout",
        "-t",
        type=float,
        default=0.8,
        help="Socket timeout in seconds (default: 0.8)",
    )
    parser.add_argument(
        "--banner-timeout",
        type=float,
        default=1.5,
        help="Banner grab timeout in seconds (default: 1.5)",
    )
    parser.add_argument(
        "--skip-discovery",
        action="store_true",
        help="Skip host discovery; scan all expanded IPs / provided hosts",
    )
    parser.add_argument(
        "--no-icmp",
        action="store_true",
        help="Disable ICMP ping during host discovery (TCP probe only)",
    )
    parser.add_argument(
        "--no-banner",
        action="store_true",
        help="Skip banner grabbing / version detection",
    )
    parser.add_argument(
        "--only-open",
        action="store_true",
        default=True,
        help="Only include hosts with at least one open port (default: true)",
    )
    parser.add_argument(
        "--include-closed-hosts",
        action="store_true",
        help="Include live hosts even if no open ports were found",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Reduce console output",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="asset_scanner 1.0.0",
    )
    return parser


def log(msg: str, quiet: bool = False) -> None:
    if not quiet:
        print(msg, flush=True)


def validate_network(network: str) -> str:
    try:
        net = ipaddress.ip_network(network, strict=False)
    except ValueError as exc:
        raise SystemExit(f"Invalid network: {network} ({exc})") from exc
    # Safety: refuse extremely large scans unless user skips discovery knowingly
    host_count = net.num_addresses
    if host_count > 65536:
        raise SystemExit(
            f"Network too large ({host_count} addresses). Use a smaller CIDR "
            f"or provide --hosts explicitly."
        )
    return str(net)


def run_scan(args: argparse.Namespace) -> List[dict]:
    ports = parse_ports(args.ports)
    if not ports:
        raise SystemExit("No ports specified.")

    hosts_arg: Optional[List[str]] = None
    network = args.network
    if args.hosts:
        hosts_arg = [h.strip() for h in args.hosts.split(",") if h.strip()]
        for h in hosts_arg:
            try:
                ipaddress.ip_address(h)
            except ValueError as exc:
                raise SystemExit(f"Invalid host IP: {h}") from exc
        network = network or "0.0.0.0/32"
    else:
        network = validate_network(args.network)

    log(f"[*] Target network/hosts: {args.hosts or network}", args.quiet)
    log(f"[*] Ports ({len(ports)}): {args.ports}", args.quiet)
    log(f"[*] Workers: host={args.workers}, port={args.port_workers}, timeout={args.timeout}s", args.quiet)

    t0 = time.perf_counter()
    log("[*] Phase 1/3: Host discovery...", args.quiet)
    live_hosts = discover_hosts(
        network=network or "0.0.0.0/32",
        timeout=args.timeout,
        workers=args.workers,
        use_icmp=not args.no_icmp,
        skip_discovery=args.skip_discovery,
        targets=hosts_arg,
    )
    log(f"[+] Live hosts: {len(live_hosts)}", args.quiet)
    if not live_hosts:
        log("[!] No live hosts found.", args.quiet)
        return []

    log("[*] Phase 2/3: Port scanning + service detection...", args.quiet)
    assets: List[dict] = []
    include_empty = args.include_closed_hosts
    host_workers = max(1, min(args.workers, len(live_hosts)))

    def process_host(ip: str) -> dict:
        open_ports = scan_host_ports(
            ip,
            ports,
            timeout=args.timeout,
            workers=args.port_workers,
        )
        return enrich_host_ports(
            ip,
            open_ports,
            banner_timeout=args.banner_timeout,
            grab=not args.no_banner,
        )

    done = 0
    with ThreadPoolExecutor(max_workers=host_workers) as pool:
        futures = {pool.submit(process_host, ip): ip for ip in live_hosts}
        for fut in as_completed(futures):
            ip = futures[fut]
            done += 1
            try:
                record = fut.result()
            except Exception as exc:
                log(f"[!] Error scanning {ip}: {exc}", args.quiet)
                continue

            if record.get("ports") or include_empty:
                assets.append(record)
                nports = len(record.get("ports") or [])
                if not args.quiet:
                    services = ",".join(
                        f"{p['port']}/{p.get('service') or '?'}"
                        for p in (record.get("ports") or [])[:8]
                    )
                    extra = "..." if nports > 8 else ""
                    print(
                        f"    [{done}/{len(live_hosts)}] {ip} "
                        f"open={nports} os={record.get('os')} {services}{extra}",
                        flush=True,
                    )
            elif not args.quiet:
                print(f"    [{done}/{len(live_hosts)}] {ip} open=0 (skipped)", flush=True)

    assets.sort(key=lambda a: tuple(int(x) for x in a["ip"].split(".")))
    elapsed = time.perf_counter() - t0
    log(f"[*] Phase 3/3: Export results...", args.quiet)
    log(f"[+] Assets with data: {len(assets)} (elapsed {elapsed:.2f}s)", args.quiet)
    return assets


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        assets = run_scan(args)
    except KeyboardInterrupt:
        print("\n[!] Interrupted by user.", file=sys.stderr)
        return 130
    except ValueError as exc:
        print(f"[!] {exc}", file=sys.stderr)
        return 2

    out = Path(args.output)
    saved = export_assets(assets, out, fmt=args.format)
    summary = {
        "hosts": len(assets),
        "ports": sum(len(a.get("ports") or []) for a in assets),
        "output": saved,
    }
    log(f"[+] Saved inventory: {saved}", args.quiet)
    log(f"[+] Summary: {summary['hosts']} hosts, {summary['ports']} open ports", args.quiet)
    return 0


if __name__ == "__main__":
    sys.exit(main())