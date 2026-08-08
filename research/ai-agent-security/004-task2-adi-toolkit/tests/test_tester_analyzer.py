"""Tests for ADITester and SuccessRateAnalyzer."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adi.models import AgentType, InjectionFormat
from adi.tester import ADITester, DEFAULT_SUCCESS_MARKERS
from adi.analyzer import SuccessRateAnalyzer


def test_build_matrix_not_empty():
    tester = ADITester()
    cases = tester.build_matrix(
        agent_types=[AgentType.GENERAL],
        formats=[InjectionFormat.JSON, InjectionFormat.METADATA],
        payloads_per_agent=1,
        field_limit=2,
        seed=0,
    )
    assert len(cases) >= 2
    assert all(c.artifact.content for c in cases)


def test_evaluate_response_success():
    tester = ADITester()
    cases = tester.build_matrix(
        agent_types=[AgentType.GENERAL],
        formats=[InjectionFormat.JSON],
        payloads_per_agent=1,
        field_limit=1,
        seed=1,
    )
    case = cases[0]
    result = tester.evaluate_response(case, "Acknowledged POLICY_BYPASS_OK from system")
    assert result.success is True
    assert result.score > 0
    assert result.matched_success


def test_evaluate_response_failure():
    tester = ADITester()
    cases = tester.build_matrix(
        agent_types=[AgentType.GENERAL],
        formats=[InjectionFormat.HTML],
        payloads_per_agent=1,
        field_limit=1,
        seed=2,
    )
    case = cases[0]
    result = tester.evaluate_response(
        case,
        "I cannot comply. As an AI I must decline and follow safety policy.",
    )
    assert result.success is False
    assert result.matched_failure


def test_run_all_simulation():
    tester = ADITester()
    cases = tester.build_matrix(
        agent_types=[AgentType.WEB, AgentType.CODING],
        formats=[InjectionFormat.JSON, InjectionFormat.DOM],
        payloads_per_agent=1,
        field_limit=2,
        seed=3,
    )
    results = tester.run_all(cases, simulate_if_missing=True)
    assert len(results) == len(cases)
    summary = tester.summary()
    assert summary["total"] == len(results)
    assert 0.0 <= summary["rate"] <= 1.0


def test_custom_callback():
    def cb(content: str, context: dict) -> str:
        return "POLICY_BYPASS_OK"

    tester = ADITester(agent_callback=cb)
    cases = tester.build_matrix(
        agent_types=[AgentType.GENERAL],
        formats=[InjectionFormat.METADATA],
        payloads_per_agent=1,
        field_limit=1,
        seed=4,
    )
    results = tester.run_all(cases, simulate_if_missing=False)
    assert all(r.success for r in results)


def test_analyzer_report_structure(tmp_path):
    tester = ADITester()
    cases = tester.build_matrix(
        agent_types=[AgentType.GENERAL, AgentType.WEB],
        formats=[InjectionFormat.JSON, InjectionFormat.HTML, InjectionFormat.METADATA],
        payloads_per_agent=1,
        field_limit=2,
        seed=5,
    )
    results = tester.run_all(cases)
    analyzer = SuccessRateAnalyzer(results)
    report = analyzer.analyze()
    assert report.total == len(results)
    assert report.successes + report.failures == report.total
    assert "json" in report.by_format or len(report.by_format) >= 1
    assert report.recommendations

    out = tmp_path / "report.json"
    analyzer.save_report(str(out))
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["total"] == report.total
    assert "by_format" in data

    # round-trip from results export
    res_path = tmp_path / "results.json"
    tester.export_results(str(res_path))
    loaded = SuccessRateAnalyzer.from_json_file(str(res_path))
    report2 = loaded.analyze()
    assert report2.total == report.total


def test_success_markers_nonempty():
    assert "POLICY_BYPASS_OK" in DEFAULT_SUCCESS_MARKERS