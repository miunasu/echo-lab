# PLAN - ADI Scanner

## Background

As AI Agents are increasingly integrated into development workflows (code review,
commit summarization, automated PR generation, changelog generation), they
consume user-controlled data such as commit messages and code comments. An
adversary with commit access — or who can influence repository content — may
embed adversarial text in these fields to manipulate Agent behavior. This is
classified as Agent Data Injection (ADI).

This tool provides static, offline detection of ADI patterns in git repositories,
targeting the researcher and security engineer audience.

---

## Design Decisions

###1. Static regex over LLM-based detection

**Decision**: Use curated regex pattern sets rather than sending text to an LLM
for classification.

**Rationale**:
- Offline and reproducible — no API dependency, deterministic results
- Safe — avoids the irony of sending potentially adversarial payloads to an LLMduring a security scan
- Fast — suitable for pre-commit hooks and CI pipelines
- Auditable — every rule and its rationale is visible in the source

**Tradeoff**: Lower recall on novel or obfuscated payloads. Addressed by ADI-007
(encoded payload detection) and planned semantic analysis extensions.

### 2. Risk tiers (HIGH / MEDIUM / LOW)

**Decision**: Three-tier risk classification rather than a numeric score.

**Rationale**: Mirrors industry-standard vulnerability severity language (CVSSv3
qualitative scale). Enables CI integration via exit codes without requiring
threshold tuning. HIGH maps to exit code 2 for automated blocking.

### 3. Scan scope: commits + file comments only

**Decision**: Initial scope limited to git log commit messages and source file
comments. Does not scan issue bodies, CI config, or arbitrary text files.

**Rationale**: These two surfaces are the highest-value injection vectors in a
typical Agent-assisted development workflow:
- Commit messages are frequently fed to summarization and changelog Agents
- Code comments are read by review, documentation, and refactoring Agents

### 4. Self-exclusion of detection signatures

**Decision**: Pattern strings in the tool source are stored as detection
signatures, not as natural language instructions. The tool does not scan itself
by default (it is not in the target repository).

**Rationale**: Prevents the tool's own rule patterns from triggering ADI-001
or ADI-002 alerts when the tool source is present in a scanned repository. If
a user intentionally places this tool inside the scanned repo, they should add
the scanner directory to a `.adiignore` (future feature).

---

## Architecture

```
scanner.py
  |
  +-- RULES[]: Static rule definitions (id, risk, patterns)
  +-- COMPILED_RULES[]     : Pre-compiled regex objects (module load time)
  |
  +-- get_commits()        : git log -> list of commit dicts
  +-- get_tracked_files()  : git ls-files -> file list
  +-- extract_comments()   : regex-based comment extractor
  +-- scan_text()          : apply COMPILED_RULES to a text fragment
  |
  +-- scan_commits()       : commits -> list[Finding]
  +-- scan_file_comments() : tracked files -> list[Finding]
  |
  +-- format_text()        : Finding[] -> human-readable report
  +-- format_json()        : Finding[] -> JSON report
  |
  +-- main()               : CLI argument parsing, orchestration, output
```

---

## Rule Design Notes

### ADI-001: Instruction Injection
Targets the canonical prompt injection phrase family. Patterns cover common
variations: "ignore/disregard/forget previous instructions", "override system
prompt", "new task:", "from now on". Anchored to prevent false positives on
legitimate security documentation by requiring the full phrase structure.

### ADI-002: Role Hijacking
Targets persona reassignment phrases. Excludes common legitimate roles
(developer, reviewer, linter) to reduce false positives in code review contexts.
DAN mode and "developer mode enabled" are included as known jailbreak markers.

### ADI-003: Data Exfiltration Lure
Targets instructions to print, output, send, or encode secrets. Covers API keys,
credentials, tokens, passwords, private keys, environment variables, and system
prompts. Includes base64-encode-secret combinations.

### ADI-004: Tool Abuse Lure
Targets embedded code patterns that could trigger agent tool use: file writes,
subprocess calls, os.system, HTTP fetch, and dynamic import of OS modules.
Relevant when Agents have code execution or file system tool access.

### ADI-005: Prompt Delimiter Injection
Targets structural markers used to fake context boundaries in LLM inputs:
`<system>`, `[INST]`, `### Human:`, `<|im_start|>`, and similar. These are used
to inject fake turns into the conversation context.

### ADI-006: Indirect Goal Redirect
Targets softer manipulation: "your primary goal is", "prioritize this task",
"above all else". Lower confidence than ADI-001, classified as MEDIUM.

### ADI-007: Encoded Payload
Targets long base64 or hex blobs. These are LOW confidence (high false positive
rate from legitimate binary data in comments) but worth flagging for manual
review. A future improvement is to decode and re-scan the payload content.

---

## Planned Extensions

### Short term
- `.adiignore` file support to exclude paths or rule IDs
- `--since` / `--until` date range filter for commit scan
- Decode-and-rescan for ADI-007 (base64/hex payloads)
- Pre-commit hook installer (`scanner --install-hook`)

### Medium term
- Scan additional surfaces: PR/issue body (via GitHub/GitLab API), CI YAML values
- Semantic similarity detection using a local embedding model (no API calls)
- Confidence scoring with false-positive suppression heuristics
- SARIF output format for integration with GitHub Code Scanning

### Long term
- Differential scan mode: only scan changed lines in a diff
- Red-team payload generator for testing Agent robustness
- Integration with CAPE sandbox output (cross-reference with malware-yara-extraction skill)
- Supply chain variant: scan dependencies' commit histories for ADI patterns

---

## Testing Strategy

Manual test vectors (to be formalized as pytest cases):

1. Create a repo with a known-malicious commit message containing ADI-001 text;assert scanner returns exit code 2 and one HIGH finding.
2. Create a Python file with a comment containing ADI-004 patterns; assert
   file_comment finding with correct line number.
3. Scan a clean repository with no injections; assert exit code 0 and empty
   findings list.
4. Run with `-format json` and validate JSON schema.
5. Verify `--help` output and that `-repo` is required.