"""Eligibility-gated semantic candidate generation.

This is an internal expansion path.  It deliberately stops at scored,
traceable candidates and does not combine them with lexical results.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from agentknowledgevault.vault.models import KnowledgeRecord

from .eligibility import RetrievalEligibility
from .embeddings import (
    SEMANTIC_DOCUMENT_REPRESENTATION_VERSION,
    EmbeddingProviderIdentity,
    EmbeddingValidationError,
    validate_embedding_provider,
)
from .semantic_index import DerivedSemanticIndex, SemanticIndexSyncResult


@dataclass(frozen=True)
class SemanticCandidate:
    """A semantic hit with enough identity to be safely audited."""

    knowledge_ref: str
    semantic_score: float
    provider_id: str
    model_id: str
    embedding_dimension: int
    representation_version: str = SEMANTIC_DOCUMENT_REPRESENTATION_VERSION

    @property
    def score(self) -> float:
        """Convenient internal alias for consumers handling scored candidates."""
        return self.semantic_score

    @property
    def provider_identity(self) -> EmbeddingProviderIdentity:
        return EmbeddingProviderIdentity(
            self.provider_id, self.model_id, self.embedding_dimension
        )


@dataclass(frozen=True)
class SemanticCandidateResult:
    candidates: tuple[SemanticCandidate, ...]
    synchronization: SemanticIndexSyncResult


def utc_now() -> datetime:
    return datetime.now(UTC)


class SemanticCandidateService:
    """Synchronize and query semantic state behind the Level 0 hard gate."""

    def __init__(self, index: DerivedSemanticIndex) -> None:
        self.index = index
        self._eligibility = RetrievalEligibility()

    def generate(
        self,
        records: Iterable[KnowledgeRecord],
        query: str,
        scope: Sequence[str],
        now: datetime | None = None,
    ) -> SemanticCandidateResult:
        source = list(records)
        eligible, _ = self._eligibility.filter(source, scope, now or utc_now())
        # Ineligible records never reach semantic_document/embed_documents.
        synchronization = self.index.synchronize(eligible)
        try:
            hits = self.index.search(query, (r.knowledge_ref for r in eligible))
        except (
            sqlite3.DatabaseError,
            EmbeddingValidationError,
            RuntimeError,
            ValueError,
        ):
            # Synchronization and search are separate filesystem operations.  A
            # derived file may disappear, become corrupt, or change vector
            # space in between them.  Rebuild only from the already gated set,
            # then retry exactly once.
            synchronization = self.index.rebuild(eligible)
            hits = self.index.search(query, (r.knowledge_ref for r in eligible))
        identity = validate_embedding_provider(self.index.provider)
        candidates = tuple(
            SemanticCandidate(
                hit.knowledge_ref,
                hit.score,
                identity.provider_id,
                identity.model_id,
                identity.embedding_dimension,
            )
            for hit in hits
        )
        return SemanticCandidateResult(candidates, synchronization)

    # Explicit aliases keep the internal API easy to discover without creating
    # a caller-facing Level 1 orchestration surface.
    candidates = generate
    search = generate


SemanticCandidateGenerator = SemanticCandidateService
