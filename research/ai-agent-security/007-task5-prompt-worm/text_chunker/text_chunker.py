#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
text_chunker.py - Long-document text chunking utility.

Supports:
  - Strategies: fixed, paragraph, sentence, sliding
  - Size units: characters or tokens (tiktoken)
  - Overlap between consecutive chunks
  - Multilingual (Chinese / English) sentence & paragraph splitting
  - CLI and importable API
  - JSON output for RAG / vector DB / distributed processing
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    chunk_id: int
    content: str
    start_pos: int
    end_pos: int
    overlap_with_next: int

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Tokenizer helpers (optional tiktoken)
# ---------------------------------------------------------------------------

_tiktoken_encoding = None
_tiktoken_available: Optional[bool] = None


def _get_encoding(encoding_name: str = "cl100k_base"):
    global _tiktoken_encoding, _tiktoken_available
    if _tiktoken_available is False:
        return None
    if _tiktoken_encoding is not None:
        return _tiktoken_encoding
    try:
        import tiktoken  # type: ignore

        _tiktoken_encoding = tiktoken.get_encoding(encoding_name)
        _tiktoken_available = True
        return _tiktoken_encoding
    except Exception:
        _tiktoken_available = False
        return None


def count_units(text: str, unit: str = "char", encoding_name: str = "cl100k_base") -> int:
    """Return length of text in characters or tokens."""
    if unit == "token":
        enc = _get_encoding(encoding_name)
        if enc is None:
            raise RuntimeError(
                "Token-based chunking requires tiktoken. "
                "Install with: pip install tiktoken"
            )
        return len(enc.encode(text))
    return len(text)


def take_units(
    text: str,
    max_units: int,
    unit: str = "char",
    encoding_name: str = "cl100k_base",
) -> Tuple[str, int]:
    """
    Take a prefix of `text` with at most `max_units` characters/tokens.
    Returns (prefix, consumed_char_length).
    """
    if max_units <= 0 or not text:
        return "", 0

    if unit == "char":
        prefix = text[:max_units]
        return prefix, len(prefix)

    enc = _get_encoding(encoding_name)
    if enc is None:
        raise RuntimeError(
            "Token-based chunking requires tiktoken. "
            "Install with: pip install tiktoken"
        )
    tokens = enc.encode(text)
    if len(tokens) <= max_units:
        return text, len(text)
    prefix_tokens = tokens[:max_units]
    prefix = enc.decode(prefix_tokens)
    # Guard against decode producing more/less chars than expected edge cases
    return prefix, len(prefix)


def slice_by_units(
    text: str,
    start_units: int,
    end_units: int,
    unit: str = "char",
    encoding_name: str = "cl100k_base",
) -> Tuple[str, int, int]:
    """
    Slice text by unit range [start_units, end_units).
    Returns (slice_text, start_char, end_char) relative to `text`.
    """
    if unit == "char":
        start_char = max(0, start_units)
        end_char = min(len(text), end_units)
        return text[start_char:end_char], start_char, end_char

    enc = _get_encoding(encoding_name)
    if enc is None:
        raise RuntimeError(
            "Token-based chunking requires tiktoken. "
            "Install with: pip install tiktoken"
        )
    tokens = enc.encode(text)
    start_u = max(0, start_units)
    end_u = min(len(tokens), end_units)
    if start_u >= end_u:
        return "", 0, 0
    # Approximate char offsets via progressive decode for accurate positions
    prefix = enc.decode(tokens[:start_u]) if start_u > 0 else ""
    full = enc.decode(tokens[:end_u])
    start_char = len(prefix)
    end_char = len(full)
    return text[start_char:end_char], start_char, end_char


# ---------------------------------------------------------------------------
# Boundary detection (CN + EN)
# ---------------------------------------------------------------------------

# Sentence end markers: Latin + CJK
_SENTENCE_END = re.compile(
    r"(?<=[.!?。！？…])"  # after end punctuation
    r"(?:[\"'”’）\)】》»])?"  # optional closing quotes/brackets
    r"(?=\s+|(?=[A-Z\u4e00-\u9fff])|$)"  # space, capital/CJK, or EOS
)

# Paragraph split: 2+ newlines (optionally with blank lines containing spaces)
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n+")


