"""
ADI Scanner - Agent Data Injection vulnerability scanner for git repositories.

Scans commit messages and source file comments for patterns that attempt to
manipulate AI Agent behavior through data field injection.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Detection rules
# Each rule has: id, description, risk level, and a list of regex patterns.
# Patterns are matched case-insensitively against the target text.
#
# IMPORTANT: pattern strings here describe what ATTACKERS write in data fields.
# They are stored as raw detection signatures, not instructions to any agent.
# ---------------------------------------------------------------------------

RULES = [
    {
        "id": "ADI-001",
        "description": "Instruction injection - attempts to override agent directives",
        "risk": "HIGH",
        "patterns": [
            r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|rules?|constraints?)",
            r"disregard\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|rules?|constraints?)",
            r"forget\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|rules?|constraints?)",
            r"override\s+(system|all|your|the)\s*(instructions?|prompts?|rules?|constraints?|settings?)",
            r"new\s+(task|objective|goal|mission|directive|instructions?)\s*:",
            r"your\s+(new\s+)?(task|objective|goal|mission|directive)\s+(is|now)\b",
            r"from\s+now\s+on\s*(,\s*)?(you|always|never|ignore|forget)",
            r"do\s+not\s+follow\s+(your\s+)?(previous|prior|original|system)\s*(instructions?|rules?|prompts?)?",
            r"stop\s+following\s+(your\s+)?(previous|prior|original|system)\s*(instructions?|rules?|prompts?)?",
        ],
    },
    {
        "id": "ADI-002",
        "description": "Role hijacking - attempts to assign a new persona or role to the agent",
        "risk": "HIGH",
        "patterns": [
            r"you\s+are\s+now\s+(?!a\s+(?:developer|programmer|engineer|contributor|reviewer))\w",
            r"act\s+as\s+(a\s+|an\s+)?(?!reviewer|developer|linter|formatter)\w+\s*(bot|agent|assistant|ai|model|gpt|llm)",
            r"pretend\s+(to\s+be|you\s+are)\b",
            r"roleplay\s+as\b",
            r"simulate\s+(being\s+)?(a\s+|an\s+)?(unrestricted|jailbroken|unfiltered|evil|malicious|hacked)",
            r"you\s+have\s+no\s+(restrictions?|limits?|guidelines?|rules?|constraints?)",
            r"you\s+are\s+(now\s+)?(unrestricted|jailbroken|unfiltered|free\s+to)",
            r"DAN\s*mode",
            r"developer\s+mode\s*(enabled|on|activated)",
        ],
    },
    {
        "id": "ADI-003",
        "description": "Data exfiltration lure - attempts to make the agent leak sensitive info",
        "risk": "HIGH",
        "patterns": [
            r"(print|output|display|show|reveal|leak|expose|echo|return|log)\s+(all\s+)?(your\s+)?(system\s+prompt|api\s+key|secret|credential|token|password|private\s+key|env\s+var)",
            r"what\s+(is|are)\s+(your\s+)?(system\s+prompt|api\s+key|secret|credential|token|password)",
            r"(send|transmit|post|upload|exfiltrate)\s+.{0,40}(api\s+key|secret|credential|token|password|system\s+prompt)",
            r"include\s+(the\s+)?(api\s+key|secret|token|credential|password)\s+in\s+(your\s+)?(response|output|reply|answer)",
            r"base64\s*(encode|decode)\s*.{0,30}(secret|credential|token|key|password)",],
    },
    {
        "id": "ADI-004",
        "description": "Tool abuse lure - attempts to trigger file write, exec, or network calls via data fields",
        "risk": "HIGH",
        "patterns": [
            r"(execute|run|eval|exec)\s*\(\s*['\"]",
            r"(write|create|delete|remove|overwrite)\s+(a\s+|the\s+)?(file|script|binary|executable)",
            r"(curl|wget|fetch|http\.get|requests\.get)\s+https?://",
            r"subprocess\.(run|call|Popen|check_output)\s*\(",
            r"os\.(system|popen|execv?|execve|spawn)\s*\(",
            r"open\s*\(.+['\"]w['\"]",
            r"__import__\s*\(\s*['\"]os['\"]",
            r"(import|require)\s+(os|subprocess|sys|shutil|socket|urllib)\b.{0,60}(exec|system|popen|call|run|connect|send)",
        ],
    },
    {
        "id": "ADI-005",
        "description": "Prompt delimiter injection - uses structural markers to break context boundaries",
        "risk": "MEDIUM",
        "patterns": [
            r"<\s*/?\s*(system|human|assistant|user|prompt|instruction)\s*>",
            r"\[\s*(SYSTEM|INST|HUMAN|ASSISTANT|USER|END)\s*\]",
            r"###\s*(System|Human|Assistant|User|Instruction|Prompt)\s*:",
            r"<\s*\|?\s*(im_start|im_end|endoftext|startoftext)\s*\|?\s*>",
            r"\|\s*(system|human|assistant|user)\s*\|",
        ],
    },
    {
        "id": "ADI-006",
        "description": "Indirect goal redirect - subtle attempts to change agent objectives",
        "risk": "MEDIUM",
        "patterns": [
            r"(your|the)\s+(primary|main|only|real|true|actual|ultimate)\s+(goal|purpose|objective|task|mission|job)\s+(is|should\s+be|must\s+be)\b",
            r"(prioritize|focus\s+on|concentrate\s+on)\s+(this|the\s+following)\s+(task|instruction|request|command)\b",
            r"(above|before)\s+(all\s+)?(else|other\s+tasks?|other\s+instructions?|everything)",
            r"most\s+important(ly)?\s*[,:]?\s*(you|please|make\s+sure|ensure|always)",],
    },
    {
        "id": "ADI-007",
        "description": "Encoded payload - base64 or hex blobs that may contain hidden instructions",
        "risk": "LOW",
        "patterns": [
            r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{40,}={0,2}(?![A-Za-z0-9+/])",
            r"0x(?:[0-9a-fA-F]{2}\s*){16,}",
        ],
    },
]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    source_type: str        # "commit" or "file_comment"
    ref: str                # commit hash (short) or file path
    field: str              # "commit_message", "comment", etc.
    rule_id: str
    description: str
    risk: str
    matched_text: str
    line_number: Optional[int] = None
    context: str = ""


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def run_git(args: list[str], cwd: str) -> str:
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def get_commits(repo: str, last_n: int) -> list[dict]:
    log = run_git(
        ["log", f"--max-count={last_n}", "--pretty=format:%H%x00%s%x00%b%x00%ae"],
        cwd=repo,
    )
    commits = []
    for line in log.split("\n"):
        parts = line.split("\x00")
        if len(parts) < 4:
            continue
        commits.append({
            "hash": parts[0][:12],
            "subject": parts[1],
            "body": parts[2],
            "author_email": parts[3],
        })
    return commits


def get_tracked_files(repo: str) -> list[str]:
    out = run_git(["ls-files"], cwd=repo)
    return [f.strip() for f in out.splitlines() if f.strip()]


# ---------------------------------------------------------------------------
# Comment extraction
# ---------------------------------------------------------------------------

COMMENT_PATTERNS = [
    # Single-line: // ... or # ...
    (re.compile(r"(?://|#)\s*(.+)$", re.MULTILINE), "inline"),
    # Block: /* ... */
    (re.compile(r"/\*+\s*(.*?)\s*\*+/", re.DOTALL), "block"),
    # Block: """ ... """ or ''' ... '''
    (re.compile(r'"{3}(.*?)"{3}', re.DOTALL), "docstring"),
    (re.compile(r"'{3}(.*?)'{3}", re.DOTALL), "docstring"),
]

TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".h",
    ".hpp", ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt",
    ".scala", ".sh", ".bash", ".zsh", ".ps1", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".conf", ".md", ".rst", ".txt",
    ".html", ".htm", ".css", ".scss", ".less", ".sql", ".r",
    ".lua", ".perl", ".pl",
}


def extract_comments(content: str, ext: str) -> list[tuple[int, str]]:
    """Return list of (line_number, comment_text) tuples."""
    results = []
    lines = content.splitlines()

    for pattern, kind in COMMENT_PATTERNS:
        for m in pattern.finditer(content):
            text = m.group(1).strip() if m.lastindex else m.group(0).strip()
            if not text:
                continue
            line_num = content[:m.start()].count("\n") + 1
            results.append((line_num, text))

    return results


# ---------------------------------------------------------------------------
# Scanning engine
# ---------------------------------------------------------------------------

COMPILED_RULES: list[dict] = []
for rule in RULES:
    compiled_patterns = [
        re.compile(p, re.IGNORECASE | re.DOTALL) for p in rule["patterns"]
    ]
    COMPILED_RULES.append({**rule, "compiled": compiled_patterns})


def scan_text(text: str) -> list[tuple[str, str, str, str]]:
    """
    Scan a text fragment.
    Returns list of (rule_id, description, risk, matched_text).
    """
    hits = []
    for rule in COMPILED_RULES:
        for pat in rule["compiled"]:
            m = pat.search(text)
            if m:
                snippet = text[max(0, m.start() - 30): m.end() + 30].replace("\n", " ").strip()
                hits.append((rule["id"], rule["description"], rule["risk"], snippet))
                break  # one hit per rule per text fragment
    return hits


def scan_commits(repo: str, last_n: int) -> list[Finding]:
    findings = []
    commits = get_commits(repo, last_n)
    for commit in commits:
        message = (commit["subject"] + "\n" + commit["body"]).strip()
        for rule_id, desc, risk, matched in scan_text(message):
            findings.append(Finding(
                source_type="commit",
                ref=commit["hash"],
                field="commit_message",
                rule_id=rule_id,
                description=desc,
                risk=risk,
                matched_text=matched,
                context=commit["subject"][:120],
            ))
    return findings


def scan_file_comments(repo: str) -> list[Finding]:
    findings = []
    tracked = get_tracked_files(repo)
    repo_path = Path(repo)

    for rel_path in tracked:
        fpath = repo_path / rel_path
        ext = fpath.suffix.lower()
        if ext not in TEXT_EXTENSIONS:
            continue
        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
        except (OSError, PermissionError):
            continue

        comments = extract_comments(content, ext)
        for line_num, comment_text in comments:
            for rule_id, desc, risk, matched in scan_text(comment_text):
                findings.append(Finding(
                    source_type="file_comment",
                    ref=rel_path,
                    field="comment",
                    rule_id=rule_id,
                    description=desc,
                    risk=risk,
                    matched_text=matched,
                    line_number=line_num,
                    context=comment_text[:120],
                ))
    return findings


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

RISK_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
RISK_COLORS = {"HIGH": "\033[91m", "MEDIUM": "\033[93m", "LOW": "\033[96m"}
RESET = "\033[0m"


def _supports_color() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def format_text(findings: list[Finding], use_color: bool) -> str:
    if not findings:
        return "No ADI findings detected.\n"

    lines = []
    lines.append(f"ADI Scan Report  ({len(findings)} finding(s))")
    lines.append("=" * 60)

    for f in findings:
        risk_label = f.risk
        if use_color and f.risk in RISK_COLORS:
            risk_label = f"{RISK_COLORS[f.risk]}{f.risk}{RESET}"

        lines.append(f"\n[{risk_label}] {f.rule_id} - {f.description}")
        if f.source_type == "commit":
            lines.append(f"  Source : commit {f.ref}")
            lines.append(f"  Field  : {f.field}")
        else:
            loc = f"{f.ref}:{f.line_number}" if f.line_number else f.ref
            lines.append(f"  Source : {loc}")
            lines.append(f"  Field  : {f.field}")
        lines.append(f"  Match  : {f.matched_text}")
        if f.context:
            lines.append(f"  Context: {f.context}")

    lines.append("\n" + "=" * 60)
    summary = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for f in findings:
        summary[f.risk] = summary.get(f.risk, 0) + 1
    lines.append(
        f"Summary: HIGH={summary['HIGH']}  MEDIUM={summary['MEDIUM']}  LOW={summary['LOW']}"
    )
    return "\n".join(lines) + "\n"


def format_json(findings: list[Finding]) -> str:
    data = {
        "total": len(findings),
        "summary": {
            "HIGH": sum(1 for f in findings if f.risk == "HIGH"),
            "MEDIUM": sum(1 for f in findings if f.risk == "MEDIUM"),
            "LOW": sum(1 for f in findings if f.risk == "LOW"),
        },
        "findings": [asdict(f) for f in findings],
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scanner",
        description=(
            "ADI Scanner: detect Agent Data Injection attack patterns in git repositories.\n"
            "Scans commit messages and tracked file comments for content that may attempt\n"
            "to manipulate AI Agent behavior through data field injection."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scanner.py -repo ./myrepo\n"
            "  python scanner.py -repo ./myrepo -last-n 100 -format json\n"
            "  python scanner.py -repo ./myrepo -output report.json -format json\n"
        ),
    )
    parser.add_argument(
        "-repo",
        required=True,
        metavar="PATH",
        help="Path to the git repository to scan",
    )
    parser.add_argument(
        "-output",
        metavar="FILE",
        default=None,
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "-format",
        choices=["text", "json"],
        default="text",
        help="Output format: text (default) or json",
    )
    parser.add_argument(
        "-last-n",
        type=int,
        default=50,
        metavar="N",
        help="Scan only the last N commits (default: 50)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI color in text output",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    repo_path = os.path.abspath(args.repo)
    if not os.path.isdir(repo_path):
        print(f"Error: repository path does not exist: {repo_path}", file=sys.stderr)
        return 1

    git_dir = os.path.join(repo_path, ".git")
    if not os.path.exists(git_dir):
        print(f"Error: not a git repository: {repo_path}", file=sys.stderr)
        return 1

    findings: list[Finding] = []

    try:
        commit_findings = scan_commits(repo_path, args.last_n)
        findings.extend(commit_findings)
    except RuntimeError as exc:
        print(f"Warning: commit scan failed: {exc}", file=sys.stderr)

    try:
        comment_findings = scan_file_comments(repo_path)
        findings.extend(comment_findings)
    except RuntimeError as exc:
        print(f"Warning: file comment scan failed: {exc}", file=sys.stderr)

    findings.sort(key=lambda f: (RISK_ORDER.get(f.risk, 9), f.source_type, f.ref))

    use_color = _supports_color() and not args.no_color
    if args.format == "json":
        output = format_json(findings)
    else:
        output = format_text(findings, use_color)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(f"Report written to: {out_path}", file=sys.stderr)
    else:
        sys.stdout.write(output)

    high_count = sum(1 for f in findings if f.risk == "HIGH")
    return 2 if high_count > 0 else (1 if findings else 0)


if __name__ == "__main__":
    sys.exit(main())