"""NVD API 2.0 client for CVE lookups."""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

import requests

from models import CVEInfo

logger = logging.getLogger(__name__)

NVD_API_BASE = "https://services.nvd.nist.gov/rest/json/cves/2.0"
DEFAULT_TIMEOUT = 30
# Without API key NVD allows ~5 requests / 30s; with key ~50 / 30s
MIN_INTERVAL_NO_KEY = 6.5
MIN_INTERVAL_WITH_KEY = 0.7

# Public exploit / PoC indicators in reference tags or URLs
EXPLOIT_HINTS = (
    "exploit",
    "exploits",
    "poc",
    "proof-of-concept",
    "proof_of_concept",
    "metasploit",
    "exploit-db",
    "exploitdb",
    "github.com",
    "packetstorm",
    "seebug",
)


class NVDClient:
    """Thin wrapper around NVD CVE API 2.0."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        max_results: int = 50,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("NVD_API_KEY") or os.environ.get("NIST_API_KEY")
        self.timeout = timeout
        self.max_results = max_results
        self.session = session or requests.Session()
        self._last_request_ts = 0.0
        self.min_interval = MIN_INTERVAL_WITH_KEY if self.api_key else MIN_INTERVAL_NO_KEY

    def _headers(self) -> Dict[str, str]:
        headers = {
            "User-Agent": "vuln-analyzer/1.0 (security-risk-assessment)",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["apiKey"] = self.api_key
        return headers

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request_ts
        wait = self.min_interval - elapsed
        if wait > 0:
            time.sleep(wait)

    def _get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._throttle()
        try:
            resp = self.session.get(
                NVD_API_BASE,
                params=params,
                headers=self._headers(),
                timeout=self.timeout,
            )
            self._last_request_ts = time.time()
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "30"))
                logger.warning("NVD rate limited, sleeping %ss", retry_after)
                time.sleep(retry_after)
                resp = self.session.get(
                    NVD_API_BASE,
                    params=params,
                    headers=self._headers(),
                    timeout=self.timeout,
                )
                self._last_request_ts = time.time()
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.error("NVD API request failed: %s", exc)
            return {}

    def search_by_keyword(
        self,
        keyword: str,
        results_per_page: Optional[int] = None,
    ) -> List[CVEInfo]:
        """Search CVEs by free-text keyword (product/version)."""
        keyword = (keyword or "").strip()
        if not keyword:
            return []

        rpp = min(results_per_page or self.max_results, 200)
        params: Dict[str, Any] = {
            "keywordSearch": keyword,
            "resultsPerPage": rpp,
        }
        # Prefer exact phrase matching when multi-word
        if " " in keyword:
            params["keywordExactMatch"] = ""

        data = self._get(params)
        return self._parse_vulnerabilities(data)

    def search_by_cpe(self, cpe_name: str) -> List[CVEInfo]:
        """Search CVEs matching a CPE 2.3 URI."""
        cpe_name = (cpe_name or "").strip()
        if not cpe_name:
            return []
        params = {
            "cpeName": cpe_name,
            "resultsPerPage": min(self.max_results, 200),
        }
        data = self._get(params)
        return self._parse_vulnerabilities(data)

    def get_cve(self, cve_id: str) -> Optional[CVEInfo]:
        cve_id = (cve_id or "").strip().upper()
        if not cve_id:
            return None
        data = self._get({"cveId": cve_id})
        items = self._parse_vulnerabilities(data)
        return items[0] if items else None

    def _parse_vulnerabilities(self, data: Dict[str, Any]) -> List[CVEInfo]:
        vulns = data.get("vulnerabilities") or []
        results: List[CVEInfo] = []
        for item in vulns:
            cve_obj = item.get("cve") or {}
            parsed = self._parse_single_cve(cve_obj)
            if parsed:
                results.append(parsed)
        return results

    def _parse_single_cve(self, cve_obj: Dict[str, Any]) -> Optional[CVEInfo]:
        cve_id = cve_obj.get("id")
        if not cve_id:
            return None

        description = self._extract_description(cve_obj)
        cvss, severity, vector = self._extract_cvss(cve_obj)
        refs = self._extract_references(cve_obj)
        exploit = self._detect_exploit(cve_obj, refs, description)
        cwes = self._extract_cwes(cve_obj)
        products = self._extract_products(cve_obj)

        return CVEInfo(
            cve_id=cve_id,
            description=description,
            cvss=cvss,
            severity=severity,
            vector=vector,
            published=str(cve_obj.get("published") or ""),
            last_modified=str(cve_obj.get("lastModified") or ""),
            exploit_available=exploit,
            references=refs,
            cwe_ids=cwes,
            affected_products=products,
            source="nvd",
        )

    @staticmethod
    def _extract_description(cve_obj: Dict[str, Any]) -> str:
        for desc in cve_obj.get("descriptions") or []:
            if (desc.get("lang") or "").lower() == "en":
                return (desc.get("value") or "").strip()
        descs = cve_obj.get("descriptions") or []
        if descs:
            return (descs[0].get("value") or "").strip()
        return ""

    @staticmethod
    def _extract_cvss(cve_obj: Dict[str, Any]) -> tuple:
        metrics = cve_obj.get("metrics") or {}
        # Prefer v3.1 > v3.0 > v2
        for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
            entries = metrics.get(key) or []
            if not entries:
                continue
            # Prefer Primary metric
            primary = None
            for entry in entries:
                if (entry.get("type") or "").lower() == "primary":
                    primary = entry
                    break
            entry = primary or entries[0]
            cvss_data = entry.get("cvssData") or {}
            score = cvss_data.get("baseScore")
            if score is None:
                score = entry.get("baseScore") or 0.0
            try:
                score_f = float(score)
            except (TypeError, ValueError):
                score_f = 0.0
            severity = (
                cvss_data.get("baseSeverity")
                or entry.get("baseSeverity")
                or NVDClient._score_to_severity(score_f)
            )
            vector = cvss_data.get("vectorString") or ""
            return score_f, str(severity).upper(), vector
        return 0.0, "UNKNOWN", ""

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
    def _extract_references(cve_obj: Dict[str, Any]) -> List[str]:
        urls: List[str] = []
        for ref in cve_obj.get("references") or []:
            url = ref.get("url")
            if url:
                urls.append(url)
        return urls

    @staticmethod
    def _detect_exploit(
        cve_obj: Dict[str, Any],
        refs: List[str],
        description: str,
    ) -> bool:
        # Reference tags from NVD
        for ref in cve_obj.get("references") or []:
            tags = [str(t).lower() for t in (ref.get("tags") or [])]
            if any(t in ("exploit", "technical description") for t in tags):
                # "Exploit" tag is strong signal
                if "exploit" in tags:
                    return True
            url = (ref.get("url") or "").lower()
            if any(h in url for h in ("exploit-db", "exploitdb", "metasploit", "packetstorm")):
                return True

        blob = " ".join(refs).lower() + " " + (description or "").lower()
        # Conservative: only strong public-exploit markers
        strong = ("exploit-db.com", "exploitdb", "metasploit", "packetstormsecurity")
        if any(s in blob for s in strong):
            return True
        return False

    @staticmethod
    def _extract_cwes(cve_obj: Dict[str, Any]) -> List[str]:
        cwes: List[str] = []
        for weakness in cve_obj.get("weaknesses") or []:
            for desc in weakness.get("description") or []:
                val = desc.get("value") or ""
                if val.upper().startswith("CWE-"):
                    cwes.append(val.upper())
        # unique preserve order
        seen = set()
        out: List[str] = []
        for c in cwes:
            if c not in seen:
                seen.add(c)
                out.append(c)
        return out

    @staticmethod
    def _extract_products(cve_obj: Dict[str, Any]) -> List[str]:
        products: List[str] = []
        for conf in cve_obj.get("configurations") or []:
            for node in conf.get("nodes") or []:
                for match in node.get("cpeMatch") or []:
                    criteria = match.get("criteria") or match.get("cpe23Uri") or ""
                    if criteria:
                        products.append(criteria)
        return products[:20]