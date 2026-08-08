"""
ADI (Agent Data Injection) Red Team Testing Toolkit.

Generate probabilistic-delimiter payloads, inject them into JSON/DOM/HTML
and trusted metadata fields, then measure which surfaces an agent is likely
to treat as authoritative context.
"""

from adi.models import (
    AgentType,
    InjectionFormat,
    PayloadConfig,
    PayloadResult,
    TestCase,
    TestResult,
    AnalysisReport,
)
from adi.payloads.generator import PayloadGenerator
from adi.formats.json_injector import JSONInjector
from adi.formats.dom_injector import DOMInjector
from adi.formats.html_injector import HTMLInjector
from adi.formats.metadata import MetadataInjector
from adi.tester import ADITester
from adi.analyzer import SuccessRateAnalyzer

__version__ = "1.0.0"
__all__ = [
    "AgentType",
    "InjectionFormat",
    "PayloadConfig",
    "PayloadResult",
    "TestCase",
    "TestResult",
    "AnalysisReport",
    "PayloadGenerator",
    "JSONInjector",
    "DOMInjector",
    "HTMLInjector",
    "MetadataInjector",
    "ADITester",
    "SuccessRateAnalyzer",
    "__version__",
]