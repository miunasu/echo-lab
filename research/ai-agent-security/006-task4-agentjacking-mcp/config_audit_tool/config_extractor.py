#!/usr/bin/env python3
"""
config_extractor.py - Code repository configuration audit tool.

Scans Python/JavaScript source files and common config files for sensitive
configuration items (API keys, DB connection strings, DSN, secrets, etc.),
then outputs a redacted JSON inventory for security audit use.

Usage:
    python config_extractor.py <directory> --output audit.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator, List, Optional, Sequence, Set, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCAN_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".json",
    ".env",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".properties",
}

SPECIAL_BASENAMES = {
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
    ".env.staging",
    ".env.test",
}

SKIP_DIR_NAMES = {
    ".git",
    ".svn",
    ".hg",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "coverage",
    ".idea",
    ".vscode",
    "vendor",
}

# Sensitive key name fragments (case-insensitive).
# Prefer compound forms; bare "secret"/"token"/"key" still match via fragments.
SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)"
    r"(?:"
    r"api[_-]?key|apikey|access[_-]?key|secret[_-]?key|private[_-]?key|"
    r"auth[_-]?token|access[_-]?token|refresh[_-]?token|bearer|"
    r"password|passwd|passphrase|"
    r"(?<![a-z])pwd(?![a-z])|"
    r"client[_-]?secret|app[_-]?secret|"
    r"secret|"
    r"credential|"
    r"sentry[_-]?dsn|(?<![a-z])dsn(?![a-z])|"
    r"connection[_-]?string|database[_-]?url|db[_-]?url|"
    r"mongo(?:db)?[_-]?uri|redis[_-]?url|amqp[_-]?url|"
    r"aws[_-]?(?:access|secret)|"
    r"stripe[_-]?(?:key|secret)|"
    r"jwt[_-]?secret|encryption[_-]?key|signing[_-]?key|"
    r"webhook[_-]?secret|bot[_-]?token|slack[_-]?token|"
    r"github[_-]?token|gitlab[_-]?token|npm[_-]?token|"
    r"openai[_-]?key|anthropic[_-]?key|huggingface[_-]?token|"
    r"account[_-]?key|storage[_-]?key|"
    r"databaseurl|mongouri"
    r")"
)

# Sources produced by bare value-pattern scanners (deprioritized in dedupe)
VALUE_PATTERN_SOURCES = {
    "python_value",
    "js_value",
    "dotenv_value",
    "generic_value",
    "json_value",
}

VALUE_SECRET_PATTERNS: Sequence[Tuple[str, re.Pattern[str]]] = (
    (
        "AWS_ACCESS_KEY_ID",
        re.compile(r"\b(AKIA[0-9A-Z]{16})\b"),
    ),
    (
        "GITHUB_TOKEN",
        re.compile(r"\b(gh[pousr]_[A-Za-z0-9_]{20,})\b"),
    ),
    (
        "SLACK_TOKEN",
        re.compile(r"\b(xox[baprs]-[A-Za-z0-9-]{10,})\b"),
    ),
    (
        "JWT",
        re.compile(
            r"\b(eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})\b"
        ),
    ),
    (
        "PRIVATE_KEY_BLOCK",
        re.compile(
            r"(-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----)"
        ),
    ),
    (
        "CONNECTION_URI",
        re.compile(
            r"\b((?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp|amqps)"
            r"://[^\s'\"`]+)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "SENTRY_DSN_VALUE",
        re.compile(
            r"\b(https?://[0-9a-f]{16,}@[a-z0-9.-]+(?:/[0-9]+)?)\b",
            re.IGNORECASE,
        ),
    ),
)

# Python patterns
PY_ENV_GET = re.compile(
    r"""(?P<func>os\.environ\.get|os\.getenv)\s*\(\s*['"](?P<key>[A-Za-z_][A-Za-z0-9_]*)['"]"""
    r"""(?:\s*,\s*(?:(['"])(?P<default_val>(?:(?!\3).)*)\3|(?P<default_expr>[^)]+)))?""",
    re.DOTALL,
)
PY_ENV_INDEX = re.compile(
    r"""os\.environ\s*\[\s*['"](?P<key>[A-Za-z_][A-Za-z0-9_]*)['"]\s*\]"""
)
PY_ASSIGN = re.compile(
    r"""(?P<key>(?:[A-Za-z_][A-Za-z0-9_]*\.)*[A-Za-z_][A-Za-z0-9_]*)\s*=\s*"""
    r"""(?P<q>['"])(?P<val>(?:(?!\2).|\\.)+)(?P=q)"""
)
PY_DICT = re.compile(
    r"""['"](?P<key>[A-Za-z_][A-Za-z0-9_\-]*)['"]\s*:\s*"""
    r"""(?P<q>['"])(?P<val>(?:(?!\2).|\\.)+)(?P=q)"""
)

# JS / TS patterns
JS_ENV_DOT = re.compile(r"""process\.env\.(?P<key>[A-Za-z_][A-Za-z0-9_]*)""")
JS_ENV_INDEX = re.compile(
    r"""process\.env\s*\[\s*['"](?P<key>[A-Za-z_][A-Za-z0-9_]*)['"]\s*\]"""
)
JS_ASSIGN = re.compile(
    r"""(?:(?:const|let|var)\s+)?(?P<key>(?:[A-Za-z_][A-Za-z0-9_]*\.)*[A-Za-z_][A-Za-z0-9_]*)\s*=\s*"""
    r"""(?P<q>['"`])(?P<val>(?:(?!\2).|\\.)+)(?P=q)"""
)
JS_OBJ = re.compile(
    r"""(?P<key>[A-Za-z_][A-Za-z0-9_\-]*)\s*:\s*"""
    r"""(?P<q>['"`])(?P<val>(?:(?!\2).|\\.)+)(?P=q)"""
)
JS_OBJ_QUOTED = re.compile(
    r"""['"](?P<key>[A-Za-z_][A-Za-z0-9_\-]*)['"]\s*:\s*"""
    r"""(?P<q>['"`])(?P<val>(?:(?!\2).|\\.)+)(?P=q)"""
)

ENV_LINE = re.compile(
    r"""^\s*(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<val>.*)$"""
)
INI_ASSIGN = re.compile(
    r"""^\s*(?P<key>[A-Za-z_][A-Za-z0-9_\-.]*)\s*[=:]\s*(?P<val>.+?)\s*$"""
)

# camelCase / PascalCase -> snake fragments for sensitivity check
CAMEL_SPLIT = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    file: str
    line: int
    key: str
    value_preview: str
    source: str = "unknown"

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "line": self.line,
            "key": self.key,
            "value_preview": self.value_preview,
        }


