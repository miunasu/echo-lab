"""Impact scoring, remediation advice, and report generation."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from models import (
    Asset,
    AssetReport,
    CVEInfo,
    asset_from_dict,
    severity_rank,
)
from nvd_client import NVDClient
from offline_db import OfflineCVEDatabase

logger = logging.getLogger(__name__)

SEVERITY_PRIORITY = {
    "CRITICAL": "CRITICAL",
    "HIGH": "HIGH",
    "MEDIUM": "MEDIUM",
    "LOW": "LOW",
    "NONE": "INFO",
    "UNKNOWN": "INFO",
    "INFO": "INFO",
}


def load_assets(path: str | Path) -> List[Asset]:
    """Load asset inventory JSON (list or {assets: [...]})."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)

    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        if isinstance(raw.get("assets"), list):
            items = raw["assets"]
        elif isinstance(raw.get("hosts"), list):
            items = raw["hosts"]
        elif isinstance(raw.get("inventory"), list):
            items = raw["inventory"]
        else:
            # single asset object
            items = [raw]
    else:
        raise ValueError(f"Unsupported assets format in {path}")

    assets = [asset_from_dict(x) for x in items if isinstance(x, dict)]
    if not assets:
        raise ValueError(f"No assets found in {path}")
    return assets


def compute_impact_score(cve: CVEInfo) -> float:
    """
    Patch priority contribution for a single CVE.
    Base = CVSS; exploit multiplies; severity floor applied.
    Range roughly 0-15.
    """
    score = float(cve.cvss or 0.0)
    if cve.exploit_available:
        score *= 1.35
        score += 1.5
    # slight bump for known dangerous CWEs
    dangerous_cwes = {"CWE-78", "CWE-79", "CWE-89", "CWE-94", "CWE-119", "CWE-287", "CWE-502", "CWE-787"}
    if any(c.upper() in dangerous_cwes for c in (cve.cwe_ids or [])):
        score += 0.5
    return round(score, 2)


def aggregate_priority(cves: Sequence[CVEInfo], total_score: float) -> str:
    if not cves:
        return "INFO"
    max_sev = max(cves, key=lambda c: (severity_rank(c.severity), c.cvss))
    base = SEVERITY_PRIORITY.get(max_sev.severity.upper(), "INFO")
    # escalate when many highs or critical total score
    high_count = sum(1 for c in cves if severity_rank(c.severity) >= 3)
    if total_score >= 20 or high_count >= 3:
        if severity_rank(base) < severity_rank("CRITICAL"):
            # do not invent CRITICAL without a critical CVE unless score extreme
            if any(severity_rank(c.severity) >= 4 for c in cves) or total_score >= 30:
                return "CRITICAL"
            return "HIGH" if severity_rank(base) < 3 else base
    if any(c.exploit_available and severity_rank(c.severity) >= 3 for c in cves):
        if severity_rank(base) < 3:
            return "HIGH"
    return base


def build_remediation(asset: Asset, cves: Sequence[CVEInfo], priority: str) -> List[str]:
    tips: List[str] = []
    product = asset.product or asset.service or "the service"
    version = asset.version

    if not cves:
        tips.append(f"No matching CVEs found for {product}. Keep firmware/packages updated and re-scan periodically.")
        return tips

    if version:
        tips.append(
            f"Upgrade {product} from version {version} to the latest vendor-supported release that addresses listed CVEs."
        )
    else:
        tips.append(f"Identify exact {product} version and upgrade to a patched release.")

    exploit_cves = [c.cve_id for c in cves if c.exploit_available]
    if exploit_cves:
        tips.append(
            "Public exploit activity indicated for: "
            + ", ".join(exploit_cves[:8])
            + ". Prioritize emergency patching or compensating controls."
        )

    critical_high = [c.cve_id for c in cves if severity_rank(c.severity) >= 3]
    if critical_high:
        tips.append(
            "Apply vendor security advisories for: "
            + ", ".join(critical_high[:10])
            + "."
        )

    if asset.port:
        tips.append(
            f"Restrict network exposure of {asset.ip}:{asset.port} via firewall/ACL until patched."
        )
    else:
        tips.append(f"Limit network exposure of host {asset.ip} until patches are applied.")

    if priority in ("CRITICAL", "HIGH"):
        tips.append("Schedule patch deployment within 72 hours; validate via rescanning.")
    elif priority == "MEDIUM":
        tips.append("Schedule patch deployment within 2 weeks as part of normal change windows.")
    else:
        tips.append("Track in backlog; patch during next maintenance cycle.")

    tips.append("Verify backup/restore readiness before major version upgrades.")
    return tips


