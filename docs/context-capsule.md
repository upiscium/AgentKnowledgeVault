# Context Capsule contract v0.1

The SSOT is [`schemas/context-capsule.schema.json`](../schemas/context-capsule.schema.json).

A Context Capsule is the primary Agent-facing, task-scoped retrieval artifact. It contains bounded synthesis and traceability handles, not an unbounded search dump.

## Contents

- `context`: compact task-ready synthesis.
- `critical_facts`, `constraints`, `pitfalls`: typed claims. Every claim links to at least one logical knowledge reference or evidence item.
- `unresolved`: explicit `unresolved`, `insufficient_evidence`, or `conflicting_evidence` outcomes. Absence of evidence is not silently filled.
- `knowledge_refs`: nested logical `vault://global/...`, `vault://project/<project>/...`, `vault://research/<topic>/...`, or `vault://private/<scope>/...` identities independent of storage.
- `evidence`: bounded excerpts plus provenance handles. Excerpts are capped at 512 Unicode code points and the array is capped by the request's `max_evidence_items` invariant.
- `retrieval`: requested mode, highest level used, and an observable escalation record.
- `budget`: requested token and byte boundaries, accounting method/guarantee, measured usage, and outcome.

## Traceability

Claim `knowledge_refs` and `evidence_refs` resolve within the capsule. Evidence points to one `vault://` knowledge identity and records a source type plus opaque provenance handle. Handles may be resolved by an authorized future system, but physical storage keys are never public identity.

Conflicting evidence is represented rather than flattened: a `conflicting_evidence` unresolved item cites at least two evidence handles. `insufficient_evidence` may have no evidence handles and is the truthful result when support is absent.

## Cross-contract invariants

JSON Schema validates each document's shape. Service and consumer validation must additionally enforce:

1. `retrieval.mode` equals the request mode and the recorded path obeys that mode's escalation policy.
2. `budget.requested_tokens` and `budget.requested_bytes` equal request `budget.max_tokens` and `budget.max_bytes`.
3. Exact accounting uses a named tokenizer over the complete capsule payload excluding `budget` and does not exceed the token limit.
4. Fallback accounting measures that same payload in UTF-8 bytes, does not exceed `max_bytes`, and makes no unknown-tokenizer token-count guarantee.
5. Evidence count does not exceed request `max_evidence_items`.
6. All claim/unresolved references resolve inside the capsule.
7. `status` and budget outcome agree: complete/within-budget, degraded/degraded, or failed/failed.
8. `status: failed` has empty context and no claims/evidence; its unresolved list explains the failure.
9. If even the minimum failed capsule cannot fit, no capsule is generated; retrieval returns the bounded `budget_too_small_for_capsule` protocol error instead.

The validation tests exercise these invariants without implementing retrieval.
