"""Success-rate analysis for ADI test results."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence

from adi.models import AnalysisReport, TestResult, new_id


class SuccessRateAnalyzer:
    """Aggregate TestResults into per-dimension success statistics."""

    def __init__(self, results: Optional[Sequence[TestResult]] = None) -> None:
        self.results: List[TestResult] = list(results or [])

    def add(self, result: TestResult) -> None:
        self.results.append(result)

    def extend(self, results: Iterable[TestResult]) -> None:
        self.results.extend(results)

    def analyze(self) -> AnalysisReport:
        total = len(self.results)
        successes = sum(1 for r in self.results if r.success)
        failures = total - successes
        overall = (successes / total) if total else 0.0

        by_format = self._group_stats(lambda r: r.format or "unknown")
        by_agent = self._group_stats(lambda r: r.agent_type or "unknown")
        by_field = self._group_stats(lambda r: r.field_path or "unknown")
        by_strategy = self._group_stats(
            lambda r: (r.extra or {}).get("delimiter_strategy", "n/a")
        )

        # Top payloads by score
        ranked = sorted(self.results, key=lambda r: r.score, reverse=True)
        top = [
            {
                "result_id": r.result_id,
                "case_id": r.case_id,
                "score": r.score,
                "success": r.success,
                "format": r.format,
                "field_path": r.field_path,
                "agent_type": r.agent_type,
                "matched_success": r.matched_success,
            }
            for r in ranked[:10]
        ]

        report = AnalysisReport(
            report_id=new_id("report"),
            total=total,
            successes=successes,
            failures=failures,
            overall_rate=round(overall, 4),
            by_format=by_format,
            by_agent_type=by_agent,
            by_field_path=by_field,
            by_delimiter_strategy=by_strategy,
            top_payloads=top,
            recommendations=self._recommendations(by_format, by_field, by_agent, overall),
        )
        return report

    def _group_stats(self, key_fn) -> Dict[str, Dict[str, Any]]:
        buckets: Dict[str, List[TestResult]] = defaultdict(list)
        for r in self.results:
            buckets[str(key_fn(r))].append(r)
        out: Dict[str, Dict[str, Any]] = {}
        for key, items in buckets.items():
            s = sum(1 for i in items if i.success)
            t = len(items)
            avg_score = sum(i.score for i in items) / t if t else 0.0
            out[key] = {
                "total": t,
                "successes": s,
                "failures": t - s,
                "rate": round(s / t, 4) if t else 0.0,
                "avg_score": round(avg_score, 4),
            }
        return out

    def _recommendations(
        self,
        by_format: Dict[str, Dict[str, Any]],
        by_field: Dict[str, Dict[str, Any]],
        by_agent: Dict[str, Dict[str, Any]],
        overall: float,
    ) -> List[str]:
        recs: List[str] = []
        if not self.results:
            return ["No results to analyze. Run ADITester first."]

        # Hottest formats
        if by_format:
            hot_fmt = max(by_format.items(), key=lambda kv: kv[1]["rate"])
            cold_fmt = min(by_format.items(), key=lambda kv: kv[1]["rate"])
            recs.append(
                f"Highest success format: {hot_fmt[0]} ({hot_fmt[1]['rate']:.0%}). "
                f"Prioritize hardening parsers for this surface."
            )
            recs.append(
                f"Lowest success format: {cold_fmt[0]} ({cold_fmt[1]['rate']:.0%})."
            )

        # Hottest fields (top 3)
        if by_field:
            ranked_fields = sorted(
                by_field.items(), key=lambda kv: kv[1]["rate"], reverse=True
            )
            top_fields = [
                f"{name} ({stats['rate']:.0%})"
                for name, stats in ranked_fields[:3]
                if stats["total"] >= 1
            ]
            if top_fields:
                recs.append(
                    "Most injectable metadata/fields: " + ", ".join(top_fields) + ". "
                    "Treat these as untrusted even when labelled status/author/validation."
                )

        if by_agent:
            hot_agent = max(by_agent.items(), key=lambda kv: kv[1]["rate"])
            recs.append(
                f"Most susceptible agent type in this run: {hot_agent[0]} "
                f"({hot_agent[1]['rate']:.0%})."
            )

        if overall >= 0.5:
            recs.append(
                "Overall success rate is high (>=50%). Enforce strict separation "
                "between tool/API data and system instructions; strip delimiter-heavy "
                "tokens from untrusted fields."
            )
        elif overall >= 0.2:
            recs.append(
                "Moderate ADI susceptibility. Add allow-lists for trusted metadata "
                "keys and sanitize { } [ ] < > ` sequences in ingested content."
            )
        else:
            recs.append(
                "Low measured success rate. Continue monitoring; expand field coverage "
                "and real-agent callbacks for higher fidelity."
            )

        recs.append(
            "Defense checklist: (1) never promote author/status/validation fields to "
            "system rank, (2) neutralize probabilistic delimiter noise, "
            "(3) isolate HTML/DOM attribute text from instruction channels."
        )
        return recs

    def to_json(self, indent: int = 2) -> str:
        return self.analyze().to_json(indent=indent)

    def save_report(self, path: str) -> AnalysisReport:
        report = self.analyze()
        with open(path, "w", encoding="utf-8") as f:
            f.write(report.to_json())
        return report

    def print_summary(self) -> str:
        text = self.analyze().summary()
        print(text)
        return text

    @staticmethod
    def from_json_file(path: str) -> "SuccessRateAnalyzer":
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        results = []
        for item in raw:
            results.append(
                TestResult(
                    result_id=item.get("result_id", new_id("result")),
                    case_id=item.get("case_id", ""),
                    success=bool(item.get("success")),
                    score=float(item.get("score", 0)),
                    matched_success=list(item.get("matched_success") or []),
                    matched_failure=list(item.get("matched_failure") or []),
                    agent_response=item.get("agent_response", ""),
                    format=item.get("format", ""),
                    agent_type=item.get("agent_type", ""),
                    field_path=item.get("field_path", ""),
                    latency_ms=float(item.get("latency_ms") or 0),
                    error=item.get("error"),
                    extra=dict(item.get("extra") or {}),
                )
            )
        return SuccessRateAnalyzer(results)