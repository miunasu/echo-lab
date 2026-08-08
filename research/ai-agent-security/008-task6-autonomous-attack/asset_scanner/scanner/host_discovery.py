"""Host discovery and CIDR expansion."""

from __future__ import annotations

import ipaddress
import platform
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable, List, Optional, Sequence


DEFAULT_PROBE_PORTS = (80, 443, 22, 445, 3389, 135)


def expand_network(network: str) -> List[str]:
    """Expand CIDR/network notation into host IP strings (excludes network/broadcast for IPv4)."""
    net = ipaddress.ip_network(network, strict=False)
    if isinstance(net, ipaddress.IPv4Network) and net.num_addresses > 2:
        return [str(ip) for ip in net.hosts()]
    return [str(ip) for ip in net]


def _tcp_probe(ip: str, ports: Sequence[int], timeout: float) -> bool:
    for port in ports:
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            if sock.connect_ex((ip, port)) == 0:
                return True
        except OSError:
            continue
        finally:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
    return False


def _icmp_ping(ip: str, timeout: float) -> bool:
    """Best-effort ICMP ping. May require elevated privileges on some systems."""
    system = platform.system().lower()
    try:
        if system == "windows":
            # -n count, -w timeout(ms)
            ms = max(1, int(timeout * 1000))
            cmd = ["ping", "-n", "1", "-w", str(ms), ip]
        else:
            # -c count, -W timeout(s) on Linux; macOS uses -W in ms sometimes
            sec = max(1, int(timeout))
            cmd = ["ping", "-c", "1", "-W", str(sec), ip]
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout + 2,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def is_host_alive(
    ip: str,
    timeout: float = 0.8,
    probe_ports: Optional[Sequence[int]] = None,
    use_icmp: bool = True,
) -> bool:
    """Determine if a host is alive via ICMP and/or TCP probes."""
    ports = tuple(probe_ports) if probe_ports else DEFAULT_PROBE_PORTS
    if use_icmp and _icmp_ping(ip, timeout):
        return True
    return _tcp_probe(ip, ports, timeout)


def discover_hosts(
    network: str,
    timeout: float = 0.8,
    workers: int = 64,
    probe_ports: Optional[Sequence[int]] = None,
    use_icmp: bool = True,
    skip_discovery: bool = False,
    targets: Optional[Iterable[str]] = None,
) -> List[str]:
    """
    Discover live hosts in a network.

    If skip_discovery is True, return all expanded IPs (or provided targets)
    without probing.
    """
    if targets is not None:
        ip_list = [str(ipaddress.ip_address(t.strip())) for t in targets if str(t).strip()]
    else:
        ip_list = expand_network(network)

    if skip_discovery:
        return ip_list

    alive: List[str] = []
    workers = max(1, min(workers, len(ip_list) or 1))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(is_host_alive, ip, timeout, probe_ports, use_icmp): ip
            for ip in ip_list
        }
        for fut in as_completed(futures):
            ip = futures[fut]
            try:
                if fut.result():
                    alive.append(ip)
            except Exception:
                continue

    # Stable order by IP numeric value
    alive.sort(key=lambda x: int(ipaddress.ip_address(x)))
    return alive