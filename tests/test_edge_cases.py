"""
Edge case tests — deliberate failures and graceful degradation.

These tests verify that the pipeline handles broken, missing, and
malformed data without crashing.  This is the "what if everything
goes wrong?" test suite.

The assignment explicitly values graceful degradation:
    "A missing or broken source must not crash the pipeline."
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from adapters.csv_adapter import CSVAdapter
from adapters.ats_adapter import ATSAdapter
from engine.merger import merge_cluster
from engine.confidence import score_profile
from engine.resolver import resolve_entities
from normalizers import normalize_record
from schema.canonical import RawCandidateRecord
from utils.constants import SourceType


# ===================================================================
# Malformed Input Tests
# ===================================================================


class TestMalformedCSV:
    """CSV adapter should never crash on bad input."""

    def test_empty_file(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.csv"
        path.write_text("", encoding="utf-8")
        records = CSVAdapter().extract(str(path))
        assert records == []

    def test_headers_only(self, tmp_path: Path) -> None:
        path = tmp_path / "headers_only.csv"
        path.write_text("name,email,phone\n", encoding="utf-8")
        records = CSVAdapter().extract(str(path))
        assert records == []

    def test_completely_empty_rows(self, tmp_path: Path) -> None:
        path = tmp_path / "blanks.csv"
        path.write_text("name,email\n,\n,\n,\n", encoding="utf-8")
        records = CSVAdapter().extract(str(path))
        assert records == []

    def test_extra_commas(self, tmp_path: Path) -> None:
        """Extra columns in rows shouldn't crash extraction."""
        path = tmp_path / "extra.csv"
        path.write_text("name,email\nAlice,alice@t.com,extra1,extra2\n", encoding="utf-8")
        records = CSVAdapter().extract(str(path))
        assert len(records) == 1
        assert records[0].full_name == "Alice"


