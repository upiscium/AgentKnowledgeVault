# Retrieval Request contract v0.1

The SSOT is [`schemas/retrieval-request.schema.json`](../schemas/retrieval-request.schema.json).

## Minimum request

`task` is optional, so a caller can send a simple query. `mode` and `budget` are required because cost policy and bounded output are public behavior, not implementation defaults hidden from the caller.

```json
{
  "schema_version": "0.1",
  "query": "How must a pending action be revalidated?",
  "scope": ["global", "project:Terreate"],
  "mode": "auto",
  "budget": {"max_tokens": 800, "max_evidence_items": 5}
}
```

`scope` contains logical scopes only. Omitted scope means the service's documented caller-authorized default scope; it never grants additional authority.

## Modes and escalation

- **fast** starts and remains at Level 0. It prioritizes deterministic, low-cost retrieval and returns uncertainty rather than silently escalating.
- **auto** starts at Level 0 and may escalate to Level 1, then Level 2, only when lower levels cannot produce sufficient, non-conflicting evidence within budget.
- **thorough** permits starting with or escalating through higher-cost levels, including Level 2. It does not require escalation when Level 0 is sufficient.

Mode changes computation and escalation policy only. It never changes knowledge authority, caller scope, evidence requirements, or budget enforcement.

## Budget contract

`max_tokens` is a hard boundary for budgeted capsule content, not a preference. `max_evidence_items` is also a hard maximum. Budgeted content is the canonical compact JSON projection of `context`, claim statements grouped as `critical_facts`, `constraints`, and `pitfalls`, unresolved questions, and evidence excerpts. The projection uses lexicographically sorted object keys, no insignificant whitespace, UTF-8 encoding, unescaped Unicode, and preserves array order. Envelope keys, identifiers, provenance handles, retrieval telemetry, and the budget report are excluded from that projection to avoid self-referential accounting, but remain structurally bounded by the schemas.

1. When the requested/known tokenizer is available, the service uses exact token accounting. The returned accounting method is `exact_tokenizer`, precision is `exact`, and `used <= hard_limit == requested_tokens`.
2. When no exact tokenizer is available, the deterministic hard fallback is UTF-8 bytes. The service sets `hard_limit = 4 * requested_tokens`, method `utf8_bytes`, precision `conservative`, and requires `used <= hard_limit`. The multiplier is fixed for v0.1 and is not a token estimate claim.
3. A service must never return a successful capsule whose budgeted content exceeds the selected hard limit.

If sufficient content cannot fit, the service first removes lower-value evidence excerpts and redundant prose while preserving claim-to-evidence handles. It then returns `status: degraded` with an `insufficient_evidence` or other unresolved item. If even a truthful bounded result cannot fit, it returns `status: failed` with empty context and a machine-readable budget report; it must not spill raw chunks.

## Raw retrieval

A future raw API may support debug/evaluation/admin workflows, but it is not this request's primary response and must have independent authorization and limits. Unknown response fields such as `chunks` or `raw_results` are rejected by the Context Capsule schema.