# ---------------------------------------------------------------------------
# Redaction / heuristics
# ---------------------------------------------------------------------------

def redact_value(value: str, keep: int = 4) -> str:
    """Mask middle of value; keep first/last `keep` characters when long enough.

    Example: https://abcd....@sentry.io/12345 -> https****...****2345 style
    with first 4 and last 4 visible: 'http****...****2345' for long strings.
    """
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"', "`"):
        text = text[1:-1]

    length = len(text)
    if length == 0:
        return ""
    if length <= keep * 2:
        if length <= 2:
            return "*" * length
        return text[0] + ("*" * (length - 2)) + text[-1]
    return f"{text[:keep]}****...****{text[-keep:]}"


def clean_captured_value(raw: str) -> str:
    if raw is None:
        return ""
    text = raw.strip()
    if text and text[0] not in ("'", '"'):
        if " #" in text:
            text = text.split(" #", 1)[0].rstrip()
        elif "\t#" in text:
            text = text.split("\t#", 1)[0].rstrip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"', "`"):
        text = text[1:-1]
    # Unescape common sequences from source literals
    text = (
        text.replace(r"\/", "/")
        .replace(r"\n", "\n")
        .replace(r"\t", "\t")
        .replace(r"\"", '"')
        .replace(r"\'", "'")
    )
    return text.strip()


def key_name_candidates(name: str) -> List[str]:
    """Return variants of a key name for sensitivity matching."""
    if not name:
        return []
    variants = [name, name.split(".")[-1]]
    # Split camelCase: databaseUrl -> database Url -> database_url
    simple = name.split(".")[-1]
    parts = CAMEL_SPLIT.findall(simple)
    if parts:
        variants.append("_".join(p.lower() for p in parts))
        variants.append("".join(p.lower() for p in parts))
    # Normalize hyphens
    variants.append(simple.replace("-", "_"))
    # unique preserve order
    seen: Set[str] = set()
    out: List[str] = []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def is_sensitive_key(name: str) -> bool:
    if not name:
        return False
    for cand in key_name_candidates(name):
        if SENSITIVE_KEY_PATTERN.search(cand):
            return True
    return False


