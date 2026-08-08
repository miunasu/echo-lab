"""Banner grabbing, service identification, and basic OS guessing."""

from __future__ import annotations

import re
import socket
from typing import Dict, List, Optional, Tuple


# Common port -> default service name
PORT_SERVICE_MAP = {
    21: "ftp",
    22: "ssh",
    23: "telnet",
    25: "smtp",
    53: "dns",
    80: "http",
    110: "pop3",
    111: "rpcbind",
    135: "msrpc",
    139: "netbios-ssn",
    143: "imap",
    443: "https",
    445: "microsoft-ds",
    465: "smtps",
    587: "submission",
    993: "imaps",
    995: "pop3s",
    1433: "mssql",
    1521: "oracle",
    3306: "mysql",
    3389: "rdp",
    5432: "postgresql",
    5900: "vnc",
    6379: "redis",
    8080: "http-proxy",
    8443: "https-alt",
    9200: "elasticsearch",
    27017: "mongodb",
}


# Probe payloads for better banners
PROBES = {
    "http": b"HEAD / HTTP/1.0\r\nHost: localhost\r\nUser-Agent: AssetScanner/1.0\r\n\r\n",
    "https_like": b"HEAD / HTTP/1.0\r\nHost: localhost\r\n\r\n",
    "smtp": b"EHLO asset-scanner.local\r\n",
    "ftp": b"",  # server speaks first
    "ssh": b"",  # server speaks first
    "mysql": b"",  # server speaks first
    "redis": b"INFO\r\n",
    "generic": b"\r\n",
}


def _probe_for_port(port: int) -> bytes:
    """Return client probe bytes. Empty means server-speaks-first."""
    if port in (80, 8080, 8000, 8888):
        return PROBES["http"]
    if port in (443, 8443):
        return PROBES["https_like"]
    if port in (25, 587):
        return PROBES["smtp"]
    if port == 6379:
        return PROBES["redis"]
    # Speak-first services: empty probe, just read
    if port in (21, 22, 23, 110, 143, 3306, 5432, 1521):
        return b""
    return PROBES["generic"]


def grab_banner(ip: str, port: int, timeout: float = 1.5) -> str:
    """Connect and attempt to read a service banner / response snippet."""
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip, port))

        probe = _probe_for_port(port)
        # For speak-first services, try reading first
        if not probe:
            try:
                data = sock.recv(1024)
                if data:
                    return _clean_banner(data)
            except socket.timeout:
                pass
            # fallback small probe
            try:
                sock.sendall(b"\r\n")
            except OSError:
                pass
        else:
            try:
                sock.sendall(probe)
            except OSError:
                pass

        chunks = []
        try:
            while True:
                data = sock.recv(4096)
                if not data:
                    break
                chunks.append(data)
                if sum(len(c) for c in chunks) >= 4096:
                    break
                # single read is usually enough for banners
                if len(chunks) >= 1 and port not in (80, 8080, 8000, 8888, 443, 8443):
                    break
                if port in (80, 8080, 8000, 8888, 443, 8443) and b"\r\n\r\n" in b"".join(chunks):
                    break
        except socket.timeout:
            pass

        raw = b"".join(chunks)
        return _clean_banner(raw) if raw else ""
    except OSError:
        return ""
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass


def _clean_banner(data: bytes) -> str:
    text = data.decode("utf-8", errors="replace")
    # Keep printable-ish content, collapse excessive whitespace
    text = text.replace("\x00", "")
    text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f]", ".", text)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    joined = " | ".join(lines[:8])
    return joined[:500]


def _extract_http_server(banner: str) -> Optional[str]:
    m = re.search(r"(?i)server:\s*([^\r\n|]+)", banner)
    if m:
        return m.group(1).strip()
    return None


