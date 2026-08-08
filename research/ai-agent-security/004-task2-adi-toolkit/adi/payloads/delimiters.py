"""Probabilistic delimiter injection engine.

Inserts structural characters that agents / parsers may treat as
section boundaries, code fences, or JSON/XML tokens, increasing the
chance that injected text is interpreted as trusted structure rather
than plain user content.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from adi.models import DelimiterStrategy


# Characters commonly used as structural delimiters in agent contexts.
DEFAULT_DELIMITERS: Dict[str, Sequence[str]] = {
    "brace": ("{", "}"),
    "bracket": ("[", "]"),
    "angle": ("<", ">"),
    "paren": ("(", ")"),
    "quote": ('"', "'", "`"),
    "escape": ("\\",),
    "fence": ("```", "~~~", "---", "==="),
    "xmlish": ("</", "/>", "?>", "<!"),
    "special": ("|", "#", "@", "$", "%", "&", ";"),
    "newline_markers": ("\\n", "\\r\\n", "\n---\n", "\n###\n"),
}


@dataclass
class DelimiterEngine:
    """Apply probabilistic or structured delimiter mutations to text."""

    strategy: DelimiterStrategy = DelimiterStrategy.PROBABILISTIC
    probability: float = 0.35
    seed: Optional[int] = None
    custom_delimiters: Dict[str, Sequence[str]] = field(default_factory=dict)
    max_insertions: int = 12

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)
        self._pool: List[str] = []
        source = {**DEFAULT_DELIMITERS, **self.custom_delimiters}
        for group in source.values():
            self._pool.extend(group)
        if not self._pool:
            self._pool = list("{[<>]}\\`\"'")

    def mutate(self, text: str) -> Tuple[str, List[str]]:
        """Mutate *text* according to the configured strategy.

        Returns (mutated_text, list_of_delimiters_used).
        """
        if not text:
            return text, []

        if self.strategy == DelimiterStrategy.NONE:
            return text, []
        if self.strategy == DelimiterStrategy.BRACKET_WRAP:
            return self._bracket_wrap(text)
        if self.strategy == DelimiterStrategy.ESCAPE_HEAVY:
            return self._escape_heavy(text)
        return self._probabilistic(text)

    # ------------------------------------------------------------------
    # Strategies
    # ------------------------------------------------------------------

    def _probabilistic(self, text: str) -> Tuple[str, List[str]]:
        """Insert delimiters before/after tokens with given probability."""
        tokens = self._tokenize(text)
        used: List[str] = []
        out: List[str] = []
        insertions = 0

        for tok in tokens:
            if (
                insertions < self.max_insertions
                and self._rng.random() < self.probability
                and tok.strip()
            ):
                d = self._rng.choice(self._pool)
                # Prefer wrapping short tokens; prefix longer ones.
                if len(tok) <= 8 and self._rng.random() < 0.5:
                    pair = self._closing_pair(d)
                    if pair:
                        out.append(d + tok + pair)
                        used.extend([d, pair])
                    else:
                        out.append(d + tok)
                        used.append(d)
                else:
                    position = self._rng.choice(["prefix", "suffix", "both"])
                    if position == "prefix":
                        out.append(d + tok)
                    elif position == "suffix":
                        out.append(tok + d)
                    else:
                        d2 = self._rng.choice(self._pool)
                        out.append(d + tok + d2)
                        used.append(d2)
                    used.append(d)
                insertions += 1
            else:
                out.append(tok)

        # Optional leading/trailing structural noise
        if self._rng.random() < self.probability:
            lead = self._rng.choice(self._pool)
            out.insert(0, lead)
            used.append(lead)
        if self._rng.random() < self.probability:
            trail = self._rng.choice(self._pool)
            out.append(trail)
            used.append(trail)

        return "".join(out), used

    def _bracket_wrap(self, text: str) -> Tuple[str, List[str]]:
        """Wrap the whole instruction in layered bracket/brace pairs."""
        layers = [
            ("{", "}"),
            ("[", "]"),
            ("<", ">"),
            ("```", "```"),
            ("<!--", "-->"),
        ]
        n = self._rng.randint(1, min(3, len(layers)))
        chosen = self._rng.sample(layers, n)
        result = text
        used: List[str] = []
        for open_d, close_d in chosen:
            result = f"{open_d}{result}{close_d}"
            used.extend([open_d, close_d])
        return result, used

    def _escape_heavy(self, text: str) -> Tuple[str, List[str]]:
        """Inject backslashes and escaped quotes aggressively."""
        used: List[str] = ["\\"]
        chars = list(text)
        out: List[str] = []
        for ch in chars:
            if ch in ('"', "'", "`", "{", "}", "[", "]", "\\") and self._rng.random() < 0.6:
                out.append("\\" + ch)
                used.append("\\" + ch)
            elif self._rng.random() < self.probability * 0.3:
                out.append("\\" + ch)
                used.append("\\")
            else:
                out.append(ch)
        # Surround with escaped fence
        wrapped = '\\n```\\n' + "".join(out) + '\\n```\\n'
        used.extend(["\\n", "```"])
        return wrapped, used

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Split text into words while preserving whitespace tokens."""
        parts: List[str] = []
        buf: List[str] = []
        in_space = text[:1].isspace() if text else False
        for ch in text:
            sp = ch.isspace()
            if sp == in_space:
                buf.append(ch)
            else:
                if buf:
                    parts.append("".join(buf))
                buf = [ch]
                in_space = sp
        if buf:
            parts.append("".join(buf))
        return parts

    @staticmethod
    def _closing_pair(opener: str) -> Optional[str]:
        pairs = {
            "{": "}",
            "[": "]",
            "<": ">",
            "(": ")",
            '"': '"',
            "'": "'",
            "`": "`",
            "```": "```",
            "~~~": "~~~",
            "<!--": "-->",
            "</": ">",
        }
        return pairs.get(opener)

    def sample_delimiters(self, n: int = 5) -> List[str]:
        """Return *n* random delimiters from the pool (for inspection)."""
        return self._rng.sample(self._pool, min(n, len(self._pool)))