def split_paragraphs(text: str) -> List[Tuple[int, int, str]]:
    """
    Split text into paragraphs. Returns list of (start, end, content)
    where start/end are character offsets in the original text.
    Consecutive paragraphs preserve original offsets (including blank lines).
    """
    if not text:
        return []

    parts: List[Tuple[int, int, str]] = []
    last = 0
    for m in _PARAGRAPH_SPLIT.finditer(text):
        # paragraph is text[last:m.start()]
        para_end = m.start()
        if para_end > last:
            content = text[last:para_end]
            # keep trailing single newlines out of content? keep raw
            parts.append((last, para_end, content))
        last = m.end()  # skip the blank-line separator itself

    if last < len(text):
        parts.append((last, len(text), text[last:]))

    # If no paragraph breaks found, whole text is one paragraph
    if not parts:
        parts.append((0, len(text), text))

    # Drop purely whitespace paragraphs but keep offsets consistent by skipping
    result = [(s, e, c) for s, e, c in parts if c.strip()]
    return result if result else [(0, len(text), text)]


def split_sentences(text: str, base_offset: int = 0) -> List[Tuple[int, int, str]]:
    """
    Split text into sentences with absolute char offsets = base_offset + local.
    Handles Chinese and English end punctuation.
    """
    if not text:
        return []

    # Find split points after sentence-ending punctuation
    indices = [0]
    for m in _SENTENCE_END.finditer(text):
        idx = m.end()
        if idx not in indices and 0 < idx < len(text):
            indices.append(idx)
    if indices[-1] != len(text):
        indices.append(len(text))

    sentences: List[Tuple[int, int, str]] = []
    for i in range(len(indices) - 1):
        s, e = indices[i], indices[i + 1]
        content = text[s:e]
        if content.strip():
            # strip leading whitespace from sentence but keep absolute start
            # of non-ws content for cleaner chunks
            lstrip_len = len(content) - len(content.lstrip())
            actual_s = s + lstrip_len
            actual_content = content[lstrip_len:]
            # keep trailing content as-is (incl. trailing spaces before next)
            rstrip_content = actual_content.rstrip()
            if not rstrip_content:
                continue
            actual_e = actual_s + len(rstrip_content)
            sentences.append((base_offset + actual_s, base_offset + actual_e, rstrip_content))

    if not sentences:
        stripped = text.strip()
        if stripped:
            s = text.find(stripped)
            sentences.append((base_offset + s, base_offset + s + len(stripped), stripped))
    return sentences


def find_best_break(
    text: str,
    preferred_end: int,
    search_back: int = 100,
) -> int:
    """
    Find a natural break point at or before preferred_end, looking back
    up to search_back characters. Prefers: paragraph > sentence > whitespace.
    Returns character index into `text`.
    """
    if preferred_end >= len(text):
        return len(text)
    if preferred_end <= 0:
        return 0

    window_start = max(0, preferred_end - search_back)
    window = text[window_start:preferred_end]

    # 1) paragraph break (last double-newline in window)
    para_matches = list(_PARAGRAPH_SPLIT.finditer(window))
    if para_matches:
        # break at start of separator so previous para is complete
        return window_start + para_matches[-1].start()

    # 2) sentence end in window
    sent_matches = list(_SENTENCE_END.finditer(window))
    if sent_matches:
        return window_start + sent_matches[-1].end()

    # 3) last whitespace
    for i in range(len(window) - 1, -1, -1):
        if window[i].isspace():
            return window_start + i + 1  # after the space

    return preferred_end


# ---------------------------------------------------------------------------
# Core chunking strategies
# ---------------------------------------------------------------------------

def _build_chunks_from_ranges(
    text: str,
    ranges: Sequence[Tuple[int, int]],
    overlap: int,
    unit: str,
    encoding_name: str,
) -> List[Chunk]:
    """
    Convert char-offset ranges into Chunk objects with overlap metadata.
    `overlap` is measured in the same unit as chunking (char/token).
    """
    if not ranges:
        return []

    chunks: List[Chunk] = []
    n = len(ranges)
    for i, (start, end) in enumerate(ranges):
        content = text[start:end]
        # Compute overlap_with_next in requested units
        if i < n - 1:
            next_start = ranges[i + 1][0]
            # overlapping region is [next_start, end) if next_start < end
            if next_start < end:
                overlap_text = text[next_start:end]
                ov = count_units(overlap_text, unit=unit, encoding_name=encoding_name)
            else:
                ov = 0
        else:
            ov = 0
        chunks.append(
            Chunk(
                chunk_id=i + 1,
                content=content,
                start_pos=start,
                end_pos=end,
                overlap_with_next=ov,
            )
        )
    return chunks


