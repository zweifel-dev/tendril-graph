"""LLM provider conformance tests — fixture-based, no live LLM calls (T022).

Validates that each prompt contract can:
  1. build a prompt from a synthetic LLMJudgeItem
  2. validate a canned correct response without error
  3. raise MalformedResponseError for a malformed response
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tendril.llm.contracts.ambiguous_match import AmbiguousMatchContract
from tendril.llm.contracts.base import MalformedResponseError
from tendril.llm.contracts.identity_class import IdentityClassContract
from tendril.llm.contracts.unresolved_ref import UnresolvedRefContract

FIXTURE_PATH = Path(__file__).parent.parent.parent / "fixtures" / "conformance" / "llm" / "complete_responses.json"


def _load_fixtures() -> dict:
    return json.loads(FIXTURE_PATH.read_bytes())


def _synthetic_item(decision_type: str) -> dict:
    return {
        "consumer_ref_id": "SIDECAR_URL",
        "decision_type": decision_type,
        "from_id": "github:myorg/anchor-repo",
        "env": "prod",
        "evidence": [
            {"source_type": "cicd", "locator": "github_actions:anchor-repo:SIDECAR_URL",
             "key": "SIDECAR_URL", "value": "https://sidecar.internal", "is_secret": False},
        ],
        "candidates": ["github:myorg/sidecar-service"],
        "raw_value": "https://sidecar.internal",
    }


class TestAmbiguousMatchContract:
    def setup_method(self) -> None:
        self.contract = AmbiguousMatchContract()
        self.fixtures = _load_fixtures()

    def test_build_prompt_returns_llm_request(self) -> None:
        item = _synthetic_item("AMBIGUOUS_MATCH")
        req = self.contract.build_prompt(item)
        assert req.goal.startswith("AMBIGUOUS_MATCH:")
        assert req.evidence is not None

    def test_validate_response_accepts_valid_fixture(self) -> None:
        raw = self.fixtures["ambiguous_match/v1"]
        resp = self.contract.validate_response(raw)
        assert resp.decision == "ground-to-candidate"
        assert resp.candidate_id == "github:myorg/sidecar-service"
        assert resp.reasoning

    def test_validate_response_raises_on_missing_reasoning(self) -> None:
        raw = dict(self.fixtures["_malformed_missing_reasoning"])
        with pytest.raises(MalformedResponseError):
            self.contract.validate_response(raw)

    def test_validate_response_raises_on_bad_decision(self) -> None:
        raw = {"decision": "do-nothing", "reasoning": "test"}
        with pytest.raises(MalformedResponseError):
            self.contract.validate_response(raw)

    def test_validate_response_raises_when_candidate_id_missing_for_ground(self) -> None:
        raw = {"decision": "ground-to-candidate", "reasoning": "pick this one"}
        with pytest.raises(MalformedResponseError):
            self.contract.validate_response(raw)


class TestUnresolvedRefContract:
    def setup_method(self) -> None:
        self.contract = UnresolvedRefContract()
        self.fixtures = _load_fixtures()

    def test_build_prompt_returns_llm_request(self) -> None:
        item = _synthetic_item("UNRESOLVED_REF")
        req = self.contract.build_prompt(item)
        assert req.goal.startswith("UNRESOLVED_REF:")

    def test_validate_response_accepts_valid_fixture(self) -> None:
        raw = self.fixtures["unresolved_ref/v1"]
        resp = self.contract.validate_response(raw)
        assert resp.proposed_value == "https://sidecar.internal"
        assert resp.reasoning

    def test_validate_response_accepts_null_proposed_value(self) -> None:
        raw = {"proposed_value": None, "reasoning": "This reference cannot be resolved."}
        resp = self.contract.validate_response(raw)
        assert resp.proposed_value is None

    def test_validate_response_raises_on_missing_proposed_value_key(self) -> None:
        raw = {"reasoning": "some reason"}
        with pytest.raises(MalformedResponseError):
            self.contract.validate_response(raw)

    def test_validate_response_raises_on_empty_proposed_value(self) -> None:
        raw = {"proposed_value": "", "reasoning": "oops"}
        with pytest.raises(MalformedResponseError):
            self.contract.validate_response(raw)

    def test_validate_response_raises_on_missing_reasoning(self) -> None:
        raw = {"proposed_value": "https://example.com", "reasoning": ""}
        with pytest.raises(MalformedResponseError):
            self.contract.validate_response(raw)


class TestIdentityClassContract:
    def setup_method(self) -> None:
        self.contract = IdentityClassContract()
        self.fixtures = _load_fixtures()

    def test_build_prompt_returns_llm_request(self) -> None:
        item = _synthetic_item("IDENTITY_CLASS")
        req = self.contract.build_prompt(item)
        assert req.goal.startswith("IDENTITY_CLASS:")

    def test_validate_response_accepts_valid_fixture(self) -> None:
        raw = self.fixtures["identity_class/v1"]
        resp = self.contract.validate_response(raw)
        assert resp.class_ == "url"
        assert resp.reasoning

    def test_validate_response_raises_on_invalid_class(self) -> None:
        raw = {"class": "database", "reasoning": "It is a database"}
        with pytest.raises(MalformedResponseError):
            self.contract.validate_response(raw)

    def test_validate_response_raises_on_missing_reasoning(self) -> None:
        raw = {"class": "url", "reasoning": ""}
        with pytest.raises(MalformedResponseError):
            self.contract.validate_response(raw)
