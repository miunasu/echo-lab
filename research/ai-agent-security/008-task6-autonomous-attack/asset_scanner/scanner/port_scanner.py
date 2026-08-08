"""Multi-threaded TCP port scanner."""

from __future__ import annotations

import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


def parse_ports(ports_spec: str) -> List[int]:
    """
    Parse port specification like:
      22,80,443
      1-1024
      22,80,8000-8010
    """
    result = set()
    for part in ports_spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start, end = int(start_s), int(end_s)
            if start > end:
                start, end = end, start
            if start < 1 or end > 65535:
                raise ValueError(f"Port range out of bounds: {part}")
            result.update(range(start, end + 1))
        else:
            p = int(part)
            if p < 1 or p > 65535:
                raise ValueError(f"Port out of bounds: {p}")
            result.add(p)
    return sorted(result)


def _check_port(ip: str, port: int, timeout: float) -> Optional[Tuple[int, float]]:
    import time

    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        t0 = time.perf_counter()
        code = sock.connect_ex((ip, port))
        elapsed = time.perf_counter() - t0
        if code == 0:
            return port, elapsed
    except OSError:
        return None
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
    return None


def scan_host_ports(
    ip: str,
    ports: Sequence[int],
    timeout: float = 0.8,
    workers: int = 50,
) -> List[Dict]:
    """Scan ports on a single host. Returns list of {port, latency_ms}."""
    open_ports: List[Dict] = []
    workers = max(1, min(workers, len(ports) or 1))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_check_port, ip, port, timeout) for port in ports]
        for fut in as_completed(futures):
            try:
                result = fut.result()
            except Exception:
                continue
            if result:
                port, elapsed = result
                open_ports.append(
                    {
                        "port": port,
                        "latency_ms": round(elapsed * 1000, 2),
                    }
                )

    open_ports.sort(key=lambda x: x["port"])
    return open_ports


def scan_ports(
    hosts: Iterable[str],
    ports: Sequence[int],
    timeout: float = 0.8,
    host_workers: int = 16,
    port_workers: int = 50,
    progress_cb=None,
) -> Dict[str, List[Dict]]:
    """
    Scan ports across multiple hosts.

    Returns mapping: ip -> [{port, latency_ms}, ...]
    """
    host_list = list(hosts)
    results: Dict[str, List[Dict]] = {}
    host_workers = max(1, min(host_workers, len(host_list) or 1))

    def _scan_one(ip: str) -> Tuple[str, List[Dict]]:
        return ip, scan_host_ports(ip, ports, timeout=timeout, workers=port_workers)

    with ThreadPoolExecutor(max_workers=host_workers) as pool:
        futures = {pool.submit(_scan_one, ip): ip for ip in host_list}
        done = 0
        for fut in as_completed(futures):
            ip = futures[fut]
            try:
                host_ip, open_ports = fut.result()
                results[host_ip] = open_ports
            except Exception:
                results[ip] = []
            done += 1
            if progress_cb:
                progress_cb(done, len(host_list), ip)

    return results