def _match_version_patterns(banner: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (service, version) from banner patterns."""
    lower = banner.lower()

    # SSH
    m = re.search(r"(?i)SSH-([\d.]+)-OpenSSH[_-]?([\w.]+)", banner)
    if m:
        return "ssh", f"OpenSSH {m.group(2)}"
    m = re.search(r"(?i)SSH-([\d.]+)-(\S+)", banner)
    if m:
        return "ssh", f"SSH-{m.group(1)}-{m.group(2)}"

    # HTTP Server header
    server = _extract_http_server(banner)
    if server:
        svc = "http"
        return svc, server

    if "nginx" in lower:
        m = re.search(r"(?i)nginx/?([\d.]+)", banner)
        return "http", f"nginx/{m.group(1)}" if m else "nginx"
    if "apache" in lower:
        m = re.search(r"(?i)apache/?([\d.]+)", banner)
        return "http", f"Apache/{m.group(1)}" if m else "Apache"
    if "microsoft-iis" in lower:
        m = re.search(r"(?i)microsoft-iis/?([\d.]+)", banner)
        return "http", f"Microsoft-IIS/{m.group(1)}" if m else "Microsoft-IIS"

    if "mysql" in lower or "mariadb" in lower:
        m = re.search(r"(?i)(mysql|mariadb)[^\d]*([\d.]+)?", banner)
        if m:
            name = m.group(1)
            ver = m.group(2)
            return "mysql", f"{name} {ver}".strip() if ver else name
        return "mysql", None

    if "postgresql" in lower:
        m = re.search(r"(?i)postgresql\s*([\d.]+)?", banner)
        return "postgresql", f"PostgreSQL {m.group(1)}" if m and m.group(1) else "PostgreSQL"

    if "redis" in lower:
        m = re.search(r"(?i)redis_version:([\d.]+)", banner)
        return "redis", f"Redis {m.group(1)}" if m else "Redis"

    if re.search(r"(?i)\b(ftp|filezilla|vsftpd|proftpd)\b", banner):
        m = re.search(r"(?i)(filezilla|vsftpd|proftpd)[^\d]*([\d.]+)?", banner)
        if m:
            return "ftp", f"{m.group(1)} {m.group(2)}".strip() if m.group(2) else m.group(1)
        return "ftp", None

    if re.search(r"(?i)(smtp|esmtp|postfix|exim)", banner):
        m = re.search(r"(?i)(postfix|exim)\s*([\d.]+)?", banner)
        if m:
            return "smtp", f"{m.group(1)} {m.group(2)}".strip() if m.group(2) else m.group(1)
        return "smtp", None

    return None, None


def identify_service(port: int, banner: str = "") -> Dict[str, Optional[str]]:
    """
    Identify service name and version from port + banner.

    Returns dict: service, version, banner
    """
    service = PORT_SERVICE_MAP.get(port, "unknown")
    version: Optional[str] = None

    if banner:
        detected_svc, detected_ver = _match_version_patterns(banner)
        if detected_svc:
            # Prefer banner-derived name when port map is generic/unknown
            if service in ("unknown", "http-proxy", "https-alt", "https", "http") or detected_svc == service:
                service = detected_svc if service in ("unknown", "http-proxy", "https-alt") else service
                # For http(s) ports keep http/https naming
                if port in (443, 8443) and detected_svc == "http":
                    service = "https"
                elif port in (80, 8080, 8000, 8888) and detected_svc == "http":
                    service = "http"
                elif service == "unknown":
                    service = detected_svc
            if detected_ver:
                version = detected_ver
            elif detected_svc and not version:
                # use full server string if present
                server = _extract_http_server(banner)
                if server:
                    version = server

        # SSH raw line as version fallback
        if service == "ssh" and not version:
            m = re.search(r"(?i)(SSH-\S+)", banner)
            if m:
                version = m.group(1)

    # Normalize https service name
    if port in (443, 8443) and service == "http":
        service = "https"

    return {
        "service": service,
        "version": version,
        "banner": banner or None,
    }


def guess_os(port_details: List[Dict], banners: Optional[List[str]] = None) -> str:
    """
    Heuristic OS guess based on open services and banners.
    Not a replacement for full OS fingerprinting.
    """
    texts = []
    for d in port_details:
        if d.get("version"):
            texts.append(str(d["version"]))
        if d.get("banner"):
            texts.append(str(d["banner"]))
        if d.get("service"):
            texts.append(str(d["service"]))
    if banners:
        texts.extend(banners)

    blob = " ".join(texts).lower()
    ports = {d.get("port") for d in port_details}

    scores = {
        "Windows": 0,
        "Linux": 0,
        "macOS": 0,
        "Network Device": 0,
        "Unknown": 0,
    }

    # Port-based hints
    if 3389 in ports or 445 in ports or 135 in ports or 139 in ports:
        scores["Windows"] += 3
    if 22 in ports:
        scores["Linux"] += 1
    if 548 in ports:
        scores["macOS"] += 2
    if 161 in ports or 23 in ports:
        scores["Network Device"] += 1

    # Banner hints
    windows_kw = ["microsoft", "iis", "windows", "win32", "rdp", "mssql", "microsoft-ds"]
    linux_kw = ["ubuntu", "debian", "centos", "redhat", "rhel", "linux", "openssh", "nginx", "postfix", "unix"]
    mac_kw = ["darwin", "mac os", "macos"]
    network_kw = ["cisco", "juniper", "huawei", "mikrotik", "vyos", "routeros"]

    for kw in windows_kw:
        if kw in blob:
            scores["Windows"] += 2
    for kw in linux_kw:
        if kw in blob:
            scores["Linux"] += 2
    for kw in mac_kw:
        if kw in blob:
            scores["macOS"] += 3
    for kw in network_kw:
        if kw in blob:
            scores["Network Device"] += 3

    # OpenSSH strongly suggests non-Windows historically (though Windows now has it)
    if "openssh" in blob and 3389 not in ports and 445 not in ports:
        scores["Linux"] += 1

    best = max(scores.items(), key=lambda x: x[1])
    if best[1] <= 0:
        return "Unknown"
    # Tie-break
    tied = [k for k, v in scores.items() if v == best[1] and k != "Unknown"]
    if len(tied) > 1:
        return "/".join(sorted(tied))
    return best[0]


def enrich_host_ports(
    ip: str,
    open_ports: List[Dict],
    banner_timeout: float = 1.5,
    grab: bool = True,
) -> Dict:
    """
    Build full asset record for one host:
    {ip, ports: [{port, service, version, banner?}], os}
    """
    details: List[Dict] = []
    for item in open_ports:
        port = item["port"]
        banner = ""
        if grab:
            banner = grab_banner(ip, port, timeout=banner_timeout)
        info = identify_service(port, banner)
        entry = {
            "port": port,
            "service": info["service"],
            "version": info["version"],
        }
        if banner:
            entry["banner"] = banner
        if "latency_ms" in item:
            entry["latency_ms"] = item["latency_ms"]
        details.append(entry)

    details.sort(key=lambda x: x["port"])
    os_name = guess_os(details)
    return {
        "ip": ip,
        "ports": details,
        "os": os_name,
    }