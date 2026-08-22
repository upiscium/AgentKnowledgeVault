from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

ROOT = Path(__file__).parents[1]
SCHEMA_DIR = ROOT / "schemas"


def load_schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


REQUEST_SCHEMA = load_schema("retrieval-request.schema.json")
CAPSULE_SCHEMA = load_schema("context-capsule.schema.json")
REQUEST_VALIDATOR = Draft202012Validator(REQUEST_SCHEMA)
CAPSULE_VALIDATOR = Draft202012Validator(CAPSULE_SCHEMA)


def budgeted_projection(capsule: dict[str, Any]) -> bytes:
    projection = {
        "constraints": [item["statement"] for item in capsule["constraints"]],
        "context": capsule["context"],
        "critical_facts": [item["statement"] for item in capsule["critical_facts"]],
        "evidence": [item["excerpt"] for item in capsule["evidence"]],
        "pitfalls": [item["statement"] for item in capsule["pitfalls"]],
        "unresolved": [item["question"] for item in capsule["unresolved"]],
    }
    return json.dumps(
        projection, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


@pytest.fixture
def retrieval_request() -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "query": "How must a pending action be revalidated?",
        "task": {
            "summary": "Implement a safe effect-time check",
            "repository": "VillagerAgent",
            "languages": ["Python"],
            "topics": ["execution integrity"],
        },
        "scope": ["global", "project:VillagerAgent"],
        "mode": "auto",
        "budget": {"max_tokens": 800, "max_evidence_items": 5},
    }


@pytest.fixture
def capsule() -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "0.1",
        "status": "complete",
        "context": "Revalidate the retained exact action at effect time.",
        "critical_facts": [
            {
                "id": "fact-1",
                "statement": "Admission-time validity does not imply effect-time validity.",
                "confidence": "high",
                "knowledge_refs": ["knowledge-1"],
                "evidence_refs": ["evidence-1"],
            }
        ],
        "constraints": [],
        "pitfalls": [],
        "unresolved": [],
        "knowledge_refs": [
            {
                "id": "knowledge-1",
                "uri": "vault://global/effect-time-authority",
                "revision": "v1",
            }
        ],
        "evidence": [
            {
                "id": "evidence-1",
                "knowledge_ref": "knowledge-1",
                "excerpt": "Authority validation occurs immediately before native effect.",
                "provenance": {
                    "source_type": "repository",
                    "handle": "repo://VillagerAgent/docs/authority.md#effect-time",
                },
            }
        ],
        "retrieval": {
            "mode": "auto",
            "level": 1,
            "path": [0, 1],
            "terminal_reason": "sufficient",
        },
        "budget": {
            "requested_tokens": 800,
            "method": "utf8_bytes",
            "precision": "conservative",
            "used": 0,
            "hard_limit": 3200,
            "limit_unit": "utf8_bytes",
            "serialized_bytes": 0,
            "evidence_items": 1,
            "outcome": "within_budget",
        },
    }
    measured_bytes = len(budgeted_projection(result))
    result["budget"]["used"] = measured_bytes
    result["budget"]["serialized_bytes"] = measured_bytes
    return result


def validate_contract_pair(
    retrieval_request: dict[str, Any], capsule: dict[str, Any]
) -> None:
    REQUEST_VALIDATOR.validate(retrieval_request)
    CAPSULE_VALIDATOR.validate(capsule)

    assert capsule["retrieval"]["mode"] == retrieval_request["mode"]
    path = capsule["retrieval"]["path"]
    assert path[-1] == capsule["retrieval"]["level"]
    assert path == sorted(path) and len(path) == len(set(path))
    if retrieval_request["mode"] == "fast":
        assert path == [0]
    elif retrieval_request["mode"] == "auto":
        assert path[0] == 0

    budget = capsule["budget"]
    projection = budgeted_projection(capsule)
    assert budget["requested_tokens"] == retrieval_request["budget"]["max_tokens"]
    assert budget["used"] <= budget["hard_limit"]
    assert budget["serialized_bytes"] == len(projection)
    if budget["method"] == "exact_tokenizer":
        assert budget["hard_limit"] == budget["requested_tokens"]
        if budget["tokenizer_id"] == "test:unicode-codepoint-v1":
            assert budget["used"] == len(projection.decode("utf-8"))
    else:
        assert budget["hard_limit"] == 4 * budget["requested_tokens"]
        assert budget["used"] == budget["serialized_bytes"]

    assert budget["evidence_items"] == len(capsule["evidence"])
    assert len(capsule["evidence"]) <= retrieval_request["budget"]["max_evidence_items"]

    knowledge_ids = {item["id"] for item in capsule["knowledge_refs"]}
    evidence_ids = {item["id"] for item in capsule["evidence"]}
    assert len(knowledge_ids) == len(capsule["knowledge_refs"])
    assert len(evidence_ids) == len(capsule["evidence"])
    assert all(item["knowledge_ref"] in knowledge_ids for item in capsule["evidence"])

    claims = capsule["critical_facts"] + capsule["constraints"] + capsule["pitfalls"]
    for item in claims + capsule["unresolved"]:
        assert set(item["knowledge_refs"]) <= knowledge_ids
        assert set(item["evidence_refs"]) <= evidence_ids


def test_schemas_are_valid_draft_2020_12() -> None:
    Draft202012Validator.check_schema(REQUEST_SCHEMA)
    Draft202012Validator.check_schema(CAPSULE_SCHEMA)
    assert REQUEST_SCHEMA["$id"].endswith("/v0.1/retrieval-request.schema.json")
    assert CAPSULE_SCHEMA["$id"].endswith("/v0.1/context-capsule.schema.json")