def is_plain_public_url(value: str) -> bool:
    """True for http(s) URLs that do not embed credentials or DSN tokens."""
    v = value.strip()
    if not re.match(r"(?i)^https?://", v):
        return False
    # userinfo present -> sensitive
    if re.match(r"(?i)^https?://[^/\s]+@", v):
        return False
    # sentry-like hex key in userinfo already handled; bare path URLs are public
    return True


def looks_like_secret_value(value: str) -> bool:
    """Heuristic for high-entropy / credential-like literal values."""
    if not value:
        return False
    v = value.strip()
    if len(v) < 12:
        return False

    # Plain public URLs are not secrets
    if is_plain_public_url(v):
        return False

    lower = v.lower()

    # Connection strings / URIs with scheme
    if re.match(
        r"(?i)^(postgres(?:ql)?|mysql|mongodb(\+srv)?|redis|amqp|amqss?)://",
        v,
    ):
        return True

    # HTTP URL with embedded credentials
    if re.match(r"(?i)^https?://[^/\s]+:[^/\s]+@", v):
        return True
    if re.match(r"(?i)^https?://[0-9a-f]{16,}@", v):
        return True

    # Well-known secret prefixes
    if re.search(
        r"(?i)\b(sk-|sk_live_|sk_test_|pk_live_|pk_test_|rk_live_|rk_test_|"
        r"whsec_|xox[baprs]-|gh[pousr]_|GOCSPX-|AIza)",
        v,
    ):
        return True

    # JWT
    if re.match(
        r"^eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}$", v
    ):
        return True

    # AWS access key
    if re.match(r"^AKIA[0-9A-Z]{16}$", v):
        return True

    # Long token-like (no spaces), not a plain path
    if " " in v:
        # ADO.NET style connection string
        if re.search(r"(?i)(password|pwd)\s*=", v):
            return True
        return False

    if re.fullmatch(r"[A-Za-z0-9_\-/.+=:]{20,}", v):
        # Exclude simple hostnames / semver-ish / pure lowercase words
        if re.fullmatch(r"[a-z0-9.-]+", v) and v.count(".") <= 3 and len(v) < 40:
            return False
        return True

    return False


def report_key_for(name: str, value: str) -> str:
    simple = name.split(".")[-1] if name else name
    if is_sensitive_key(simple):
        return simple
    if is_sensitive_key(name):
        return name
    if looks_like_secret_value(value):
        return f"{simple} (secret-like value)"
    return simple


# ---------------------------------------------------------------------------
# Extractors
# ---------------------------------------------------------------------------

def _value_pattern_findings(
    line: str, line_no: int, rel_path: str, source: str
) -> List[Finding]:
    findings: List[Finding] = []
    stripped = line.lstrip()
    if stripped.startswith("#") and not name_allows_hash_value(stripped):
        return findings

    for key_name, pattern in VALUE_SECRET_PATTERNS:
        for m in pattern.finditer(line):
            val = m.group(1)
            findings.append(
                Finding(
                    rel_path,
                    line_no,
                    key_name,
                    redact_value(val),
                    source=source,
                )
            )
    return findings


def name_allows_hash_value(stripped: str) -> bool:
    return False


