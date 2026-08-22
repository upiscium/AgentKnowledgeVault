# Retrieval Request contract v0.1

The SSOT is [`schemas/retrieval-request.schema.json`](../schemas/retrieval-request.schema.json).

## Minimum request

`task` is optional, so a caller can send a simple query. `mode` and `budget` are required because cost policy and bounded output are public behavior, not implementation defaults hidden from the caller.

```json
{
  "schema_version": "0.1",
  "query": "How must a pending action be revalidated?",
  "scope": ["global", "project/terreate"],
  "mode": "auto",
  "budget": {"max_tokens": 800, "max_bytes": 3200, "max_evidence_items": 5}
}
```

`scope` contains logical selectors derived from the `global`, `project`, `research`, and `private` namespace grammar. Nested selectors are allowed. Omitted scope means exactly `["global"]` in v0.1. A selector only narrows retrieval; it never grants authority or bypasses ACL decisions.

## Modes and escalation

- **fast** starts and remains at Level 0. It prioritizes deterministic, low-cost retrieval and returns uncertainty rather than silently escalating.
- **auto** starts at Level 0 and may escalate to Level 1, then Level 2, only when lower levels cannot produce sufficient, non-conflicting evidence within budget.
- **thorough** permits starting with or escalating through higher-cost levels, including Level 2. It does not require escalation when Level 0 is sufficient.

Mode changes computation and escalation policy only. It never changes knowledge authority, caller scope, evidence requirements, or budget enforcement.

## Budget contract

The accounting payload is the entire caller-visible Context Capsule except the top-level `budget` report. It therefore includes schema/status fields, context, complete claims, IDs, `vault://` URIs and revisions, confidence, reference arrays, unresolved items, evidence and provenance, and retrieval telemetry. The payload uses lexicographically sorted object keys, no insignificant whitespace, UTF-8 encoding, unescaped Unicode, and preserves array order. Only `budget` is excluded to avoid self-reference; that report has a fixed field set, bounded strings, and bounded integers in the schema.

1. `max_tokens` is a hard token boundary only when the service resolves and reports an exact tokenizer. The report uses `method: exact_tokenizer`, `guarantee: exact_tokens`, names `tokenizer_id`, and requires `used <= hard_limit == requested_tokens`.
2. `max_bytes` is an independent hard fallback boundary. When no exact tokenizer is available, the report uses `method: utf8_bytes`, `guarantee: hard_bytes`, and requires `used == serialized_bytes <= hard_limit == requested_bytes`. This makes no claim that the resulting payload is at most `max_tokens` for an unknown tokenizer.
3. `max_evidence_items` is an independent hard maximum.
4. A service must never return a successful capsule whose complete accounting payload exceeds the selected hard boundary.

If sufficient content cannot fit, the service first removes lower-value evidence excerpts and redundant prose while preserving claim-to-evidence handles. It then returns `status: degraded` with an `insufficient_evidence` or other unresolved item. If even a truthful complete accounting payload cannot fit, it returns `status: failed` with empty context and a machine-readable budget report; it must not spill raw chunks. A caller that requires an exact token guarantee must treat a `hard_bytes` result as lacking that guarantee and may reject it.

## Raw retrieval

A future raw API may support debug/evaluation/admin workflows, but it is not this request's primary response and must have independent authorization and limits. Unknown response fields such as `chunks` or `raw_results` are rejected by the Context Capsule schema.