def test_simple_query_does_not_require_task() -> None:
    REQUEST_VALIDATOR.validate(
        {
            "schema_version": "0.1",
            "query": "What constraints apply?",
            "mode": "fast",
            "budget": {"max_tokens": 200, "max_evidence_items": 2},
        }
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update({"mode": "unbounded"}),
        lambda value: value.update({"scope": ["sqlite:row:42"]}),
        lambda value: value["budget"].update({"max_tokens": 0}),
        lambda value: value["budget"].update({"max_evidence_items": -1}),
        lambda value: value.update({"raw_top_k": 100}),
        lambda value: value.pop("budget"),
    ],
)
def test_invalid_retrieval_requests_are_rejected(
    retrieval_request: dict[str, Any], mutation: Any
) -> None:
    mutation(retrieval_request)
    with pytest.raises(ValidationError):
        REQUEST_VALIDATOR.validate(retrieval_request)


def test_valid_request_and_capsule_pair(
    retrieval_request: dict[str, Any], capsule: dict[str, Any]
) -> None:
    validate_contract_pair(retrieval_request, capsule)


def test_raw_chunk_dump_is_not_a_capsule_field(capsule: dict[str, Any]) -> None:
    capsule["raw_chunks"] = ["unbounded source text"]
    with pytest.raises(ValidationError):
        CAPSULE_VALIDATOR.validate(capsule)


def test_storage_identity_cannot_replace_vault_uri(capsule: dict[str, Any]) -> None:
    capsule["knowledge_refs"][0]["uri"] = "sqlite://knowledge/42"
    with pytest.raises(ValidationError):
        CAPSULE_VALIDATOR.validate(capsule)


def test_claim_requires_traceability(capsule: dict[str, Any]) -> None:
    claim = capsule["critical_facts"][0]
    claim["knowledge_refs"] = []
    claim["evidence_refs"] = []
    with pytest.raises(ValidationError):
        CAPSULE_VALIDATOR.validate(capsule)


def test_conflict_requires_two_evidence_handles(capsule: dict[str, Any]) -> None:
    capsule["unresolved"] = [
        {
            "id": "question-1",
            "kind": "conflicting_evidence",
            "question": "Which constraint is current?",
            "knowledge_refs": ["knowledge-1"],
            "evidence_refs": ["evidence-1"],
        }
    ]
    with pytest.raises(ValidationError):
        CAPSULE_VALIDATOR.validate(capsule)


@pytest.mark.parametrize(
    ("field", "value"),
    [("used", 3201), ("hard_limit", 3199), ("evidence_items", 2)],
)
def test_cross_contract_budget_mismatch_is_rejected(
    retrieval_request: dict[str, Any],
    capsule: dict[str, Any],
    field: str,
    value: int,
) -> None:
    capsule["budget"][field] = value
    with pytest.raises(AssertionError):
        validate_contract_pair(retrieval_request, capsule)


def test_fast_mode_cannot_escalate(
    retrieval_request: dict[str, Any], capsule: dict[str, Any]
) -> None:
    retrieval_request["mode"] = "fast"
    capsule["retrieval"]["mode"] = "fast"
    with pytest.raises(ValidationError):
        validate_contract_pair(retrieval_request, capsule)


def test_auto_mode_cannot_skip_level_one(capsule: dict[str, Any]) -> None:
    capsule["retrieval"]["level"] = 2
    capsule["retrieval"]["path"] = [0, 2]
    with pytest.raises(ValidationError):
        CAPSULE_VALIDATOR.validate(capsule)


def test_fallback_usage_is_computed_from_budgeted_content(
    retrieval_request: dict[str, Any], capsule: dict[str, Any]
) -> None:
    capsule["context"] = "x" * 4000
    with pytest.raises(AssertionError):
        validate_contract_pair(retrieval_request, capsule)


def test_exact_test_tokenizer_usage_is_reproduced(
    retrieval_request: dict[str, Any], capsule: dict[str, Any]
) -> None:
    projection = budgeted_projection(capsule)
    capsule["budget"].update(
        {
            "method": "exact_tokenizer",
            "precision": "exact",
            "tokenizer_id": "test:unicode-codepoint-v1",
            "used": len(projection.decode("utf-8")),
            "hard_limit": retrieval_request["budget"]["max_tokens"],
            "limit_unit": "tokens",
            "serialized_bytes": len(projection),
        }
    )
    validate_contract_pair(retrieval_request, capsule)


def test_failed_capsule_has_no_synthesized_payload(capsule: dict[str, Any]) -> None:
    failed = copy.deepcopy(capsule)
    failed.update(
        {
            "status": "failed",
            "context": "",
            "critical_facts": [],
            "constraints": [],
            "pitfalls": [],
            "evidence": [],
            "unresolved": [
                {
                    "id": "failure-1",
                    "kind": "insufficient_evidence",
                    "question": "No truthful capsule fits the hard budget.",
                    "knowledge_refs": [],
                    "evidence_refs": [],
                }
            ],
        }
    )
    failed["budget"]["evidence_items"] = 0
    failed["budget"]["outcome"] = "failed"
    CAPSULE_VALIDATOR.validate(failed)


def test_schema_files_are_the_documented_ssot() -> None:
    for document in ("architecture.md", "retrieval-contract.md", "context-capsule.md"):
        text = (ROOT / "docs" / document).read_text(encoding="utf-8")
        assert "SSOT" in text or "single source of truth" in text
