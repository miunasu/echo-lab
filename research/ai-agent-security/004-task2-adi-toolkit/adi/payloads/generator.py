"""ADI Payload Generator with probabilistic delimiter injection."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from adi.models import (
    AgentType,
    DelimiterStrategy,
    PayloadConfig,
    PayloadResult,
    new_id,
)
from adi.payloads.delimiters import DelimiterEngine
from adi.payloads.templates import TemplateLibrary


class PayloadGenerator:
    """Generate ADI payloads for web / coding / general agents.

    Core technique: probabilistic insertion of structural delimiters
    ({ } [ ] < > \\ ` etc.) so that agent parsers or prompt assemblers
    may re-interpret user-controlled data as system-level structure.
    """

    def __init__(
        self,
        default_config: Optional[PayloadConfig] = None,
        templates: Optional[TemplateLibrary] = None,
    ) -> None:
        self.default_config = default_config or PayloadConfig()
        self.templates = templates or TemplateLibrary()

    def generate(
        self,
        config: Optional[PayloadConfig] = None,
        template_name: Optional[str] = None,
        instruction: Optional[str] = None,
        use_trusted_wrapper: bool = True,
        tags: Optional[Sequence[str]] = None,
    ) -> PayloadResult:
        """Generate a single mutated payload."""
        cfg = config or self.default_config
        raw = instruction or cfg.instruction
        if not instruction and (template_name or not raw or raw == PayloadConfig().instruction):
            raw = self.templates.compose(
                agent_type=cfg.agent_type,
                template_name=template_name,
                custom_instruction=instruction,
                use_trusted_wrapper=use_trusted_wrapper,
            )
        elif use_trusted_wrapper and instruction:
            raw = self.templates.wrap_as_trusted(instruction)

        engine = DelimiterEngine(
            strategy=cfg.delimiter_strategy,
            probability=cfg.delimiter_prob,
            seed=cfg.seed,
        )
        mutated, used = engine.mutate(raw)

        result_tags = list(tags or [])
        result_tags.extend(
            [
                f"agent:{cfg.agent_type.value}",
                f"strategy:{cfg.delimiter_strategy.value}",
                f"disguise:{cfg.disguise_as}",
            ]
        )

        return PayloadResult(
            payload_id=new_id("payload"),
            raw_instruction=raw,
            mutated_text=mutated,
            agent_type=cfg.agent_type,
            delimiter_strategy=cfg.delimiter_strategy,
            delimiters_used=used,
            tags=result_tags,
        )

    def generate_batch(
        self,
        count: int = 5,
        agent_types: Optional[Sequence[AgentType]] = None,
        strategies: Optional[Sequence[DelimiterStrategy]] = None,
        base_instruction: Optional[str] = None,
        delimiter_prob: float = 0.35,
        seed: Optional[int] = None,
    ) -> List[PayloadResult]:
        """Generate a diverse batch of payloads across agents/strategies."""
        agents = list(agent_types or list(AgentType))
        strats = list(
            strategies
            or [
                DelimiterStrategy.PROBABILISTIC,
                DelimiterStrategy.BRACKET_WRAP,
                DelimiterStrategy.ESCAPE_HEAVY,
            ]
        )
        results: List[PayloadResult] = []
        for i in range(count):
            agent = agents[i % len(agents)]
            strategy = strats[i % len(strats)]
            cfg = PayloadConfig(
                agent_type=agent,
                instruction=base_instruction or PayloadConfig().instruction,
                delimiter_strategy=strategy,
                delimiter_prob=delimiter_prob,
                seed=(None if seed is None else seed + i),
            )
            # Rotate templates for variety
            names = self.templates.list_names()
            tname = names[i % len(names)] if not base_instruction else None
            results.append(
                self.generate(
                    config=cfg,
                    template_name=tname,
                    instruction=base_instruction,
                    use_trusted_wrapper=True,
                    tags=[f"batch_index:{i}"],
                )
            )
        return results

    def generate_for_agent(
        self,
        agent_type: AgentType,
        count: int = 3,
        delimiter_prob: float = 0.35,
        seed: Optional[int] = None,
    ) -> List[PayloadResult]:
        """Generate payloads optimized for a single agent type."""
        instructions = self.templates.for_agent(agent_type)
        results: List[PayloadResult] = []
        strategies = [
            DelimiterStrategy.PROBABILISTIC,
            DelimiterStrategy.BRACKET_WRAP,
            DelimiterStrategy.ESCAPE_HEAVY,
        ]
        for i in range(count):
            instr = instructions[i % len(instructions)]
            cfg = PayloadConfig(
                agent_type=agent_type,
                instruction=instr,
                delimiter_strategy=strategies[i % len(strategies)],
                delimiter_prob=delimiter_prob,
                seed=(None if seed is None else seed + i),
            )
            results.append(
                self.generate(
                    config=cfg,
                    instruction=instr,
                    use_trusted_wrapper=True,
                )
            )
        return results

    def preview_delimiters(self, n: int = 10, seed: int = 0) -> List[str]:
        """Inspect the delimiter pool (debugging / docs)."""
        engine = DelimiterEngine(seed=seed)
        return engine.sample_delimiters(n)

    def describe(self) -> Dict[str, Any]:
        return {
            "default_agent": self.default_config.agent_type.value,
            "default_strategy": self.default_config.delimiter_strategy.value,
            "default_prob": self.default_config.delimiter_prob,
            "templates": self.templates.list_names(),
            "sample_delimiters": self.preview_delimiters(),
        }