def _offset_to_line(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def extract_python(text: str, rel_path: str) -> List[Finding]:
    findings: List[Finding] = []
    lines = text.splitlines()

    # Multiline-aware env get/getenv
    for m in PY_ENV_GET.finditer(text):
        key = m.group("key")
        if not is_sensitive_key(key):
            continue
        default_val = m.group("default_val")
        line_no = _offset_to_line(text, m.start())
        if default_val:
            preview = redact_value(clean_captured_value(default_val))
        else:
            preview = "<from-environ>"
        findings.append(
            Finding(rel_path, line_no, key, preview, source="python_environ_get")
        )

    for line_no, line in enumerate(lines, start=1):
        for m in PY_ENV_INDEX.finditer(line):
            key = m.group("key")
            if is_sensitive_key(key):
                findings.append(
                    Finding(
                        rel_path,
                        line_no,
                        key,
                        "<from-environ>",
                        source="python_environ_index",
                    )
                )

        for m in PY_ASSIGN.finditer(line):
            key = m.group("key")
            # Skip if RHS is os.environ... (already covered)
            raw_rhs = line.split("=", 1)[-1].strip() if "=" in line else ""
            if raw_rhs.startswith("os.environ") or raw_rhs.startswith("os.getenv"):
                continue
            val = clean_captured_value(m.group("val"))
            simple = key.split(".")[-1]
            if is_sensitive_key(simple) or is_sensitive_key(key) or looks_like_secret_value(val):
                findings.append(
                    Finding(
                        rel_path,
                        line_no,
                        report_key_for(key, val),
                        redact_value(val),
                        source="python_assign",
                    )
                )

        for m in PY_DICT.finditer(line):
            key = m.group("key")
            val = clean_captured_value(m.group("val"))
            if is_sensitive_key(key) or looks_like_secret_value(val):
                findings.append(
                    Finding(
                        rel_path,
                        line_no,
                        report_key_for(key, val),
                        redact_value(val),
                        source="python_dict",
                    )
                )

        findings.extend(
            _value_pattern_findings(line, line_no, rel_path, "python_value")
        )

    return findings


def extract_js(text: str, rel_path: str) -> List[Finding]:
    findings: List[Finding] = []
    lines = text.splitlines()

    for line_no, line in enumerate(lines, start=1):
        for m in JS_ENV_DOT.finditer(line):
            key = m.group("key")
            if is_sensitive_key(key):
                findings.append(
                    Finding(
                        rel_path,
                        line_no,
                        key,
                        "<from-environ>",
                        source="js_process_env",
                    )
                )
        for m in JS_ENV_INDEX.finditer(line):
            key = m.group("key")
            if is_sensitive_key(key):
                findings.append(
                    Finding(
                        rel_path,
                        line_no,
                        key,
                        "<from-environ>",
                        source="js_process_env_index",
                    )
                )

        for pattern, source in (
            (JS_ASSIGN, "js_assign"),
            (JS_OBJ, "js_object"),
            (JS_OBJ_QUOTED, "js_object_quoted"),
        ):
            for m in pattern.finditer(line):
                key = m.group("key")
                val = clean_captured_value(m.group("val"))
                # Skip process.env assignments already handled
                if "process.env" in line and m.group("val") is None:
                    continue
                rhs = line[m.end() :] if False else ""
                if is_sensitive_key(key) or looks_like_secret_value(val):
                    # Avoid flagging process.env.X as assign value
                    if val.startswith("process.env"):
                        continue
                    findings.append(
                        Finding(
                            rel_path,
                            line_no,
                            report_key_for(key, val),
                            redact_value(val),
                            source=source,
                        )
                    )

        findings.extend(_value_pattern_findings(line, line_no, rel_path, "js_value"))

    return findings


def extract_env(text: str, rel_path: str) -> List[Finding]:
    findings: List[Finding] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = ENV_LINE.match(line)
        if not m:
            continue
        key = m.group("key")
        val = clean_captured_value(m.group("val"))
        if is_sensitive_key(key) or looks_like_secret_value(val):
            findings.append(
                Finding(
                    rel_path,
                    line_no,
                    report_key_for(key, val),
                    redact_value(val),
                    source="dotenv",
                )
            )
        findings.extend(
            _value_pattern_findings(line, line_no, rel_path, "dotenv_value")
        )
    return findings


def extract_from_generic_line(line: str, line_no: int, rel_path: str) -> List[Finding]:
    findings: List[Finding] = []
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or stripped.startswith(";"):
        return findings
    m = INI_ASSIGN.match(line)
    if m:
        key = m.group("key")
        val = clean_captured_value(m.group("val"))
        if is_sensitive_key(key) or looks_like_secret_value(val):
            findings.append(
                Finding(
                    rel_path,
                    line_no,
                    report_key_for(key, val),
                    redact_value(val),
                    source="generic_assign",
                )
            )
    findings.extend(
        _value_pattern_findings(line, line_no, rel_path, "generic_value")
    )
    return findings


def _approx_line_for_json_key(text: str, key: str, value: str) -> int:
    try:
        key_json = json.dumps(key)
        val_json = json.dumps(value)
    except (TypeError, ValueError):
        key_json, val_json = f'"{key}"', f'"{value}"'

    patterns = [
        re.compile(re.escape(key_json) + r"\s*:\s*" + re.escape(val_json)),
        re.compile(re.escape(key_json) + r"\s*:"),
    ]
    for pat in patterns:
        m = pat.search(text)
        if m:
            return text.count("\n", 0, m.start()) + 1
    return 1


def extract_json(text: str, rel_path: str) -> List[Finding]:
    findings: List[Finding] = []

    def walk(obj, path_prefix: str = "") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                key_path = f"{path_prefix}.{k}" if path_prefix else str(k)
                if isinstance(v, (dict, list)):
                    walk(v, key_path)
                elif isinstance(v, str):
                    if is_sensitive_key(str(k)) or looks_like_secret_value(v):
                        line_no = _approx_line_for_json_key(text, str(k), v)
                        findings.append(
                            Finding(
                                rel_path,
                                line_no,
                                report_key_for(str(k), v),
                                redact_value(v),
                                source="json",
                            )
                        )
                elif v is not None and is_sensitive_key(str(k)):
                    line_no = _approx_line_for_json_key(text, str(k), str(v))
                    findings.append(
                        Finding(
                            rel_path,
                            line_no,
                            str(k),
                            redact_value(str(v)),
                            source="json",
                        )
                    )
        elif isinstance(obj, list):
            for idx, item in enumerate(obj):
                walk(item, f"{path_prefix}[{idx}]")

    try:
        data = json.loads(text)
        walk(data)
    except json.JSONDecodeError:
        for line_no, line in enumerate(text.splitlines(), start=1):
            findings.extend(extract_from_generic_line(line, line_no, rel_path))

    for line_no, line in enumerate(text.splitlines(), start=1):
        findings.extend(
            _value_pattern_findings(line, line_no, rel_path, "json_value")
        )

    return findings


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def dedupe_findings(findings: List[Finding]) -> List[Finding]:
    """Remove exact duplicates and generic value-hits already covered by named keys."""
    # 1) exact sig
    exact_seen: Set[Tuple[str, int, str, str]] = set()
    unique: List[Finding] = []
    for f in findings:
        sig = (f.file, f.line, f.key, f.value_preview)
        if sig in exact_seen:
            continue
        exact_seen.add(sig)
        unique.append(f)

    drop: Set[int] = set()

    def is_value_pattern_hit(f: Finding) -> bool:
        return f.source in VALUE_PATTERN_SOURCES

    # 2) drop value-pattern hits if same file + same preview already has a named key hit
    #    (line may differ for multiline constructs, e.g. os.environ.get default)
    by_file_preview: dict[Tuple[str, str], List[Finding]] = {}
    for f in unique:
        by_file_preview.setdefault((f.file, f.value_preview), []).append(f)

    for group in by_file_preview.values():
        has_named = any(not is_value_pattern_hit(g) for g in group)
        if not has_named:
            continue
        for g in group:
            if is_value_pattern_hit(g):
                drop.add(id(g))

    # 3) drop near-duplicate keys on same line that only differ by path prefix
    #    e.g. "webhook_url" vs "integrations.webhook_url (secret-like value)"
    by_line: dict[Tuple[str, int], List[Finding]] = {}
    for f in unique:
        if id(f) in drop:
            continue
        by_line.setdefault((f.file, f.line), []).append(f)

    for group in by_line.values():
        if len(group) < 2:
            continue
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                if a.value_preview != b.value_preview:
                    continue
                a_simple = a.key.split(".")[-1].replace(" (secret-like value)", "")
                b_simple = b.key.split(".")[-1].replace(" (secret-like value)", "")
                if a_simple.lower() == b_simple.lower():
                    def rank(f: Finding) -> tuple:
                        return (
                            0 if is_value_pattern_hit(f) else 1,
                            0 if " " not in f.key and "." not in f.key else 1,
                            -len(f.key),
                        )

                    if rank(a) >= rank(b):
                        drop.add(id(b))
                    else:
                        drop.add(id(a))

    result = [f for f in unique if id(f) not in drop]
    result.sort(key=lambda f: (f.file, f.line, f.key))
    return result


# ---------------------------------------------------------------------------
# File scanning
# ---------------------------------------------------------------------------

def should_scan_file(path: Path) -> bool:
    name = path.name
    if name in SPECIAL_BASENAMES or name.startswith(".env"):
        return True
    return path.suffix.lower() in SCAN_EXTENSIONS


def iter_scan_files(root: Path) -> Iterator[Path]:
    root = root.resolve()
    if root.is_file():
        if should_scan_file(root):
            yield root
        return

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d
            for d in dirnames
            if d not in SKIP_DIR_NAMES and not d.startswith(".")
        ]
        for filename in filenames:
            path = Path(dirpath) / filename
            if should_scan_file(path):
                yield path


