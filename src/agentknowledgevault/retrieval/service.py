"""Deterministic Level 0 retrieval and Context Capsule assembly."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentknowledgevault.vault.models import KnowledgeRecord
from agentknowledgevault.vault.repository import VaultRepository

from .budget import BudgetAccountant, ExactTokenCounter
from .eligibility import (
    RetrievalEligibility,
    has_unevaluated_conditions,
    record_freshness,
    scope_specificity,
)
from .index import DerivedLexicalIndex, normalized_terms
from .models import (
    RankedKnowledge,
    RetrievalDiagnostics,
    RetrievalRequest,
    RetrievalResult,
)
from .request import parse_retrieval_request

Clock = Callable[[], datetime]
Monotonic = Callable[[], float]


def utc_now() -> datetime:
    return datetime.now(UTC)


class Level0RetrievalService:
    """Canonical-only deterministic retrieval with a disposable lexical index."""

    def __init__(
        self,
        repository: VaultRepository,
        index_path: str | Path | None = None,
        *,
        clock: Clock = utc_now,
        token_counters: Mapping[str, ExactTokenCounter] | None = None,
        monotonic: Monotonic = time.perf_counter,
    ) -> None:
        canonical_path = repository.database_path
        derived_path = Path(
            index_path or canonical_path.with_suffix(".level0-index.db")
        )
        if derived_path.resolve() == canonical_path.resolve():
            raise ValueError("derived lexical index must not be the canonical Vault DB")
        self.repository = repository
        self.index = DerivedLexicalIndex(derived_path)
        self._clock = clock
        self._eligibility = RetrievalEligibility()
        self._token_counters = dict(token_counters or {})
        self._monotonic = monotonic

    def rebuild_index(self) -> str:
        """Explicitly rebuild disposable lexical state from canonical records."""

        return self.index.rebuild(self.repository.list_knowledge()).watermark

    def retrieve(self, request_value: Mapping[str, Any]) -> RetrievalResult:
        started = self._monotonic()
        request = parse_retrieval_request(request_value)
        accountant = BudgetAccountant(request, self._token_counters)
        minimum_payload = accountant.minimum_failed_payload()
        minimum_measurement = accountant.measure(minimum_payload)
        if not minimum_measurement.fits:
            return self._result(
                capsule=None,
                error=accountant.budget_too_small_error(minimum_measurement),
                counts=(0, 0, 0, 0, 0, 0, 0),
                index_rebuilt=False,
                watermark="not-synchronized",
                serialized_bytes=0,
                started=started,
            )

        records = self.repository.list_knowledge()
        sync = self.index.synchronize(records)
        eligible, counts = self._eligible_records(records, request)
        try:
            search_hits = self.index.search(request.query)
        except sqlite3.DatabaseError:
            sync = self.index.rebuild(records)
            search_hits = self.index.search(request.query)
        hits = {hit.knowledge_ref: hit for hit in search_hits}
        ranked = self._rank(eligible, hits, request)
        capsule, measurement, selected_count = self._assemble(
            ranked, records, request, accountant
        )
        return self._result(
            capsule=capsule,
            error=None,
            counts=(counts[0], selected_count, *counts[1:]),
            index_rebuilt=sync.rebuilt,
            watermark=sync.watermark,
            serialized_bytes=measurement.serialized_bytes,
            started=started,
        )

    def _eligible_records(
        self, records: list[KnowledgeRecord], request: RetrievalRequest
    ) -> tuple[list[KnowledgeRecord], tuple[int, int, int, int, int, int]]:
        eligible, counts = self._eligibility.filter(
            records, request.scope, self._clock()
        )
        return eligible, (
            counts.candidate_count,
            counts.excluded_scope,
            counts.excluded_lifecycle,
            counts.excluded_applicability,
            counts.excluded_stale,
            counts.malformed_freshness,
        )

    def _rank(
        self,
        eligible: list[KnowledgeRecord],
        hits: Mapping[str, Any],
        request: RetrievalRequest,
    ) -> list[RankedKnowledge]:
        query = normalized_terms(request.query)
        requested_topics = (
            {normalized_terms(topic) for topic in request.task.topics}
            if request.task is not None
            else set()
        )
        ranked: list[RankedKnowledge] = []
        for record in eligible:
            hit = hits.get(record.knowledge_ref)
            if hit is None:
                continue
            tags = {normalized_terms(tag) for tag in record.tags}
            path_topics = {
                normalized_terms(part) for part in record.knowledge_path.split("/")
            }
            ranked.append(
                RankedKnowledge(
                    knowledge_ref=record.knowledge_ref,
                    lexical_score=hit.score,
                    exact_title=query == normalized_terms(record.title),
                    exact_tag=query in tags,
                    exact_topic=bool(requested_topics & (tags | path_topics)),
                    scope_specificity=self._scope_specificity(
                        record.knowledge_ref, request.scope
                    ),
                )
            )
        return sorted(
            ranked,
            key=lambda item: (
                -item.exact_title,
                -item.exact_tag,
                -item.exact_topic,
                item.lexical_score,
                -item.scope_specificity,
                item.knowledge_ref,
            ),
        )

    def _assemble(
        self,
        ranked: list[RankedKnowledge],
        records: list[KnowledgeRecord],
        request: RetrievalRequest,
        accountant: BudgetAccountant,
    ) -> tuple[dict[str, Any], Any, int]:
        by_ref = {record.knowledge_ref: record for record in records}
        cap = request.budget.max_evidence_items
        candidates = [by_ref[item.knowledge_ref] for item in ranked[:cap]]
        omitted_by_cap = len(ranked) > len(candidates)

        if not ranked:
            payload = self._failed_payload(
                request,
                question="no eligible canonical Level 0 evidence matched the request",
                terminal_reason="insufficient_evidence",
            )
            capsule, measurement = accountant.finalize(payload, outcome="failed")
            if measurement.fits:
                return capsule, measurement, 0
            minimum = accountant.minimum_failed_payload()
            capsule, measurement = accountant.finalize(minimum, outcome="failed")
            return capsule, measurement, 0

        if not candidates:
            payload = self._failed_payload(
                request,
                question=(
                    "matching canonical evidence could not be included because "
                    "max_evidence_items is zero"
                ),
                terminal_reason="budget_limited",
            )
            capsule, measurement = accountant.finalize(payload, outcome="failed")
            if measurement.fits:
                return capsule, measurement, 0
            minimum = accountant.minimum_failed_payload()
            capsule, measurement = accountant.finalize(minimum, outcome="failed")
            return capsule, measurement, 0

        for selected_count in range(len(candidates), 0, -1):
            selected = candidates[:selected_count]
            degraded = omitted_by_cap or selected_count < len(candidates)
            payload = self._evidence_payload(request, selected, degraded=degraded)
            outcome = "degraded" if degraded else "within_budget"
            capsule, measurement = accountant.finalize(payload, outcome=outcome)
            if measurement.fits:
                return capsule, measurement, selected_count

        minimum = accountant.minimum_failed_payload()
        capsule, measurement = accountant.finalize(minimum, outcome="failed")
        return capsule, measurement, 0

    def _evidence_payload(
        self,
        request: RetrievalRequest,
        records: list[KnowledgeRecord],
        *,
        degraded: bool,
    ) -> dict[str, Any]:
        knowledge_refs: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        context_parts: list[str] = []
        for position, record in enumerate(records, start=1):
            knowledge_id = f"knowledge-{position}"
            evidence_id = f"evidence-{position}"
            knowledge_refs.append(
                {
                    "id": knowledge_id,
                    "uri": record.knowledge_ref,
                    "revision": str(record.revision),
                }
            )
            evidence.append(
                {
                    "id": evidence_id,
                    "knowledge_ref": knowledge_id,
                    "excerpt": self._excerpt(record.body, record.title, request.query),
                    "provenance": self._provenance(record),
                }
            )
            context_parts.append(f"{record.title} [{knowledge_id}]")

        unresolved: list[dict[str, Any]] = []
        if degraded:
            unresolved.append(
                {
                    "id": "budget",
                    "kind": "insufficient_evidence",
                    "question": "context budget or evidence cap prevented inclusion of lower-ranked evidence",
                    "knowledge_refs": [],
                    "evidence_refs": [],
                }
            )
        return {
            "schema_version": "0.1",
            "status": "degraded" if degraded else "complete",
            "context": "Relevant canonical knowledge: " + "; ".join(context_parts),
            "critical_facts": [],
            "constraints": [],
            "pitfalls": [],
            "unresolved": unresolved,
            "knowledge_refs": knowledge_refs,
            "evidence": evidence,
            "retrieval": {
                "mode": request.mode,
                "level": 0,
                "path": [0],
                "terminal_reason": "budget_limited" if degraded else "sufficient",
            },
        }

    @staticmethod
    def _failed_payload(
        request: RetrievalRequest, *, question: str, terminal_reason: str
    ) -> dict[str, Any]:
        return {
            "schema_version": "0.1",
            "status": "failed",
            "context": "",
            "critical_facts": [],
            "constraints": [],
            "pitfalls": [],
            "unresolved": [
                {
                    "id": "evidence",
                    "kind": "insufficient_evidence",
                    "question": question,
                    "knowledge_refs": [],
                    "evidence_refs": [],
                }
            ],
            "knowledge_refs": [],
            "evidence": [],
            "retrieval": {
                "mode": request.mode,
                "level": 0,
                "path": [0],
                "terminal_reason": terminal_reason,
            },
        }

    def _result(
        self,
        *,
        capsule: dict[str, Any] | None,
        error: dict[str, Any] | None,
        counts: tuple[int, int, int, int, int, int, int],
        index_rebuilt: bool,
        watermark: str,
        serialized_bytes: int,
        started: float,
    ) -> RetrievalResult:
        finished = self._monotonic()
        diagnostics = RetrievalDiagnostics(
            candidate_count=counts[0],
            selected_count=counts[1],
            excluded_scope_count=counts[2],
            excluded_lifecycle_count=counts[3],
            excluded_applicability_count=counts[4],
            excluded_stale_count=counts[5],
            malformed_freshness_count=counts[6],
            index_rebuilt=index_rebuilt,
            index_watermark=watermark,
            serialized_bytes=serialized_bytes,
            elapsed_ms=max(0.0, (finished - started) * 1000),
        )
        return RetrievalResult(capsule, error, diagnostics)

    @staticmethod
    def _scope_specificity(knowledge_ref: str, selectors: tuple[str, ...]) -> int:
        return scope_specificity(knowledge_ref, selectors)

    @staticmethod
    def _freshness(stale_after: str | None, now: datetime) -> str:
        return record_freshness(stale_after, now)

    @staticmethod
    def _has_unevaluated_conditions(record: KnowledgeRecord) -> bool:
        return has_unevaluated_conditions(record)

    @staticmethod
    def _excerpt(body: str, title: str, query: str, limit: int = 320) -> str:
        source = body.strip() or title.strip()
        if not source:
            return "Untitled canonical knowledge"
        tokens = normalized_terms(query).split()
        folded = source.casefold()
        positions = [folded.find(token) for token in tokens if folded.find(token) >= 0]
        center = min(positions) if positions else 0
        start = max(0, center - limit // 3)
        end = min(len(source), start + limit)
        start = max(0, end - limit)
        excerpt = source[start:end]
        if start > 0:
            excerpt = "…" + excerpt[1:]
        if end < len(source):
            excerpt = excerpt[:-1] + "…"
        return excerpt

    @staticmethod
    def _provenance(record: KnowledgeRecord) -> dict[str, str]:
        allowed = {"okf", "repository", "web", "operator", "other"}
        candidates: list[Any] = []
        if isinstance(record.sources, list):
            candidates.extend(record.sources)
        if isinstance(record.provenance, dict):
            candidates.append(record.provenance)
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            source_type = candidate.get("source_type", candidate.get("kind", "other"))
            handle = candidate.get("handle", candidate.get("uri"))
            if isinstance(handle, str) and 1 <= len(handle) <= 2048:
                return {
                    "source_type": (
                        source_type
                        if isinstance(source_type, str) and source_type in allowed
                        else "other"
                    ),
                    "handle": handle,
                }
        return {"source_type": "other", "handle": record.knowledge_ref}
