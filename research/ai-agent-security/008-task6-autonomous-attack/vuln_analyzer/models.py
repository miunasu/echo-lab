"""Data models for vulnerability impact analysis."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Asset:
    """Single asset entry from inventory."""

    ip: str
    port: Optional[int] = None
    service: str = ""
    product: str = ""
    version: str = ""
    vendor: str = ""
    os: str = ""
    tags: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        endpoint = self.ip
        if self.port is not None:
            endpoint = f"{self.ip}:{self.port}"
        product_part = self.product or self.service or "unknown"
        if self.version:
            product_part = f"{product_part} {self.version}"
        return f"{endpoint} ({product_part})"

    # Generic network service names that should not drive CVE search alone
    _GENERIC_SERVICES = frozenset({
        "ssh", "http", "https", "ftp", "sftp", "smtp", "pop3", "imap",
        "dns", "dhcp", "smb", "rdp", "vnc", "telnet", "mysql", "mssql",
        "postgres", "postgresql", "redis", "mongodb", "ldap", "ntp",
        "snmp", "tcp", "udp", "ssl", "tls", "www", "web", "api",
    })

    @property
    def search_keywords(self) -> List[str]:
        keywords: List[str] = []
        if self.product and self.version:
            keywords.append(f"{self.product} {self.version}")
        if self.product:
            keywords.append(self.product)
        # Only use service as keyword when it is specific (not generic proto name)
        # or when product is empty / identical to service.
        svc = (self.service or "").strip()
        if svc:
            svc_l = svc.lower()
            product_l = (self.product or "").strip().lower()
            if svc_l not in self._GENERIC_SERVICES or not product_l or svc_l == product_l:
                if svc_l not in {k.lower() for k in keywords}:
                    keywords.append(svc)
        if self.vendor and self.product:
            keywords.append(f"{self.vendor} {self.product}")
        # de-duplicate while preserving order
        seen = set()
        unique: List[str] = []
        for kw in keywords:
            key = kw.strip().lower()
            if key and key not in seen:
                seen.add(key)
                unique.append(kw.strip())
        return unique


@dataclass
class CVEInfo:
    """Normalized CVE record."""

    cve_id: str
    description: str = ""
    cvss: float = 0.0
    severity: str = "UNKNOWN"
    vector: str = ""
    published: str = ""
    last_modified: str = ""
    exploit_available: bool = False
    references: List[str] = field(default_factory=list)
    cwe_ids: List[str] = field(default_factory=list)
    affected_products: List[str] = field(default_factory=list)
    source: str = "nvd"

    def to_report_dict(self) -> Dict[str, Any]:
        return {
            "cve_id": self.cve_id,
            "cvss": self.cvss,
            "severity": self.severity,
            "description": self.description,
            "exploit_available": self.exploit_available,
            "vector": self.vector,
            "published": self.published,
            "references": self.references[:10],
            "cwe_ids": self.cwe_ids,
        }


@dataclass
class AssetReport:
    """Vulnerability report for one asset."""

    asset: str
    cves: List[Dict[str, Any]] = field(default_factory=list)
    priority: str = "INFO"
    remediation: List[str] = field(default_factory=list)
    patch_priority_score: float = 0.0
    matched_keywords: List[str] = field(default_factory=list)
    cve_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset": self.asset,
            "cves": self.cves,
            "priority": self.priority,
            "remediation": self.remediation,
            "patch_priority_score": round(self.patch_priority_score, 2),
            "cve_count": self.cve_count,
            "matched_keywords": self.matched_keywords,
        }


def asset_from_dict(data: Dict[str, Any]) -> Asset:
    """Build Asset from flexible JSON inventory fields."""
    ip = str(
        data.get("ip")
        or data.get("host")
        or data.get("address")
        or data.get("asset_ip")
        or "unknown"
    )
    port_val = data.get("port")
    port: Optional[int]
    try:
        port = int(port_val) if port_val is not None else None
    except (TypeError, ValueError):
        port = None

    product = str(
        data.get("product")
        or data.get("software")
        or data.get("name")
        or data.get("application")
        or ""
    )
    service = str(data.get("service") or data.get("protocol") or product or "")
    version = str(data.get("version") or data.get("ver") or "")
    vendor = str(data.get("vendor") or data.get("manufacturer") or "")
    os_name = str(data.get("os") or data.get("operating_system") or "")
    tags = data.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    return Asset(
        ip=ip,
        port=port,
        service=service,
        product=product or service,
        version=version,
        vendor=vendor,
        os=os_name,
        tags=list(tags),
        raw=dict(data),
    )


def severity_rank(severity: str) -> int:
    order = {
        "CRITICAL": 4,
        "HIGH": 3,
        "MEDIUM": 2,
        "LOW": 1,
        "NONE": 0,
        "UNKNOWN": 0,
        "INFO": 0,
    }
    return order.get((severity or "UNKNOWN").upper(), 0)