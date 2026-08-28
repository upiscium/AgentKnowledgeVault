"""Embedding contracts and deterministic semantic document representation.

This module defines the provider boundary only.  It deliberately contains no
provider implementation, index, or similarity-search behavior.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from numbers import Real
from typing import Protocol, TypeAlias, cast

from agentknowledgevault.vault.json_codec import JsonValue, canonical_json
from agentknowledgevault.vault.models import KnowledgeRecord

EmbeddingVector: TypeAlias = Sequence[float]
SEMANTIC_DOCUMENT_REPRESENTATION_VERSION = "semantic-document-v1"


class EmbeddingProvider(Protocol):
    """An embedding service with separate document and query operations."""

    provider_id: str
    model_id: str
    embedding_dimension: int

    def embed_documents(self, texts: Sequence[str]) -> Sequence[EmbeddingVector]: ...

    def embed_query(self, text: str) -> EmbeddingVector: ...


class EmbeddingValidationError(ValueError):
    """Raised when provider identity or returned vectors are not usable."""


@dataclass(frozen=True)
class EmbeddingProviderIdentity:
    """Validated identity for a provider's vector space."""

    provider_id: str
    model_id: str
    embedding_dimension: int

    def __post_init__(self) -> None:
        validate_provider_identity(
            self.provider_id, self.model_id, self.embedding_dimension
        )


def validate_provider_identity(
    provider_id: str, model_id: str, embedding_dimension: int
) -> None:
    """Validate the identity advertised by an embedding provider."""
    if not isinstance(provider_id, str) or not provider_id.strip():
        raise EmbeddingValidationError("provider_id must be a non-empty string")
    if not isinstance(model_id, str) or not model_id.strip():
        raise EmbeddingValidationError("model_id must be a non-empty string")
    if (
        isinstance(embedding_dimension, bool)
        or not isinstance(embedding_dimension, int)
        or embedding_dimension <= 0
    ):
        raise EmbeddingValidationError("embedding_dimension must be a positive integer")


def validate_embedding_provider(
    provider: EmbeddingProvider,
) -> EmbeddingProviderIdentity:
    """Validate and snapshot a provider's advertised identity."""
    try:
        identity = EmbeddingProviderIdentity(
            provider.provider_id, provider.model_id, provider.embedding_dimension
        )
    except AttributeError as error:
        raise EmbeddingValidationError(
            "provider must advertise provider_id, model_id, and embedding_dimension"
        ) from error
    if not callable(getattr(provider, "embed_documents", None)) or not callable(
        getattr(provider, "embed_query", None)
    ):
        raise EmbeddingValidationError(
            "provider must implement embed_documents and embed_query"
        )
    return identity


def validate_embedding_vector(
    vector: EmbeddingVector, dimension: int, *, label: str = "embedding"
) -> tuple[float, ...]:
    """Return an immutable vector after validating shape and finite values."""
    if isinstance(vector, (str, bytes)):
        raise EmbeddingValidationError(f"{label} must be a sequence of numbers")
    if isinstance(dimension, bool) or not isinstance(dimension, int) or dimension <= 0:
        raise EmbeddingValidationError("dimension must be a positive integer")
    try:
        source_values = tuple(vector)
        values = tuple(
            float(value)
            for value in source_values
            if isinstance(value, Real) and not isinstance(value, bool)
        )
    except (TypeError, ValueError) as error:
        raise EmbeddingValidationError(f"{label} must contain only numbers") from error
    if len(values) != len(source_values):
        raise EmbeddingValidationError(f"{label} must contain only numbers")
    if len(values) != dimension:
        raise EmbeddingValidationError(
            f"{label} has dimension {len(values)}; expected {dimension}"
        )
    if not all(math.isfinite(value) for value in values):
        raise EmbeddingValidationError(f"{label} must contain only finite numbers")
    return values


def validate_embedding_vectors(
    vectors: Sequence[EmbeddingVector],
    dimension: int,
    *,
    expected_count: int | None = None,
) -> tuple[tuple[float, ...], ...]:
    """Validate vectors, optionally requiring one vector per input document."""
    try:
        if expected_count is not None and len(vectors) != expected_count:
            raise EmbeddingValidationError(
                f"embedding batch has {len(vectors)} vectors; expected {expected_count}"
            )
        return tuple(
            validate_embedding_vector(vector, dimension, label=f"embedding[{index}]")
            for index, vector in enumerate(vectors)
        )
    except TypeError as error:
        raise EmbeddingValidationError("embeddings must be a sequence") from error


def embed_documents(
    provider: EmbeddingProvider, texts: Sequence[str]
) -> tuple[tuple[float, ...], ...]:
    """Call a provider and enforce document batch cardinality and dimensions."""
    identity = validate_embedding_provider(provider)
    return validate_embedding_vectors(
        provider.embed_documents(texts),
        identity.embedding_dimension,
        expected_count=len(texts),
    )


def embed_query(provider: EmbeddingProvider, text: str) -> tuple[float, ...]:
    """Call a provider and validate the returned query vector."""
    identity = validate_embedding_provider(provider)
    return validate_embedding_vector(
        provider.embed_query(text),
        identity.embedding_dimension,
        label="query embedding",
    )


def semantic_document(record: KnowledgeRecord) -> str:
    """Build the versioned canonical JSON document sent to an embedder."""
    payload: dict[str, JsonValue] = {
        "body": record.body,
        "knowledge_path": record.knowledge_path,
        "namespace": record.namespace,
        "representation_version": SEMANTIC_DOCUMENT_REPRESENTATION_VERSION,
        "tags": cast(list[JsonValue], list(record.tags)),
        "title": record.title,
    }
    return canonical_json(payload)


# Compatibility names for callers of the original WU-12-04 surface.
embedding_document = semantic_document
semantic_document_representation = semantic_document
