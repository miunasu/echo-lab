"""Offline / local CVE database loader and query helpers."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from models import CVEInfo

logger = logging.getLogger(__name__)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


class OfflineCVEDatabase:
    """
    Local CVE store for offline analysis.

    Expected JSON formats (auto-detected):
    1) {"cves": [ {...}, ... ]}
    2) [ {...}, ... ]
    3) {"CVE-YYYY-NNNN": {...}, ...}

    Each CVE object supports flexible field names:
      cve_id / id / cve
      description / summary / desc
      cvss / cvss_score / score / base_score
      severity / base_severity
      exploit_available / has_exploit / exploit
      products / product / affected / keywords  (list or string)
      version / versions
      references / refs
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.records: List[CVEInfo] = []
        self._product_index: Dict[str, List[int]] = {}
        self._load()

    def _load(self) -> None:
        if not self.db_path.exists():
            raise FileNotFoundError(f"Offline CVE database not found: {self.db_path}")

        with self.db_path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)

        items = self._normalize_raw(raw)
        for item in items:
            cve = self._to_cveinfo(item)
            if cve:
                idx = len(self.records)
                self.records.append(cve)
                for token in self._index_tokens(item, cve):
                    self._product_index.setdefault(token, []).append(idx)

        logger.info("Loaded %d CVE records from %s", len(self.records), self.db_path)

    @staticmethod
    def _normalize_raw(raw: Any) -> List[Dict[str, Any]]:
        if isinstance(raw, list):
            return [x for x in raw if isinstance(x, dict)]
        if isinstance(raw, dict):
            if "cves" in raw and isinstance(raw["cves"], list):
                return [x for x in raw["cves"] if isinstance(x, dict)]
            if "vulnerabilities" in raw and isinstance(raw["vulnerabilities"], list):
                # NVD-like dump
                out: List[Dict[str, Any]] = []
                for v in raw["vulnerabilities"]:
                    if isinstance(v, dict) and "cve" in v:
                        out.append(v["cve"])
                    elif isinstance(v, dict):
                        out.append(v)
                return out
            # mapping id -> object
            out = []
            for key, val in raw.items():
                if key in ("metadata", "version", "generated_at"):
                    continue
                if isinstance(val, dict):
                    obj = dict(val)
                    obj.setdefault("cve_id", key)
                    out.append(obj)
            return out
        raise ValueError("Unsupported offline DB JSON structure")

    @staticmethod
    def _to_cveinfo(item: Dict[str, Any]) -> Optional[CVEInfo]:
        cve_id = (
            item.get("cve_id")
            or item.get("id")
            or item.get("cve")
            or item.get("CVE")
            or ""
        )
        cve_id = str(cve_id).strip().upper()
        if not cve_id:
            return None

        description = str(
            item.get("description")
            or item.get("summary")
            or item.get("desc")
            or ""
        ).strip()

        score_raw = (
            item.get("cvss")
            if item.get("cvss") is not None
            else item.get("cvss_score")
            if item.get("cvss_score") is not None
            else item.get("score")
            if item.get("score") is not None
            else item.get("base_score")
            if item.get("base_score") is not None
            else 0.0
        )
        try:
            cvss = float(score_raw)
        except (TypeError, ValueError):
            cvss = 0.0

        severity = str(
            item.get("severity")
            or item.get("base_severity")
            or OfflineCVEDatabase._score_to_severity(cvss)
        ).upper()

        exploit_val = item.get("exploit_available")
        if exploit_val is None:
            exploit_val = item.get("has_exploit", item.get("exploit", False))
        exploit_available = bool(exploit_val)

        refs = item.get("references") or item.get("refs") or []
        if isinstance(refs, str):
            refs = [refs]

        cwes = item.get("cwe_ids") or item.get("cwes") or item.get("cwe") or []
        if isinstance(cwes, str):
            cwes = [cwes]

        products = item.get("affected_products") or item.get("products") or item.get("product") or []
        if isinstance(products, str):
            products = [products]

        return CVEInfo(
            cve_id=cve_id,
            description=description,
            cvss=cvss,
            severity=severity,
            vector=str(item.get("vector") or item.get("cvss_vector") or ""),
            published=str(item.get("published") or item.get("published_date") or ""),
            last_modified=str(item.get("last_modified") or ""),
            exploit_available=exploit_available,
            references=[str(r) for r in refs],
            cwe_ids=[str(c).upper() for c in cwes],
            affected_products=[str(p) for p in products],
            source="offline",
        )

    @staticmethod
    def _score_to_severity(score: float) -> str:
        if score >= 9.0:
            return "CRITICAL"
        if score >= 7.0:
            return "HIGH"
        if score >= 4.0:
            return "MEDIUM"
        if score > 0:
            return "LOW"
        return "NONE"

    @staticmethod
    def _index_tokens(item: Dict[str, Any], cve: CVEInfo) -> Set[str]:
        tokens: Set[str] = set()
        for p in cve.affected_products:
            tokens.add(_norm(p))
            # also index CPE product component if present
            if p.startswith("cpe:"):
                parts = p.split(":")
                if len(parts) >= 5:
                    tokens.add(_norm(parts[3]))  # vendor
                    tokens.add(_norm(parts[4]))  # product
                    if len(parts) >= 6 and parts[5] not in ("*", "-"):
                        tokens.add(_norm(f"{parts[4]} {parts[5]}"))

        for key in ("keywords", "keyword", "product", "products", "software", "service"):
            val = item.get(key)
            if isinstance(val, list):
                for v in val:
                    tokens.add(_norm(str(v)))
            elif isinstance(val, str) and val.strip():
                tokens.add(_norm(val))

        versions = item.get("versions") or item.get("version") or []
        if isinstance(versions, str):
            versions = [versions]
        product_name = item.get("product") or item.get("software")
        if isinstance(product_name, list) and product_name:
            product_name = product_name[0]
        if product_name and versions:
            for ver in versions:
                tokens.add(_norm(f"{product_name} {ver}"))

        # description tokens are NOT fully indexed (too noisy); keep cve id
        tokens.add(_norm(cve.cve_id))
        tokens.discard("")
        return tokens

    _GENERIC_QUERY_TERMS = frozenset({
        "ssh", "http", "https", "ftp", "sftp", "smtp", "smb", "rdp",
        "tcp", "udp", "ssl", "tls", "www", "web", "api", "mysql",
        "dns", "ldap", "snmp", "telnet", "vnc",
    })

    def search(
        self,
        product: str = "",
        version: str = "",
        keywords: Optional[Iterable[str]] = None,
        service: str = "",
    ) -> List[CVEInfo]:
        """Return CVEs matching product/version/keywords."""
        queries: List[str] = []
        if product and version:
            queries.append(_norm(f"{product} {version}"))
        if product:
            queries.append(_norm(product))
        # Avoid ultra-generic service tokens (e.g. http matching Apache httpd)
        if service and _norm(service) not in self._GENERIC_QUERY_TERMS:
            queries.append(_norm(service))
        if keywords:
            for kw in keywords:
                q = _norm(kw)
                if q and q not in self._GENERIC_QUERY_TERMS:
                    queries.append(q)

        # de-dupe queries
        seen_q: Set[str] = set()
        uniq_queries: List[str] = []
        for q in queries:
            if q and q not in seen_q:
                seen_q.add(q)
                uniq_queries.append(q)

        matched_indices: Set[int] = set()

        # 1) direct index hit
        for q in uniq_queries:
            for idx in self._product_index.get(q, []):
                matched_indices.add(idx)

        # 2) controlled substring match (skip very short / generic queries)
        for q in uniq_queries:
            if len(q) < 4:
                continue
            for key, indices in self._product_index.items():
                if q == key:
                    matched_indices.update(indices)
                elif len(q) >= 5 and (q in key or key in q):
                    # require the shorter side to be reasonably specific
                    shorter, longer = (q, key) if len(q) <= len(key) else (key, q)
                    if len(shorter) >= 5 and shorter in longer:
                        matched_indices.update(indices)

        # 3) fallback scan: product must appear in description / affected list
        if product:
            p_norm = _norm(product)
            v_norm = _norm(version) if version else ""
            for idx, rec in enumerate(self.records):
                if idx in matched_indices:
                    continue
                hay = _norm(
                    " ".join(rec.affected_products)
                    + " "
                    + rec.description
                )
                if p_norm in hay:
                    # if version supplied, prefer version evidence but do not require
                    # it exclusively — many CVE texts omit exact version strings
                    if v_norm and v_norm in hay:
                        matched_indices.add(idx)
                    elif not v_norm:
                        matched_indices.add(idx)
                    else:
                        # product hit without version still accepted for offline recall
                        matched_indices.add(idx)

        results = [self.records[i] for i in sorted(matched_indices)]
        results.sort(key=lambda c: (c.cvss, c.exploit_available), reverse=True)
        return results

    def get(self, cve_id: str) -> Optional[CVEInfo]:
        target = (cve_id or "").strip().upper()
        for rec in self.records:
            if rec.cve_id == target:
                return rec
        return None

    def __len__(self) -> int:
        return len(self.records)