def _apply_overlap_to_ranges(
    ranges: List[Tuple[int, int]],
    text: str,
    overlap: int,
    unit: str,
    encoding_name: str,
) -> List[Tuple[int, int]]:
    """
    Expand each range (except the first) backward so it overlaps the previous
    chunk by approximately `overlap` units. Used for non-sliding strategies
    that first produce non-overlapping segments.
    """
    if overlap <= 0 or len(ranges) <= 1:
        return ranges

    result: List[Tuple[int, int]] = [ranges[0]]
    for i in range(1, len(ranges)):
        start, end = ranges[i]
        prev_start, prev_end = result[i - 1]  # use already-adjusted prev
        # Walk backward from start to include ~overlap units from previous content
        # We want new_start such that text[new_start:start] ~= overlap units,
        # but not before prev_start.
        target_start = start
        if unit == "char":
            target_start = max(prev_start, start - overlap)
        else:
            # Take last `overlap` tokens of text[:start], map to char offset
            prefix = text[:start]
            enc = _get_encoding(encoding_name)
            if enc is None:
                target_start = max(prev_start, start - overlap)  # fallback
            else:
                tokens = enc.encode(prefix)
                if len(tokens) > overlap:
                    keep = enc.decode(tokens[-overlap:])
                    target_start = start - len(keep)
                    target_start = max(prev_start, target_start)
                else:
                    target_start = prev_start
        # Ensure we don't go past previous start and keep end
        target_start = max(0, min(target_start, start))
        result.append((target_start, end))
    return result


def _overlap_start_char(
    text: str,
    end_char: int,
    overlap: int,
    unit: str,
    encoding_name: str,
) -> int:
    """Return a char offset such that text[offset:end_char] ~= overlap units."""
    if overlap <= 0 or end_char <= 0:
        return end_char
    if unit == "char":
        return max(0, end_char - overlap)
    prefix = text[:end_char]
    enc = _get_encoding(encoding_name)
    if enc is None:
        return max(0, end_char - overlap)
    tokens = enc.encode(prefix)
    if len(tokens) <= overlap:
        return 0
    keep = enc.decode(tokens[-overlap:])
    return max(0, end_char - len(keep))


def chunk_fixed(
    text: str,
    chunk_size: int,
    overlap: int = 0,
    unit: str = "char",
    encoding_name: str = "cl100k_base",
    soft_boundary: bool = True,
) -> List[Chunk]:
    """
    Fixed-size chunking. Optionally soft-break near natural boundaries.
    Next chunk starts `overlap` units before the previous chunk end, so soft
    boundary shortening never creates coverage gaps.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    if not text:
        return []

    text_len = len(text)
    ranges: List[Tuple[int, int]] = []
    start_char = 0

    while start_char < text_len:
        # Take up to chunk_size units from the current start
        _, consumed = take_units(
            text[start_char:], chunk_size, unit=unit, encoding_name=encoding_name
        )
        end_char = start_char + consumed
        if end_char <= start_char:
            end_char = min(start_char + 1, text_len)

        # Soft boundary: prefer natural break at or before planned end
        if soft_boundary and end_char < text_len:
            search_back = min(200, max(20, (end_char - start_char) // 4))
            break_char = find_best_break(text, end_char, search_back=search_back)
            if break_char > start_char:
                end_char = break_char

        if end_char <= start_char:
            end_char = min(start_char + 1, text_len)

        ranges.append((start_char, end_char))

        if end_char >= text_len:
            break

        # Next window starts overlap units before current end
        next_start = _overlap_start_char(
            text, end_char, overlap, unit, encoding_name
        )
        # Always make forward progress
        if next_start <= start_char:
            next_start = start_char + 1
        # If overlap would restart at the same logical window, advance minimally
        if next_start >= end_char:
            next_start = end_char

        start_char = next_start

        # Prevent infinite loops on degenerate inputs
        if len(ranges) > 1 and ranges[-1] == ranges[-2]:
            break
        if len(ranges) > text_len + 5:
            break

    # Deduplicate identical consecutive ranges
    cleaned: List[Tuple[int, int]] = []
    for r in ranges:
        if r[1] <= r[0]:
            continue
        if cleaned and r[0] == cleaned[-1][0] and r[1] == cleaned[-1][1]:
            continue
        cleaned.append(r)

    return _build_chunks_from_ranges(text, cleaned, overlap, unit, encoding_name)


def chunk_sliding(
    text: str,
    chunk_size: int,
    overlap: int = 0,
    unit: str = "char",
    encoding_name: str = "cl100k_base",
) -> List[Chunk]:
    """
    Pure sliding-window chunking (hard cuts, no soft boundary adjustment).
    Window size = chunk_size, stride = chunk_size - overlap.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    if not text:
        return []

    total = count_units(text, unit=unit, encoding_name=encoding_name)
    if total == 0:
        return []

    step = max(chunk_size - overlap, 1)
    ranges: List[Tuple[int, int]] = []
    pos = 0

    while pos < total:
        end = min(pos + chunk_size, total)
        _, start_char, end_char = slice_by_units(
            text, pos, end, unit=unit, encoding_name=encoding_name
        )
        if end_char > start_char:
            ranges.append((start_char, end_char))
        if end >= total:
            break
        pos += step

    return _build_chunks_from_ranges(text, ranges, overlap, unit, encoding_name)


