from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime

from test_semantic_index import FakeProvider, record

from agentknowledgevault.retrieval import (
    SemanticCandidateService,
)
from agentknowledgevault.retrieval.semantic_index import DerivedSemanticIndex
from agentknowledgevault.vault.models import KnowledgeStatus


def test_candidates_are_traceable_and_gate_all_ineligible_records(tmp_path) -> None:
    provider = FakeProvider()
    service = SemanticCandidateService(
        DerivedSemanticIndex(
            tmp_path / "semantic.db",
            provider,
            canonical_database_path=tmp_path / "vault.db",
        )
    )
    now = datetime(2026, 1, 1, tzinfo=UTC)
    eligible = record("vault://project/ok", "first")
    records = [
        eligible,
        replace(eligible, knowledge_ref="vault://other/no-scope"),
        replace(
            eligible,
            knowledge_ref="vault://project/deprecated",
            status=KnowledgeStatus.DEPRECATED,
        ),
        replace(
            eligible,
            knowledge_ref="vault://project/stale",
            stale_after="2025-01-01T00:00:00Z",
        ),
        replace(
            eligible,
            knowledge_ref="vault://project/malformed",
            stale_after="not-a-date",
        ),
        replace(
            eligible,
            knowledge_ref="vault://project/conditional",
            applies_when={"x": 1},
        ),
    ]
    result = service.generate(records, "query", ["project"], now)
    assert [candidate.knowledge_ref for candidate in result.candidates] == [
        eligible.knowledge_ref
    ]
    candidate = result.candidates[0]
    assert (candidate.semantic_score, candidate.provider_id, candidate.model_id) == (
        1.0,
        "test-provider",
        "test-model",
    )
    assert candidate.embedding_dimension == 2
    assert provider.document_calls == 1


def test_search_identity_mismatch_is_rebuilt_before_results_are_returned(
    tmp_path,
) -> None:
    provider = FakeProvider()
    index = DerivedSemanticIndex(
        tmp_path / "semantic.db",
        provider,
        canonical_database_path=tmp_path / "vault.db",
    )
    service = SemanticCandidateService(index)
    item = record("vault://project/item")
    service.generate([item], "query", ["project"])
    with sqlite3.connect(index.database_path) as connection:
        connection.execute(
            "UPDATE semantic_metadata SET value = 'wrong' WHERE key = 'model_id'"
        )
    result = service.generate([item], "query", ["project"])
    assert result.synchronization.rebuilt
    assert result.candidates[0].model_id == "test-model"
