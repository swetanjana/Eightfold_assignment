"""
Tests for the projection engine and output validator.

Covers:
    - Field selection and renaming.
    - Confidence and provenance inclusion per field.
    - on_missing policies: null, omit, error.
    - Output validation: format checks, confidence range.
"""

from __future__ import annotations

import pytest

from engine.projector import project, ProjectionError
from validators.output_validator import validate_output
from schema.canonical import (
    CanonicalProfile,
    FieldValue,
    ProvenanceRecord,
)
from schema.config import ProjectionConfig, FieldProjection
from utils.constants import SourceType


# ===================================================================
# Helpers
# ===================================================================


def _make_profile(**overrides) -> CanonicalProfile:
    """Create a CanonicalProfile with sensible defaults for testing."""
    profile = CanonicalProfile()
    profile.full_name = FieldValue(
        value="Alice Smith",
        confidence=0.9,
        provenance=[ProvenanceRecord(
            field_name="full_name",
            source_type=SourceType.ATS_JSON,
            source_path="ats.json",
            original_value="Alice Smith",
            method="direct",
        )],
    )
    profile.emails = FieldValue(
        value=["alice@test.com"],
        confidence=0.9,
        provenance=[ProvenanceRecord(
            field_name="emails",
            source_type=SourceType.ATS_JSON,
            source_path="ats.json",
            original_value=["alice@test.com"],
            method="direct",
        )],
    )
    profile.phones = FieldValue(
        value=["+15551234567"],
        confidence=0.8,
        provenance=[],
    )
    profile.skills = FieldValue(
        value=["Python", "Machine Learning"],
        confidence=0.85,
        provenance=[],
    )
    profile.current_company = FieldValue(
        value="Google",
        confidence=0.9,
        provenance=[],
    )
    profile.location = FieldValue(value="San Francisco, US", confidence=0.7, provenance=[])
    profile.overall_confidence = 0.85
    profile.sources_used = ["ats.json", "recruiter.csv"]

    for key, val in overrides.items():
        setattr(profile, key, val)

    return profile


def _make_config(
    fields: list[dict] | None = None,
    on_missing: str = "null",
    include_overall: bool = True,
    include_meta: bool = True,
) -> ProjectionConfig:
    """Create a ProjectionConfig from simple dicts."""
    if fields is None:
        fields = [
            {"source_field": "full_name", "output_field": "name"},
            {"source_field": "emails", "output_field": "emails"},
        ]
    return ProjectionConfig(
        fields=[FieldProjection(**f) for f in fields],
        on_missing=on_missing,
        include_overall_confidence=include_overall,
        include_metadata=include_meta,
    )


# ===================================================================
# Projection Tests
# ===================================================================


class TestProjection:
    """Tests for the projection engine."""

    def test_basic_field_selection_and_renaming(self) -> None:
        profile = _make_profile()
        config = _make_config(fields=[
            {"source_field": "full_name", "output_field": "candidate_name"},
            {"source_field": "skills", "output_field": "technical_skills"},
        ])

        output = project(profile, config)

        assert output["candidate_name"] == "Alice Smith"
        assert "Python" in output["technical_skills"]
        assert "full_name" not in output  # Renamed, not original key

    def test_include_confidence(self) -> None:
        profile = _make_profile()
        config = _make_config(fields=[
            {"source_field": "full_name", "output_field": "name", "include_confidence": True},
        ])

        output = project(profile, config)

        assert isinstance(output["name"], dict)
        assert output["name"]["value"] == "Alice Smith"
        assert output["name"]["confidence"] == 0.9

    def test_include_provenance(self) -> None:
        profile = _make_profile()
        config = _make_config(fields=[
            {"source_field": "emails", "output_field": "emails", "include_provenance": True},
        ])

        output = project(profile, config)

        assert isinstance(output["emails"], dict)
        assert "provenance" in output["emails"]
        assert len(output["emails"]["provenance"]) > 0

    def test_on_missing_null(self) -> None:
        profile = _make_profile()
        profile.links = FieldValue(value=None, confidence=0.0, provenance=[])

        config = _make_config(
            fields=[{"source_field": "links", "output_field": "links"}],
            on_missing="null",
        )

        output = project(profile, config)
        assert output["links"] is None

    def test_on_missing_omit(self) -> None:
        profile = _make_profile()
        profile.links = FieldValue(value=None, confidence=0.0, provenance=[])

        config = _make_config(
            fields=[
                {"source_field": "full_name", "output_field": "name"},
                {"source_field": "links", "output_field": "links"},
            ],
            on_missing="omit",
        )

        output = project(profile, config)
        assert "name" in output
        assert "links" not in output  # Omitted because missing

    def test_on_missing_error(self) -> None:
        profile = _make_profile()
        profile.links = FieldValue(value=None, confidence=0.0, provenance=[])

        config = _make_config(
            fields=[{"source_field": "links", "output_field": "links"}],
            on_missing="error",
        )

        with pytest.raises(ProjectionError):
            project(profile, config)

    def test_overall_confidence_included(self) -> None:
        profile = _make_profile()
        config = _make_config(include_overall=True)

        output = project(profile, config)
        assert "overall_confidence" in output

    def test_metadata_included(self) -> None:
        profile = _make_profile()
        config = _make_config(include_meta=True)

        output = project(profile, config)
        assert "_metadata" in output
        assert "profile_id" in output["_metadata"]
        assert "sources_used" in output["_metadata"]

    def test_metadata_excluded(self) -> None:
        profile = _make_profile()
        config = _make_config(include_meta=False)

        output = project(profile, config)
        assert "_metadata" not in output

    def test_same_profile_different_configs_different_output(self) -> None:
        """Core architectural proof: same data, different config → different shape."""
        profile = _make_profile()

        config_full = _make_config(fields=[
            {"source_field": "full_name", "output_field": "name"},
            {"source_field": "emails", "output_field": "emails"},
            {"source_field": "skills", "output_field": "skills"},
        ])
        config_minimal = _make_config(
            fields=[{"source_field": "full_name", "output_field": "candidate_name"}],
            include_overall=False,
            include_meta=False,
        )

        out_full = project(profile, config_full)
        out_minimal = project(profile, config_minimal)

        assert len(out_full) > len(out_minimal)
        assert "emails" in out_full
        assert "emails" not in out_minimal
        assert "candidate_name" in out_minimal
        assert "candidate_name" not in out_full


# ===================================================================
# Output Validation Tests
# ===================================================================


class TestOutputValidation:
    """Tests for the output validator."""

    def test_valid_output_passes(self) -> None:
        output = {
            "name": "Alice Smith",
            "emails": ["alice@test.com"],
            "phones": ["+15551234567"],
            "overall_confidence": 0.85,
        }
        result = validate_output(output)
        assert result.is_valid

    def test_invalid_phone_produces_warning(self) -> None:
        output = {
            "phones": ["not-a-phone"],
            "overall_confidence": 0.5,
        }
        result = validate_output(output)
        assert len(result.warnings) > 0
        assert any("E.164" in w.message for w in result.warnings)

    def test_invalid_email_produces_warning(self) -> None:
        output = {
            "emails": ["not-an-email"],
            "overall_confidence": 0.5,
        }
        result = validate_output(output)
        assert len(result.warnings) > 0

    def test_confidence_out_of_range_produces_warning(self) -> None:
        output = {"overall_confidence": 1.5}
        result = validate_output(output)
        assert len(result.warnings) > 0

    def test_confidence_wrong_type_produces_error(self) -> None:
        output = {"overall_confidence": "not_a_number"}
        result = validate_output(output)
        assert not result.is_valid
        assert len(result.errors) > 0