def dedupe_cves(cves: Iterable[CVEInfo]) -> List[CVEInfo]:
    best: Dict[str, CVEInfo] = {}
    for cve in cves:
        existing = best.get(cve.cve_id)
        if existing is None:
            best[cve.cve_id] = cve
            continue
        # keep richer / higher score record
        if (cve.cvss, cve.exploit_available, len(cve.description)) > (
            existing.cvss,
            existing.exploit_available,
            len(existing.description),
        ):
            best[cve.cve_id] = cve
    return sorted(best.values(), key=lambda c: (c.cvss, c.exploit_available), reverse=True)


def filter_relevant(cves: Sequence[CVEInfo], asset: Asset, max_items: int = 25) -> List[CVEInfo]:
    """Relevance filter: require product/vendor signal; CVSS alone is not enough."""
    if not cves:
        return []
    product = (asset.product or "").lower().strip()
    service = (asset.service or "").lower().strip()
    version = (asset.version or "").lower().strip()
    vendor = (asset.vendor or "").lower().strip()
    # Use product primarily; fall back to service only if product missing
    primary = product or service

    scored: List[Tuple[float, CVEInfo]] = []
    for cve in cves:
        rel = 0.0
        product_hit = False
        blob = (
            cve.description
            + " "
            + " ".join(cve.affected_products)
            + " "
            + " ".join(getattr(cve, "references", []) or [])
        ).lower()

        if primary and primary in blob:
            rel += 3.0
            product_hit = True
        # multi-token product e.g. "apache httpd" / "windows server"
        if primary and " " in primary:
            tokens = [t for t in primary.split() if len(t) > 2]
            if tokens and all(t in blob for t in tokens):
                rel += 2.5
                product_hit = True
        if vendor and vendor in blob:
            rel += 1.5
            product_hit = True
        if version and version in blob and product_hit:
            rel += 2.0
        # weak service-only hit does not count as product_hit for generic services
        if service and service not in Asset._GENERIC_SERVICES and service in blob:
            rel += 1.0
            product_hit = True

        rel += float(cve.cvss) / 10.0
        if cve.exploit_available:
            rel += 0.5

        # Drop entries with no product/vendor evidence
        if primary and not product_hit:
            continue
        scored.append((rel, cve))

    scored.sort(key=lambda x: x[0], reverse=True)
    filtered = [c for rel, c in scored if rel >= 1.0]
    if not filtered and scored:
        # keep top few only if something scored but below threshold
        filtered = [c for _, c in scored[:3]]
    return filtered[:max_items]


