"""
Tests for the merge engine, entity resolver, and confidence scorer.

Covers:
    - Entity resolution: records with shared emails are grouped together.
    - Conflict resolution: highest-trust source wins for scalar fields.
    - Array merging: union + dedup for emails, phones, skills.
    - Provenance: every field tracks its source and resolution method.
    - Confidence scoring: format validation adjustments, overall score.
    - Edge cases: single record, empty cluster, all fields missing.
"""

from __future__ import annotations

import pytest

from engine.merger import merge_cluster
from engine.resolver import resolve_entities
from engine.confidence import score_profile
from schema.canonical import RawCandidateRecord, CanonicalProfile
from utils.constants import SourceType


# ===================================================================
# Helper factories
# ===================================================================


def _make_record(
    source_type: SourceType = SourceType.CSV,
    source_path: str = "test.csv",
    **kwargs,
) -> RawCandidateRecord:
    """Create a RawCandidateRecord with defaults for testing."""
    defaults = {
        "source_type": source_type,
        "source_path": source_path,
        "full_name": None,
        "emails": [],
        "phones": [],
        "location": None,
        "skills": [],
        "experience": [],
        "education": [],
        "current_company": None,
        "current_title": None,
        "links": [],
        "raw_metadata": {},
    }
    defaults.update(kwargs)
    return RawCandidateRecord(**defaults)


# ===================================================================
# Entity Resolution Tests
# ===================================================================


class TestEntityResolution:
    """Tests for ``resolve_entities``."""

    def test_groups_records_by_shared_email(self) -> None:
        r1 = _make_record(emails=["alice@test.com"])
        r2 = _make_record(
            source_type=SourceType.ATS_JSON,
            source_path="test.json",
            emails=["alice@test.com"],
        )
        r3 = _make_record(emails=["bob@test.com"])

        clusters = resolve_entities([r1, r2, r3])
        assert len(clusters) == 2

        # Find the cluster with Alice
        alice_cluster = [c for c in clusters if any("alice" in e for r in c for e in r.emails)]
        assert len(alice_cluster) == 1
        assert len(alice_cluster[0]) == 2

    def test_groups_records_by_shared_phone(self) -> None:
        r1 = _make_record(phones=["+15551234567"])
        r2 = _make_record(
            source_type=SourceType.ATS_JSON,
            source_path="test.json",
            phones=["+15551234567"],
        )

        clusters = resolve_entities([r1, r2])
        assert len(clusters) == 1
        assert len(clusters[0]) == 2

    def test_transitive_matching(self) -> None:
        """A shares email with B, B shares phone with C → all in one cluster."""
        r1 = _make_record(emails=["shared@test.com"])
        r2 = _make_record(
            source_type=SourceType.ATS_JSON,
            source_path="test.json",
            emails=["shared@test.com"],
            phones=["+15559999999"],
        )
        r3 = _make_record(
            source_type=SourceType.RESUME_PDF,
            source_path="resume.pdf",
            phones=["+15559999999"],
        )

        clusters = resolve_entities([r1, r2, r3])
        assert len(clusters) == 1
        assert len(clusters[0]) == 3

    def test_no_matching_keys_are_singletons(self) -> None:
        r1 = _make_record(emails=["a@test.com"])
        r2 = _make_record(emails=["b@test.com"])
        r3 = _make_record(emails=["c@test.com"])

        clusters = resolve_entities([r1, r2, r3])
        assert len(clusters) == 3

    def test_empty_input(self) -> None:
        assert resolve_entities([]) == []


# ===================================================================
# Merge Engine Tests
# ===================================================================


