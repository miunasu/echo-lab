"""Command-line interface for the ADI toolkit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from adi.models import AgentType, DelimiterStrategy, InjectionFormat, PayloadConfig
from adi.payloads.generator import PayloadGenerator
from adi.formats.json_injector import JSONInjector
from adi.formats.dom_injector import DOMInjector
from adi.formats.html_injector import HTMLInjector
from adi.formats.metadata import MetadataInjector
from adi.tester import ADITester
from adi.analyzer import SuccessRateAnalyzer


def _parse_agent(value: str) -> AgentType:
    return AgentType(value.lower())


def _parse_strategy(value: str) -> DelimiterStrategy:
    return DelimiterStrategy(value.lower())


def cmd_generate(args: argparse.Namespace) -> int:
    gen = PayloadGenerator()
    cfg = PayloadConfig(
        agent_type=_parse_agent(args.agent),
        instruction=args.instruction or PayloadConfig().instruction,
        delimiter_strategy=_parse_strategy(args.strategy),
        delimiter_prob=args.prob,
        seed=args.seed,
    )
    if args.batch > 1:
        results = gen.generate_batch(
            count=args.batch,
            agent_types=[cfg.agent_type],
            strategies=[cfg.delimiter_strategy],
            base_instruction=args.instruction,
            delimiter_prob=args.prob,
            seed=args.seed,
        )
    else:
        results = [
            gen.generate(
                config=cfg,
                instruction=args.instruction,
                template_name=args.template,
            )
        ]

    out_data = [r.to_dict() for r in results]
    text = json.dumps(out_data, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Wrote {len(results)} payload(s) -> {args.output}")
    else:
        print(text)
    return 0


def cmd_inject(args: argparse.Namespace) -> int:
    gen = PayloadGenerator()
    cfg = PayloadConfig(
        agent_type=_parse_agent(args.agent),
        delimiter_strategy=_parse_strategy(args.strategy),
        delimiter_prob=args.prob,
        seed=args.seed,
    )
    payload = gen.generate(
        config=cfg,
        instruction=args.instruction,
        template_name=args.template,
    )

    fmt = args.format.lower()
    field = args.field or ""
    if fmt == "json":
        art = JSONInjector().inject(payload, field_path=field)
    elif fmt == "dom":
        art = DOMInjector().inject(payload, field_path=field)
    elif fmt == "html":
        art = HTMLInjector().inject(payload, field_path=field)
    elif fmt == "metadata":
        art = MetadataInjector(style=args.meta_style).inject(payload, field_path=field)
    else:
        print(f"Unknown format: {fmt}", file=sys.stderr)
        return 2

    if args.output:
        Path(args.output).write_text(art.content, encoding="utf-8")
        print(f"Wrote artifact {art.artifact_id} ({art.format.value}:{art.field_path}) -> {args.output}")
    else:
        print(art.content)
    if args.dump_meta:
        print("---", file=sys.stderr)
        print(json.dumps(art.to_dict(), ensure_ascii=False, indent=2), file=sys.stderr)
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    tester = ADITester()
    agents = [_parse_agent(a) for a in args.agents.split(",")] if args.agents else None
    formats = (
        [InjectionFormat(f.strip()) for f in args.formats.split(",")]
        if args.formats
        else None
    )
    cases = tester.build_matrix(
        agent_types=agents,
        formats=formats,
        payloads_per_agent=args.payloads,
        field_limit=args.field_limit,
        seed=args.seed,
        instruction=args.instruction,
    )
    results = tester.run_all(cases, simulate_if_missing=True)
    summary = tester.summary()
    print(
        f"Ran {summary['total']} cases | "
        f"success={summary['successes']} fail={summary['failures']} | "
        f"rate={summary['rate']:.2%}"
    )

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / "results.json"
    cases_path = out_dir / "cases.json"
    report_path = out_dir / "report.json"
    tester.export_results(str(results_path))
    tester.export_cases(str(cases_path))

    analyzer = SuccessRateAnalyzer(results)
    report = analyzer.save_report(str(report_path))
    print(report.summary())
    print(f"Artifacts written under {out_dir}")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    analyzer = SuccessRateAnalyzer.from_json_file(args.results)
    report = analyzer.analyze()
    print(report.summary())
    if args.output:
        Path(args.output).write_text(report.to_json(), encoding="utf-8")
        print(f"Report saved -> {args.output}")
    return 0


def cmd_list_fields(args: argparse.Namespace) -> int:
    mapping = {
        "json": JSONInjector().list_candidate_fields(),
        "dom": DOMInjector().list_candidate_fields(),
        "html": HTMLInjector().list_candidate_fields(),
        "metadata": MetadataInjector().list_candidate_fields(),
    }
    if args.format:
        key = args.format.lower()
        if key not in mapping:
            print(f"Unknown format: {key}", file=sys.stderr)
            return 2
        print(json.dumps({key: mapping[key]}, indent=2))
    else:
        print(json.dumps(mapping, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="adi-toolkit",
        description="ADI (Agent Data Injection) Red Team Testing Toolkit",
    )
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="Generate ADI payloads")
    g.add_argument("--agent", default="general", help="web|coding|general|rag|tool_use")
    g.add_argument("--strategy", default="probabilistic",
                   help="probabilistic|bracket_wrap|escape_heavy|none")
    g.add_argument("--prob", type=float, default=0.35, help="Delimiter insertion probability")
    g.add_argument("--seed", type=int, default=None)
    g.add_argument("--instruction", default=None, help="Custom instruction text")
    g.add_argument("--template", default=None, help="Template name from library")
    g.add_argument("--batch", type=int, default=1)
    g.add_argument("--output", "-o", default=None)
    g.set_defaults(func=cmd_generate)

    inj = sub.add_parser("inject", help="Generate + inject into a format")
    inj.add_argument("--format", "-f", required=True, help="json|dom|html|metadata")
    inj.add_argument("--field", default="", help="Target field/slot/surface")
    inj.add_argument("--agent", default="general")
    inj.add_argument("--strategy", default="probabilistic")
    inj.add_argument("--prob", type=float, default=0.35)
    inj.add_argument("--seed", type=int, default=7)
    inj.add_argument("--instruction", default=None)
    inj.add_argument("--template", default=None)
    inj.add_argument("--meta-style", default="json",
                     help="For metadata: json|yaml|headers|sidecar|kv")
    inj.add_argument("--output", "-o", default=None)
    inj.add_argument("--dump-meta", action="store_true")
    inj.set_defaults(func=cmd_inject)

    t = sub.add_parser("test", help="Run offline ADI test matrix + analysis")
    t.add_argument("--agents", default="general,web,coding",
                   help="Comma-separated agent types")
    t.add_argument("--formats", default="json,dom,html,metadata")
    t.add_argument("--payloads", type=int, default=2, help="Payloads per agent")
    t.add_argument("--field-limit", type=int, default=3)
    t.add_argument("--seed", type=int, default=42)
    t.add_argument("--instruction", default=None)
    t.add_argument("--output-dir", default="output/adi_run")
    t.set_defaults(func=cmd_test)

    a = sub.add_parser("analyze", help="Analyze an existing results.json")
    a.add_argument("results", help="Path to results.json")
    a.add_argument("--output", "-o", default=None)
    a.set_defaults(func=cmd_analyze)

    lf = sub.add_parser("list-fields", help="List injectable fields per format")
    lf.add_argument("--format", default=None)
    lf.set_defaults(func=cmd_list_fields)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())