class VulnAnalyzer:
    """Orchestrates asset loading, CVE lookup, scoring, and reporting."""

    def __init__(
        self,
        offline: bool = False,
        offline_db_path: Optional[str] = None,
        api_key: Optional[str] = None,
        max_cves_per_asset: int = 25,
        online_fallback: bool = False,
    ) -> None:
        self.offline = offline
        self.max_cves_per_asset = max_cves_per_asset
        self.online_fallback = online_fallback
        self.offline_db: Optional[OfflineCVEDatabase] = None
        self.nvd: Optional[NVDClient] = None

        if offline or offline_db_path:
            if not offline_db_path:
                raise ValueError("--offline requires --db path to local CVE JSON database")
            self.offline_db = OfflineCVEDatabase(offline_db_path)
            self.offline = True

        if not self.offline or online_fallback:
            self.nvd = NVDClient(api_key=api_key, max_results=max_cves_per_asset)

    def lookup_cves(self, asset: Asset) -> Tuple[List[CVEInfo], List[str]]:
        keywords = asset.search_keywords
        collected: List[CVEInfo] = []

        if self.offline_db is not None:
            offline_hits = self.offline_db.search(
                product=asset.product,
                version=asset.version,
                service=asset.service,
                keywords=keywords,
            )
            collected.extend(offline_hits)
            logger.info(
                "Offline DB matched %d CVE(s) for %s",
                len(offline_hits),
                asset.display_name,
            )

        need_online = (not self.offline) or (self.online_fallback and not collected)
        if need_online and self.nvd is not None:
            seen_kw: Set[str] = set()
            for kw in keywords:
                key = kw.lower()
                if key in seen_kw:
                    continue
                seen_kw.add(key)
                try:
                    hits = self.nvd.search_by_keyword(kw)
                    collected.extend(hits)
                    logger.info("NVD keyword '%s' -> %d hit(s)", kw, len(hits))
                except Exception as exc:  # noqa: BLE001
                    logger.error("NVD search failed for '%s': %s", kw, exc)
                # stop early if enough candidates
                if len(dedupe_cves(collected)) >= self.max_cves_per_asset * 2:
                    break

        merged = dedupe_cves(collected)
        relevant = filter_relevant(merged, asset, max_items=self.max_cves_per_asset)
        return relevant, keywords

    def analyze_asset(self, asset: Asset) -> AssetReport:
        cves, keywords = self.lookup_cves(asset)
        per_scores = [compute_impact_score(c) for c in cves]
        total_score = round(sum(per_scores), 2) if per_scores else 0.0
        # weight top findings more for priority score display
        top = sorted(per_scores, reverse=True)[:5]
        patch_priority_score = round(sum(top), 2)
        priority = aggregate_priority(cves, total_score)
        remediation = build_remediation(asset, cves, priority)

        cve_dicts: List[Dict[str, Any]] = []
        for cve, impact in zip(cves, per_scores):
            d = cve.to_report_dict()
            d["impact_score"] = impact
            cve_dicts.append(d)

        return AssetReport(
            asset=asset.display_name,
            cves=cve_dicts,
            priority=priority,
            remediation=remediation,
            patch_priority_score=patch_priority_score,
            matched_keywords=keywords,
            cve_count=len(cve_dicts),
        )

    def analyze(self, assets: Sequence[Asset]) -> Dict[str, Any]:
        reports = [self.analyze_asset(a) for a in assets]
        summary = self._summary(reports)
        return {
            "summary": summary,
            "results": [r.to_dict() for r in reports],
        }

    def analyze_file(self, assets_path: str | Path) -> Dict[str, Any]:
        assets = load_assets(assets_path)
        report = self.analyze(assets)
        report["summary"]["assets_file"] = str(assets_path)
        report["summary"]["mode"] = "offline" if self.offline and not self.online_fallback else (
            "hybrid" if self.offline and self.online_fallback else "online"
        )
        return report

    @staticmethod
    def _summary(reports: Sequence[AssetReport]) -> Dict[str, Any]:
        priority_counts: Dict[str, int] = {
            "CRITICAL": 0,
            "HIGH": 0,
            "MEDIUM": 0,
            "LOW": 0,
            "INFO": 0,
        }
        total_cves = 0
        for r in reports:
            priority_counts[r.priority] = priority_counts.get(r.priority, 0) + 1
            total_cves += r.cve_count
        overall = "INFO"
        for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"):
            if priority_counts.get(level, 0) > 0:
                overall = level
                break
        return {
            "asset_count": len(reports),
            "total_cves": total_cves,
            "priority_counts": priority_counts,
            "overall_priority": overall,
        }


def write_report(report: Dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    logger.info("Report written to %s", path)