class TestMergeCluster:
    """Tests for ``merge_cluster``."""

    def test_single_record_uses_direct_method(self) -> None:
        r = _make_record(
            source_type=SourceType.ATS_JSON,
            full_name="Alice Smith",
            emails=["alice@test.com"],
        )
        profile = merge_cluster([r])

        assert profile.full_name.value == "Alice Smith"
        assert profile.full_name.provenance[0].method == "direct"

    def test_ats_beats_csv_on_scalar_conflict(self) -> None:
        """ATS (trust 0.9) should win over CSV (trust 0.8) for scalar fields."""
        csv_record = _make_record(
            source_type=SourceType.CSV,
            source_path="recruiter.csv",
            full_name="Alex Johnson",
            current_title="Software Engineer",
        )
        ats_record = _make_record(
            source_type=SourceType.ATS_JSON,
            source_path="ats.json",
            full_name="Alexander Johnson",
            current_title="Senior Software Engineer",
        )

        profile = merge_cluster([csv_record, ats_record])

        # ATS should win because trust weight 0.9 > 0.8
        assert profile.full_name.value == "Alexander Johnson"
        assert profile.full_name.provenance[0].method == "trust_weight"
        assert profile.full_name.provenance[0].source_type == SourceType.ATS_JSON

    def test_agreement_boosts_confidence(self) -> None:
        """When multiple sources agree, confidence should be boosted."""
        r1 = _make_record(
            source_type=SourceType.CSV,
            full_name="Alice Smith",
        )
        r2 = _make_record(
            source_type=SourceType.ATS_JSON,
            source_path="ats.json",
            full_name="Alice Smith",
        )

        profile = merge_cluster([r1, r2])

        assert profile.full_name.value == "Alice Smith"
        assert profile.full_name.provenance[0].method == "agreement"
        # ATS base weight (0.9) + agreement bonus (0.05)
        assert profile.full_name.confidence >= 0.9

    def test_array_fields_are_unioned(self) -> None:
        r1 = _make_record(emails=["alice@gmail.com"])
        r2 = _make_record(
            source_type=SourceType.ATS_JSON,
            source_path="ats.json",
            emails=["alice.smith@company.com"],
        )

        profile = merge_cluster([r1, r2])

        assert len(profile.emails.value) == 2
        assert "alice@gmail.com" in profile.emails.value
        assert "alice.smith@company.com" in profile.emails.value

    def test_array_fields_are_deduplicated(self) -> None:
        r1 = _make_record(emails=["alice@gmail.com"])
        r2 = _make_record(
            source_type=SourceType.ATS_JSON,
            source_path="ats.json",
            emails=["alice@gmail.com"],
        )

        profile = merge_cluster([r1, r2])

        assert len(profile.emails.value) == 1

    def test_skills_unioned_from_multiple_sources(self) -> None:
        r1 = _make_record(skills=["Python", "ML"])
        r2 = _make_record(
            source_type=SourceType.ATS_JSON,
            source_path="ats.json",
            skills=["Python", "TensorFlow"],
        )

        profile = merge_cluster([r1, r2])

        assert "Python" in profile.skills.value
        assert "ML" in profile.skills.value
        assert "TensorFlow" in profile.skills.value
        # Python should appear only once (dedup)
        assert profile.skills.value.count("Python") == 1

    def test_experience_deduped_by_company_title(self) -> None:
        r1 = _make_record(
            experience=[{"company": "Google", "title": "Engineer", "start_date": "2020", "end_date": "2023"}]
        )
        r2 = _make_record(
            source_type=SourceType.ATS_JSON,
            source_path="ats.json",
            experience=[{"company": "Google", "title": "Engineer", "start_date": "Jan 2020", "end_date": "Present"}],
        )

        profile = merge_cluster([r1, r2])

        # Same company+title → should be deduped to 1 entry
        assert len(profile.experience.value) == 1

    def test_missing_field_gets_zero_confidence(self) -> None:
        r = _make_record(full_name="Alice")  # no location

        profile = merge_cluster([r])

        assert profile.location.value is None
        assert profile.location.confidence == 0.0

    def test_empty_cluster_returns_empty_profile(self) -> None:
        profile = merge_cluster([])

        assert profile.full_name.value is None
        assert profile.overall_confidence == 0.0


# ===================================================================
# Confidence Scoring Tests
# ===================================================================


class TestConfidenceScoring:
    """Tests for ``score_profile``."""

    def test_overall_confidence_computed(self) -> None:
        r = _make_record(
            source_type=SourceType.ATS_JSON,
            full_name="Alice Smith",
            emails=["alice@test.com"],
            phones=["+15551234567"],
            skills=["Python"],
        )
        profile = merge_cluster([r])
        scored = score_profile(profile)

        assert scored.overall_confidence > 0.0
        assert scored.overall_confidence <= 1.0

    def test_missing_critical_fields_lower_confidence(self) -> None:
        """A profile missing name and email should have lower overall confidence."""
        full_record = _make_record(
            source_type=SourceType.ATS_JSON,
            full_name="Alice",
            emails=["alice@test.com"],
            phones=["+15551234567"],
            skills=["Python"],
            location="US",
        )
        sparse_record = _make_record(
            source_type=SourceType.ATS_JSON,
            source_path="sparse.json",
            skills=["Python"],
        )

        full_profile = score_profile(merge_cluster([full_record]))
        sparse_profile = score_profile(merge_cluster([sparse_record]))

        assert full_profile.overall_confidence > sparse_profile.overall_confidence
