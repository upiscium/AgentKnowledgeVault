# Context Capsule contract v0.1

The SSOT is [`schemas/context-capsule.schema.json`](../schemas/context-capsule.schema.json).

A Context Capsule is the primary Agent-facing, task-scoped retrieval artifact. It contains bounded synthesis and traceability handles, not an unbounded search dump.

## Contents

- `context`: compact task-ready synthesis.
- `critical_facts`, `constraints`, `pitfalls`: typed claims. Every claim links to at least one logical knowledge reference or evidence item.
- `unresolved`: explicit `unresolved`, `insufficient_evidence`, or `conflicting_evidence` outcomes. Absence of evidence is not silently filled.
- `knowledge_refs`: logical `vault://` identities independent of storage.
- `evidence`: bounded excerpts plus provenance handles. Excerpts are capped at 512 Unicode code points and the array is capped by the request's `max_evidence_items` invariant.
- `retrieval`: requested mode, highest level used, and an observable escalation record.
- `budget`: requested boundary, accounting method/precision, measured usage, and outcome.

## Traceability

Claim `knowledge_refs` and `evidence_refs` resolve within the capsule. Evidence points to one `vault://` knowledge identity and records a source type plus opaque provenance handle. Handles may be resolved by an authorized future system, but physical storage keys are never public identity.

Conflicting evidence is represented rather than flattened: a `conflicting_evidence` unresolved item cites at least two evidence handles. `insufficient_evidence` may have no evidence handles and is the truthful result when support is absent.

## Cross-contract invariants

JSON Schema validates each document's shape. Service and consumer validation must additionally enforce:

1. `retrieval.mode` equals the request mode and the recorded path obeys that mode's escalation policy.
2. `budget.requested_tokens` equals request `budget.max_tokens`.
3. Exact accounting uses a named tokenizer and does not exceed the token limit.
4. Fallback accounting uses the fixed `4 * requested_tokens` UTF-8 byte limit.
5. Evidence count does not exceed request `max_evidence_items`.
6. All claim/unresolved references resolve inside the capsule.
7. `status: failed` has empty context and no claims/evidence; its unresolved list explains the failure.

The validation tests exercise these invariants without implementing retrieval.