def _pack_segments(
    segments: Sequence[Tuple[int, int, str]],
    text: str,
    chunk_size: int,
    overlap: int,
    unit: str,
    encoding_name: str,
) -> List[Chunk]:
    """
    Greedily pack ordered segments (paragraphs or sentences) into chunks
    that do not exceed chunk_size units. Then apply overlap.
    """
    if not segments:
        return []

    # First pass: non-overlapping packed ranges
    raw_ranges: List[Tuple[int, int]] = []
    cur_start: Optional[int] = None
    cur_end: Optional[int] = None
    cur_units = 0

    for seg_start, seg_end, seg_content in segments:
        seg_units = count_units(seg_content, unit=unit, encoding_name=encoding_name)

        # Oversized single segment: split with fixed strategy
        if seg_units > chunk_size:
            # flush current
            if cur_start is not None and cur_end is not None:
                raw_ranges.append((cur_start, cur_end))
                cur_start, cur_end, cur_units = None, None, 0
            sub = chunk_fixed(
                seg_content,
                chunk_size=chunk_size,
                overlap=0,
                unit=unit,
                encoding_name=encoding_name,
                soft_boundary=True,
            )
            for ch in sub:
                raw_ranges.append((seg_start + ch.start_pos, seg_start + ch.end_pos))
            continue

        if cur_start is None:
            cur_start = seg_start
            cur_end = seg_end
            cur_units = seg_units
            continue

        # Measure join cost: include gap between cur_end and seg_start
        gap = text[cur_end:seg_start] if cur_end is not None else ""
        gap_units = count_units(gap, unit=unit, encoding_name=encoding_name)
        joined = cur_units + gap_units + seg_units

        if joined <= chunk_size:
            cur_end = seg_end
            cur_units = joined
        else:
            raw_ranges.append((cur_start, cur_end if cur_end is not None else seg_end))
            cur_start = seg_start
            cur_end = seg_end
            cur_units = seg_units

    if cur_start is not None and cur_end is not None:
        raw_ranges.append((cur_start, cur_end))

    # Apply overlap by extending starts backward
    overlapped = _apply_overlap_to_ranges(
        raw_ranges, text, overlap, unit, encoding_name
    )
    return _build_chunks_from_ranges(text, overlapped, overlap, unit, encoding_name)


def chunk_paragraph(
    text: str,
    chunk_size: int,
    overlap: int = 0,
    unit: str = "char",
    encoding_name: str = "cl100k_base",
) -> List[Chunk]:
    """Pack whole paragraphs into chunks up to chunk_size."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")
    if not text:
        return []
    paragraphs = split_paragraphs(text)
    return _pack_segments(paragraphs, text, chunk_size, overlap, unit, encoding_name)


def chunk_sentence(
    text: str,
    chunk_size: int,
    overlap: int = 0,
    unit: str = "char",
    encoding_name: str = "cl100k_base",
) -> List[Chunk]:
    """Pack whole sentences into chunks up to chunk_size."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")
    if not text:
        return []
    sentences = split_sentences(text, base_offset=0)
    return _pack_segments(sentences, text, chunk_size, overlap, unit, encoding_name)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

STRATEGIES = ("fixed", "paragraph", "sentence", "sliding")


