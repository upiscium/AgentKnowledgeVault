"""Deterministic Level 0 retrieval public API."""

from .budget import ExactTokenCounter, accounting_payload
from .eligibility import EligibilityCounts, EligibilityResult, RetrievalEligibility
from .embeddings import (
    SEMANTIC_DOCUMENT_REPRESENTATION_VERSION,
    EmbeddingProvider,
    EmbeddingProviderIdentity,
    EmbeddingValidationError,
    embed_documents,
    embed_query,
    embedding_document,
    semantic_document,
    semantic_document_representation,
    validate_embedding_provider,
    validate_embedding_vector,
    validate_embedding_vectors,
    validate_provider_identity,
)
from .fake_embeddings import DeterministicEmbeddingProvider
from .models import RetrievalDiagnostics, RetrievalResult
from .semantic_candidates import (
    SemanticCandidate,
    SemanticCandidateGenerator,
    SemanticCandidateResult,
    SemanticCandidateService,
)
from .service import Level0RetrievalService

__all__ = [
    "SEMANTIC_DOCUMENT_REPRESENTATION_VERSION",
    "DeterministicEmbeddingProvider",
    "EligibilityCounts",
    "EligibilityResult",
    "EmbeddingProvider",
    "EmbeddingProviderIdentity",
    "EmbeddingValidationError",
    "ExactTokenCounter",
    "Level0RetrievalService",
    "RetrievalDiagnostics",
    "RetrievalEligibility",
    "RetrievalResult",
    "SemanticCandidate",
    "SemanticCandidateGenerator",
    "SemanticCandidateResult",
    "SemanticCandidateService",
    "accounting_payload",
    "embed_documents",
    "embed_query",
    "embedding_document",
    "semantic_document",
    "semantic_document_representation",
    "validate_embedding_provider",
    "validate_embedding_vector",
    "validate_embedding_vectors",
    "validate_provider_identity",
]