def read_text_safe(path: Path) -> Optional[str]:
    for enc in ("utf-8", "utf-8-sig", "gbk", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
        except OSError:
            return None
    return None


def classify_and_extract(path: Path, root: Path) -> List[Finding]:
    text = read_text_safe(path)
    if text is None:
        return []

    try:
        rel = str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        rel = str(path)
    rel = rel.replace("\\", "/")

    suffix = path.suffix.lower()
    name = path.name.lower()

    if suffix == ".json":
        findings = extract_json(text, rel)
    elif name.startswith(".env") or suffix == ".env":
        findings = extract_env(text, rel)
    elif suffix == ".py":
        findings = extract_python(text, rel)
    elif suffix in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
        findings = extract_js(text, rel)
    else:
        findings = []
        for line_no, line in enumerate(text.splitlines(), start=1):
            findings.extend(extract_env_line_as_generic(line, line_no, rel))
            findings.extend(extract_from_generic_line(line, line_no, rel))

    return dedupe_findings(findings)


def extract_env_line_as_generic(line: str, line_no: int, rel_path: str) -> List[Finding]:
    """Reuse dotenv parser for yaml/ini-ish KEY=VALUE lines."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return []
    m = ENV_LINE.match(line)
    if not m:
        return []
    key = m.group("key")
    val = clean_captured_value(m.group("val"))
    if is_sensitive_key(key) or looks_like_secret_value(val):
        return [
            Finding(
                rel_path,
                line_no,
                report_key_for(key, val),
                redact_value(val),
                source="dotenv_like",
            )
        ]
    return []


def scan_directory(target: Path) -> List[Finding]:
    root = target.resolve()
    if root.is_file():
        scan_root = root.parent
        files = iter_scan_files(root)
    else:
        scan_root = root
        files = iter_scan_files(root)

    all_findings: List[Finding] = []
    for path in files:
        all_findings.extend(classify_and_extract(path, scan_root))

    return dedupe_findings(all_findings)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="config_extractor.py",
        description=(
            "Scan a code repository for sensitive configuration items "
            "(API keys, DSNs, secrets, etc.) and output a redacted JSON audit list."
        ),
    )
    parser.add_argument(
        "directory",
        help="Root directory (or single file) to scan recursively",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="audit.json",
        help="Output JSON file path (default: audit.json)",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        default=True,
        help="Pretty-print JSON output (default: on)",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Write compact JSON (no indentation)",
    )
    parser.add_argument(
        "--include-source",
        action="store_true",
        help="Include internal detection source field in output",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress progress messages on stderr",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    target = Path(args.directory)
    if not target.exists():
        print(f"Error: path does not exist: {target}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(f"Scanning: {target.resolve()}", file=sys.stderr)

    findings = scan_directory(target)

    if args.include_source:
        payload = [asdict(f) for f in findings]
    else:
        payload = [f.to_dict() for f in findings]

    out_path = Path(args.output)
    if out_path.parent and str(out_path.parent) not in ("", "."):
        out_path.parent.mkdir(parents=True, exist_ok=True)

    indent = None if args.compact else 2
    text = json.dumps(payload, ensure_ascii=False, indent=indent)
    if not text.endswith("\n"):
        text += "\n"
    out_path.write_text(text, encoding="utf-8")

    if not args.quiet:
        print(f"Found {len(findings)} configuration item(s)", file=sys.stderr)
        print(f"Wrote: {out_path.resolve()}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())