def chunk_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50,
    strategy: str = "fixed",
    unit: str = "char",
    encoding_name: str = "cl100k_base",
) -> List[Chunk]:
    """
    Split `text` into chunks.

    Args:
        text: source document
        chunk_size: max size per chunk (chars or tokens)
        overlap: overlap size with next chunk (same unit)
        strategy: fixed | paragraph | sentence | sliding
        unit: char | token
        encoding_name: tiktoken encoding name when unit=token

    Returns:
        list of Chunk
    """
    strategy = strategy.lower().strip()
    unit = unit.lower().strip()
    if strategy not in STRATEGIES:
        raise ValueError(f"Unknown strategy '{strategy}'. Choose from: {STRATEGIES}")
    if unit not in ("char", "token"):
        raise ValueError("unit must be 'char' or 'token'")

    if strategy == "fixed":
        return chunk_fixed(text, chunk_size, overlap, unit, encoding_name, soft_boundary=True)
    if strategy == "sliding":
        return chunk_sliding(text, chunk_size, overlap, unit, encoding_name)
    if strategy == "paragraph":
        return chunk_paragraph(text, chunk_size, overlap, unit, encoding_name)
    if strategy == "sentence":
        return chunk_sentence(text, chunk_size, overlap, unit, encoding_name)
    raise ValueError(f"Unknown strategy: {strategy}")


def chunks_to_json(chunks: List[Chunk], pretty: bool = True) -> str:
    data = [c.to_dict() for c in chunks]
    if pretty:
        return json.dumps(data, ensure_ascii=False, indent=2)
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def chunk_file(
    input_path: str | Path,
    chunk_size: int = 500,
    overlap: int = 50,
    strategy: str = "fixed",
    unit: str = "char",
    encoding_name: str = "cl100k_base",
    output_path: str | Path | None = None,
    encoding: str = "utf-8",
) -> List[Chunk]:
    path = Path(input_path)
    text = path.read_text(encoding=encoding)
    chunks = chunk_text(
        text,
        chunk_size=chunk_size,
        overlap=overlap,
        strategy=strategy,
        unit=unit,
        encoding_name=encoding_name,
    )
    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(chunks_to_json(chunks), encoding="utf-8")
    return chunks


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="text_chunker",
        description="Split long documents into overlapping chunks for RAG / distributed NLP.",
    )
    p.add_argument("--input", "-i", required=True, help="Input text file path")
    p.add_argument("--output", "-o", default=None, help="Output JSON file path (default: stdout)")
    p.add_argument("--chunk-size", "-s", type=int, default=500, help="Max chunk size (default: 500)")
    p.add_argument("--overlap", "-k", type=int, default=50, help="Overlap size (default: 50)")
    p.add_argument(
        "--strategy",
        "-t",
        choices=STRATEGIES,
        default="fixed",
        help="Chunking strategy (default: fixed)",
    )
    p.add_argument(
        "--unit",
        "-u",
        choices=("char", "token"),
        default="char",
        help="Size unit: char or token (default: char)",
    )
    p.add_argument(
        "--encoding-name",
        default="cl100k_base",
        help="tiktoken encoding name when --unit=token (default: cl100k_base)",
    )
    p.add_argument(
        "--file-encoding",
        default="utf-8",
        help="Input file encoding (default: utf-8)",
    )
    p.add_argument(
        "--compact",
        action="store_true",
        help="Emit compact JSON (no indent)",
    )
    p.add_argument(
        "--stats",
        action="store_true",
        help="Print chunk statistics to stderr",
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        path = Path(args.input)
        if not path.exists():
            print(f"Error: input file not found: {path}", file=sys.stderr)
            return 1

        text = path.read_text(encoding=args.file_encoding)
        chunks = chunk_text(
            text,
            chunk_size=args.chunk_size,
            overlap=args.overlap,
            strategy=args.strategy,
            unit=args.unit,
            encoding_name=args.encoding_name,
        )
        payload = chunks_to_json(chunks, pretty=not args.compact)

        if args.output:
            out = Path(args.output)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(payload, encoding="utf-8")
            print(f"Wrote {len(chunks)} chunks -> {out}", file=sys.stderr)
        else:
            sys.stdout.write(payload)
            if not payload.endswith("\n"):
                sys.stdout.write("\n")

        if args.stats:
            sizes = [
                count_units(c.content, unit=args.unit, encoding_name=args.encoding_name)
                for c in chunks
            ]
            if sizes:
                print(
                    f"stats: n={len(sizes)} "
                    f"min={min(sizes)} max={max(sizes)} "
                    f"avg={sum(sizes)/len(sizes):.1f} "
                    f"unit={args.unit} strategy={args.strategy}",
                    file=sys.stderr,
                )
            else:
                print("stats: n=0 (empty input)", file=sys.stderr)

        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())