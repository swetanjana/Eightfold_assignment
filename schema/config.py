"""
Runtime projection configuration schema.

This module defines the Pydantic models that validate user-supplied
JSON configuration files.  Pydantic is used here — and *only* here —
because this is an external trust boundary: we must validate user
input strictly before the pipeline trusts it.

The projection config controls:
    - Which canonical fields appear in the output.
    - How they are renamed.
    - Whether confidence and provenance metadata are included.
    - What happens when a requested field is missing from the profile.

Example config (``default_config.json``):

    {
        "fields": [
            {"source_field": "full_name", "output_field": "name"},
            {"source_field": "emails",    "output_field": "emails",
             "include_confidence": true,  "include_provenance": true}
        ],
        "on_missing": "null",
        "include_overall_confidence": true,
        "include_metadata": true
    }
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FieldProjection(BaseModel):
    """Configuration for projecting a single canonical field.

    Attributes:
        source_field:        The field name on ``CanonicalProfile``
                             (e.g. ``"full_name"``, ``"skills"``).
        output_field:        The key name in the emitted JSON output.
                             Allows renaming fields for downstream consumers.
        include_confidence:  If ``True``, the field's confidence score
                             is attached alongside the value.
        include_provenance:  If ``True``, the field's provenance records
                             are attached alongside the value.
    """

    source_field: str
    output_field: str
    include_confidence: bool = False
    include_provenance: bool = False


class ProjectionConfig(BaseModel):
    """Top-level runtime configuration for output projection.

    Loaded from a user-supplied JSON file and validated by Pydantic
    before the pipeline uses it.  Invalid configs fail fast with
    clear error messages.

    Attributes:
        fields:                      List of field projections to include
                                     in the output.
        on_missing:                  Policy when a requested field is
                                     absent from the canonical profile:
                                     ``"null"``  — include as ``null``,
                                     ``"omit"``  — exclude from output,
                                     ``"error"`` — raise ValidationError.
        include_overall_confidence:  Whether to include the profile-level
                                     confidence score in the output.
        include_metadata:            Whether to include ``sources_used``,
                                     ``sources_failed``, and
                                     ``merge_timestamp`` in the output.
    """

    fields: list[FieldProjection] = Field(
        ...,
        min_length=1,
        description="At least one field must be projected.",
    )
    on_missing: Literal["null", "omit", "error"] = "null"
    include_overall_confidence: bool = True
    include_metadata: bool = True