class TestMalformedJSON:
    """ATS adapter should never crash on bad input."""

    def test_empty_file(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.json"
        path.write_text("", encoding="utf-8")
        records = ATSAdapter().extract(str(path))
        assert records == []

    def test_null_json(self, tmp_path: Path) -> None:
        path = tmp_path / "null.json"
        path.write_text("null", encoding="utf-8")
        records = ATSAdapter().extract(str(path))
        assert records == []

    def test_json_number(self, tmp_path: Path) -> None:
        path = tmp_path / "number.json"
        path.write_text("42", encoding="utf-8")
        records = ATSAdapter().extract(str(path))
        assert records == []

    def test_deeply_nested_missing_fields(self, tmp_path: Path) -> None:
        data = {"applicant_name": "Alice", "contact": None}
        path = tmp_path / "nested_none.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        records = ATSAdapter().extract(str(path))
        assert len(records) == 1
        assert records[0].emails == []


# ===================================================================
# Normalization Edge Cases
# ===================================================================


class TestNormalizationEdgeCases:
    """Normalizer should handle garbage input gracefully."""

    def test_record_with_all_empty_fields(self) -> None:
        record = RawCandidateRecord(
            source_type=SourceType.CSV,
            source_path="empty.csv",
        )
        normalized = normalize_record(record)
        assert normalized.emails == []
        assert normalized.phones == []
        assert normalized.skills == []

    def test_record_with_garbage_phone(self) -> None:
        record = RawCandidateRecord(
            source_type=SourceType.CSV,
            source_path="test.csv",
            phones=["not-a-phone", "abc", "12"],
        )
        normalized = normalize_record(record)
        # All garbage phones should be dropped
        assert normalized.phones == []

    def test_record_with_mixed_valid_invalid_skills(self) -> None:
        record = RawCandidateRecord(
            source_type=SourceType.CSV,
            source_path="test.csv",
            skills=["Python", "", "  ", "ML"],
        )
        normalized = normalize_record(record)
        assert "Python" in normalized.skills
        assert "Machine Learning" in normalized.skills
        assert "" not in normalized.skills


# ===================================================================
# Merge Edge Cases
# ===================================================================


class TestMergeEdgeCases:
    """Merger should handle degenerate clusters gracefully."""

    def test_merge_single_record_with_no_data(self) -> None:
        """A completely empty record should produce a profile with all None values."""
        record = RawCandidateRecord(
            source_type=SourceType.CSV,
            source_path="empty.csv",
        )
        profile = merge_cluster([record])
        assert profile.full_name.value is None
        assert profile.full_name.confidence == 0.0

    def test_merge_preserves_source_paths(self) -> None:
        r1 = RawCandidateRecord(
            source_type=SourceType.CSV,
            source_path="a.csv",
            full_name="Alice",
        )
        r2 = RawCandidateRecord(
            source_type=SourceType.ATS_JSON,
            source_path="b.json",
            full_name="Alice",
        )
        profile = merge_cluster([r1, r2])
        assert "a.csv" in profile.sources_used
        assert "b.json" in profile.sources_used


# ===================================================================
# Confidence Edge Cases
# ===================================================================


class TestConfidenceEdgeCases:
    """Confidence scorer should handle edge cases gracefully."""

    def test_all_fields_missing_gives_zero_confidence(self) -> None:
        record = RawCandidateRecord(
            source_type=SourceType.CSV,
            source_path="empty.csv",
        )
        profile = merge_cluster([record])
        scored = score_profile(profile)
        assert scored.overall_confidence == 0.0

    def test_confidence_never_exceeds_one(self) -> None:
        """Even with many agreeing sources, confidence caps at 1.0."""
        records = [
            RawCandidateRecord(
                source_type=SourceType.ATS_JSON,
                source_path=f"ats_{i}.json",
                full_name="Alice",
                emails=["alice@test.com"],
            )
            for i in range(10)
        ]
        profile = merge_cluster(records)
        scored = score_profile(profile)
        assert scored.overall_confidence <= 1.0
        assert scored.full_name.confidence <= 1.0


# ===================================================================
# Full Pipeline Integration (mini)
# ===================================================================


class TestMiniPipelineIntegration:
    """A small end-to-end integration test without files."""

    def test_csv_and_ats_records_merge_correctly(self) -> None:
        """Simulate what the pipeline does: extract, normalize, resolve, merge, score."""
        csv_record = RawCandidateRecord(
            source_type=SourceType.CSV,
            source_path="recruiter.csv",
            full_name="Alex Johnson",
            emails=["alex@gmail.com"],
            phones=["(555) 867-5309"],
            skills=["Python", "ML"],
            current_company="Google",
            current_title="Software Engineer",
            location="San Francisco US",
        )
        ats_record = RawCandidateRecord(
            source_type=SourceType.ATS_JSON,
            source_path="ats.json",
            full_name="Alexander Johnson",
            emails=["alex@gmail.com"],
            phones=["+15558675309"],
            skills=["Python", "Machine Learning", "TensorFlow"],
            current_company="Google",
            current_title="Senior Software Engineer",
            location="San Francisco, California",
            experience=[{
                "company": "Google",
                "title": "Software Engineer",
                "start_date": "Jan 2020",
                "end_date": "Present",
            }],
        )

        # Normalize
        csv_norm = normalize_record(csv_record)
        ats_norm = normalize_record(ats_record)

        # Resolve
        clusters = resolve_entities([csv_norm, ats_norm])
        assert len(clusters) == 1  # Same email → same person

        # Merge
        profile = merge_cluster(clusters[0])

        # ATS should win on name (higher trust weight)
        assert profile.full_name.value == "Alexander Johnson"

        # Skills should be unioned
        skills = profile.skills.value
        assert "Python" in skills
        assert "Machine Learning" in skills
        assert "TensorFlow" in skills

        # Experience should be present from ATS
        assert len(profile.experience.value) > 0

        # Score
        scored = score_profile(profile)
        assert scored.overall_confidence > 0.0
