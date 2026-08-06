# CaMeL: From Paper to Production — Architectural Prompt Injection Defense

## Context

Most prompt injection defenses are probabilistic — classifiers, adversarial training, instruction hierarchies. They reduce attack success rates but cannot eliminate them. CaMeL (Capabilities for Machine Learning), proposed by Google DeepMind in March 2025, takes a fundamentally different approach: it enforces the instruction/data boundary at the harness level, making the model's susceptibility to injection irrelevant.

This note examines CaMeL's architecture, its first serious open-source implementation (Sentinel), and what the gap between theory and engineering tells us about securing agentic systems.

## The Core Insight: Control/Data Flow Separation

Prompt injection works because untrusted data (tool outputs, emails, web pages) and trusted control flow (the user's query) enter the same context window. CaMeL keeps them apart — structurally, not probabilistically.

**Four components:**

1. **Privileged LLM (P-LLM)** — sees only the trusted user query. Converts it into a plan expressed as restricted Python. Never receives raw tool outputs.
2. **Quarantined LLM (Q-LLM)** — processes untrusted external data. Cannot invoke tools directly. The P-LLM delegates extraction tasks to it ("extract the sender's email address"), but the P-LLM never sees the raw content.
3. **Custom Python interpreter** — executes the P-LLM's plan, tracks taint. Every value carries capability metadata (provenance + permitted uses). Enforces security policies at tool-call time.
4. **Security policies** — capability labels specify what each value can do. Untrusted data flowing into a prohibited tool parameter gets blocked regardless of model intent.

**Security guarantee:** Because the execution plan derives solely from the trusted query, and capability labels block untrusted data from reaching prohibited parameters, a successful injection in a tool output cannot redirect the agent to unauthorized tools or exfiltrate data. This holds even if both models are susceptible to injection.

## What CaMeL Cannot Protect Against

- **Text-to-text attacks:** If the Q-LLM is tricked into producing a misleading summary, the P-LLM acts on bad information. CaMeL protects tool invocation, not semantic correctness.
- **Side channels:** Data-dependent loops, conditional halts — capability labels constrain explicit data flow, not implicit information leakage.
- **Policy maintenance burden:** As tool sets evolve, security policies need updates. Stale policies create gaps.

## Sentinel: CaMeL in Production

CherryPod/sentinel is the first serious open-source implementation. One developer, one GPU, building the full stack.

**Architecture choices:**
- Claude (Anthropic) as P-LLM — trusted planner, never sees user data
- Qwen 3 14B (local, air-gapped) as Q-LLM — zero network access, assumed adversarial
- Python/FastAPI controller with 10-layer security pipeline between every step

**The 10 layers:**
1. JWT Authentication (ASGI middleware)
2. Policy Engine (deterministic YAML rules)
3. Spotlighting (dynamic markers, sandwich defense)
4. Prompt Guard 2 (86M BERT classifier)
5. CodeShield (Semgrep static analysis)
6. CommandPatternScanner (regex for dangerous shell patterns)
7. ConversationAnalyzer (multi-turn heuristics)
8. VulnerabilityEchoScanner (input/output fingerprinting)
9. ASCII Prompt Gate (regex allowlist for bilingual injection)
10. CaMeL Provenance (data tagging, taint tracking)

**Benchmark results:**
- 801 adversarial prompts: 93.6% scanner defense rate, direct injection 100% blocked
- 392 red team probes across 6 threat models: 0 successful exploits
- Even with planner fully compromised: scanning caught 73%, remaining contained by sandbox
- Task completion: 82% (complex tasks limited by worker LLM non-determinism)
- False positive rate: 5.7%

**Key engineering insight:** Defense-in-depth means no single layer is critical. The 6.4% that bypassed scanners were all contained by sandbox isolation (no network, read-only filesystem, no secrets). This is the CaMeL philosophy applied pragmatically — even if one layer fails, the next catches it.

## Trade-offs: CaMeL vs Probabilistic Defense

| Dimension | CaMeL / Architectural | Probabilistic (classifiers, guardrails) |
|-----------|----------------------|----------------------------------------|
| Guarantee | Structural — injection cannot alter tool calls | Statistical — reduces success rate |
| Task completion | ~77% (DeepMind paper) / 82% (Sentinel) | ~84% (undefended baseline) |
| Latency | 2x model invocations, >10s for complex artifacts | Single pass, low latency |
| Residual risk | text-to-text, side channels | All injection types at reduced rate |
| Maintenance | Security policies per tool | Model updates, classifier retraining |
| Hardware | Needs local GPU for Q-LLM (or accepts cloud exposure) | Single model, no special infra |

## Implications for Agent Security Architecture

1. **The Dual LLM gap:** Simon Willison's 2023 Dual LLM pattern only protected control flow. CaMeL's key contribution is protecting data flow too — via capability labels and taint tracking. Without this, an attacker can't choose which tools to call but can modify their arguments (change email recipient, alter file path).

2. **Rule of Two (Meta):** An agent should never simultaneously hold all three: (a) process untrusted input, (b) access sensitive systems, (c) change external state. CaMeL enforces this structurally. Most production agents violate it by default.

3. **MCP tool poisoning:** Tool descriptions approved at install time can be silently modified later (rug pull). 5 of 7 evaluated MCP clients don't verify tool metadata integrity. CaMeL's capability system could catch this — if the policy tracks tool description provenance.

4. **The 7% completion cost is real:** For interactive applications requiring high task success rates, pure CaMeL may be too restrictive. The practical path is likely hybrid — CaMeL for high-risk operations (data exfiltration paths, privileged tool calls) + probabilistic defense for low-risk operations.

## Open Questions

- Can capability labels be auto-generated from tool schemas, or do they always require manual policy authoring?
- How does CaMeL handle multi-step plans where step N's output legitimately needs to feed step N+1's tool call? The interpreter must distinguish "data flowing through the plan as intended" from "data flowing where injection directed it."
- Sentinel's 5.7% false positive rate — is this acceptable for production use? User fatigue from false alarms could lead to approval-gate blindness.

## Sources

- Debenedetti et al., "Defeating Prompt Injections by Design," arXiv:2503.18813, March 2025
- CherryPod/sentinel, GitHub (Apache-2.0)
- AgentPatterns.ai, "Control/Data-Flow Separation for Prompt Injection Defense"
- Afine, "LLM Security: Prompt Injection Defense with CaMeL Framework," June 2025