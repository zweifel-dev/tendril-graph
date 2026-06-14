"""Conformance test suite for ExtractorPlugin implementations (SPEC.md §4.4)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from tendril.plugins.base import ExtractorPlugin, ExtractionResult
from tendril.models.ir import FileEntry, RepoRef


class ConformanceExtractorPlugin(ABC):
    """Abstract conformance suite for extractors."""

    @abstractmethod
    def extractor(self) -> ExtractorPlugin: ...

    @abstractmethod
    def matching_repo_tree(self) -> list[FileEntry]: ...

    @abstractmethod
    def non_matching_repo_tree(self) -> list[FileEntry]: ...

    @abstractmethod
    def sample_repo(self) -> RepoRef: ...

    @abstractmethod
    def sample_ref(self) -> str: ...

    @abstractmethod
    def mock_read_file(self) -> object: ...

    def test_id_returns_string(self) -> None:
        eid = self.extractor().id()
        assert isinstance(eid, str)
        assert len(eid) > 0

    def test_matches_returns_true_for_matching(self) -> None:
        assert self.extractor().matches(self.matching_repo_tree()) is True

    def test_matches_returns_false_for_non_matching(self) -> None:
        assert self.extractor().matches(self.non_matching_repo_tree()) is False

    def test_extract_returns_extraction_result(self) -> None:
        result = self.extractor().extract(
            self.sample_repo(),
            self.sample_ref(),
            self.matching_repo_tree(),
            self.mock_read_file(),
        )
        assert isinstance(result, ExtractionResult)

    def test_extract_never_resolves(self) -> None:
        """Extractors locate and classify only — never resolve."""
        result = self.extractor().extract(
            self.sample_repo(),
            self.sample_ref(),
            self.matching_repo_tree(),
            self.mock_read_file(),
        )
        for ref in result.consumer_refs:
            assert ref.raw_value, "consumer ref must have a raw_value"
            assert ref.evidence, "consumer ref must have evidence"
