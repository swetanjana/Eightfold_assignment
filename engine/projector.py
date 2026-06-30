"""
Projection engine — config-driven output reshaping.

Takes a ``CanonicalProfile`` and a ``ProjectionConfig`` and produces
a plain dictionary that matches the shape the consumer requested.

This module is a pure function: ``project(profile, config) → dict``.
It does not validate the output — that is the validator's job.

The projection layer proves the core architectural point: the same
merge engine can produce different outputs from different configs,
without touching any pipeline code.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from schema.canonical import CanonicalProfile, FieldValue, ProvenanceRecord
from schema.config import ProjectionConfig

logger = logging.getLogger(__name__)


class ProjectionError(Exception):
    """Raised when a required field is missing and on_missing='error'."""

    def __init__(self, field_name: str, config_field: str) -> None:
        self.field_name = field_name
        self.config_field = config_field
        super().__init__(
            f"Required field '{config_field}' (from '{field_name}') "
            f"is missing from the canonical profile."
        )


def project(
    profile: CanonicalProfile,
    config: ProjectionConfig,
) -> dict[str, Any]:
    """Project a canonical profile into the output shape defined by config.

    Args:
        profile: A fully merged and scored ``CanonicalProfile``.
        config:  The runtime ``ProjectionConfig`` specifying which
                 fields to include, how to rename them, and what to
                 do with missing fields.

    Returns:
        A plain dictionary ready for JSON serialization.

    Raises:
        ProjectionError: If a requested field is missing and
                         ``config.on_missing`` is ``"error"``.
    """
    output: dict[str, Any] = {}

    for field_proj in config.fields:
        source_field = field_proj.source_field
        output_field = field_proj.output_field

        # Get the FieldValue from the profile
        field_value: FieldValue | None = getattr(profile, source_field, None)

        if field_value is None or _is_empty(field_value):
            # Field is missing from the profile
            if config.on_missing == "error":
                raise ProjectionError(source_field, output_field)
            elif config.on_missing == "omit":
                logger.debug(
                    "Omitting missing field '%s' (on_missing=omit)",
                    source_field,
                )
                continue
            else:
                # on_missing == "null"
                output[output_field] = None
                continue

        # Build the output value
        if field_proj.include_confidence or field_proj.include_provenance:
            # Rich output: value + metadata
            entry: dict[str, Any] = {"value": field_value.value}

            if field_proj.include_confidence:
                entry["confidence"] = field_value.confidence

            if field_proj.include_provenance:
                entry["provenance"] = [
                    _serialize_provenance(p) for p in field_value.provenance
                ]

            output[output_field] = entry
        else:
            # Flat output: just the value
            output[output_field] = field_value.value

    # --- Profile-level metadata ---
    if config.include_overall_confidence:
        output["overall_confidence"] = profile.overall_confidence

    if config.include_metadata:
        output["_metadata"] = {
            "profile_id": profile.id,
            "sources_used": profile.sources_used,
            "sources_failed": profile.sources_failed,
            "merge_timestamp": profile.merge_timestamp,
        }

    return output


def _is_empty(field_value: FieldValue) -> bool:
    """Check if a FieldValue is effectively empty."""
    if field_value.value is None:
        return True
    if isinstance(field_value.value, (list, dict)) and not field_value.value:
        return True
    if isinstance(field_value.value, str) and not field_value.value.strip():
        return True
    return False


def _serialize_provenance(record: ProvenanceRecord) -> dict[str, Any]:
    """Convert a ProvenanceRecord to a JSON-serializable dict."""
    return {
        "field": record.field_name,
        "source_type": record.source_type.value if hasattr(record.source_type, 'value') else str(record.source_type),
        "source_path": record.source_path,
        "original_value": _make_serializable(record.original_value),
        "method": record.method,
    }


def _make_serializable(value: Any) -> Any:
    """Ensure a value is JSON-serializable."""
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    if isinstance(value, (list, tuple)):
        return [_make_serializable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _make_serializable(v) for k, v in value.items()}
    return str(value)
