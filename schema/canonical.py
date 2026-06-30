"""
Canonical schema definitions for the candidate data transformer.

These are internal domain models implemented as Python dataclasses.
They are lightweight, mutable, and carry no validation overhead —
validation is enforced only at external boundaries (config loading,
final output).

Classes:
    RawCandidateRecord  — The standard intermediate representation that
                          every adapter produces. One record per candidate
                          per source file.
    ProvenanceRecord    — Lineage metadata for a single resolved field value.
                          Tracks which source provided the value and how it
                          was selected.
    FieldValue          — A wrapper that pairs a resolved value with its
                          confidence score and provenance trail.
    CanonicalProfile    — The final merged profile for one candidate.
                          Every field is a FieldValue, making confidence
                          and provenance intrinsic to the data model rather
                          than an afterthought.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from utils.constants import SourceType


# ---------------------------------------------------------------------------
# Raw extraction output — one per candidate per source
# ---------------------------------------------------------------------------


@dataclass
class RawCandidateRecord:
    """Standard intermediate representation produced by every adapter.

    Each adapter reads its own source format (CSV rows, JSON blobs,
    PDF text) and maps it into this common shape.  Fields that the
    adapter cannot extract are left as ``None`` or empty lists — never
    invented.

    Attributes:
        source_type:     Enum identifying the source category.
        source_path:     File path or URL the record was extracted from.
        full_name:       Candidate's full name, if found.
        emails:          List of email addresses found in this source.
        phones:          List of phone numbers (raw, pre-normalization).
        location:        Free-text location string (e.g. "San Francisco, US").
        skills:          List of skill strings (raw, pre-canonicalization).
        experience:      List of experience dicts with keys like
                         ``company``, ``title``, ``start_date``, ``end_date``.
        education:       List of education dicts with keys like
                         ``institution``, ``degree``, ``year``.
        current_company: Current employer name, if identifiable.
        current_title:   Current job title, if identifiable.
        links:           URLs (portfolio, GitHub, LinkedIn, etc.).
        raw_metadata:    Adapter-specific extra fields that don't map to
                         the canonical schema but may be useful for
                         debugging or provenance.
    """

    source_type: SourceType
    source_path: str

    full_name: Optional[str] = None
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    location: Optional[str] = None
    skills: list[str] = field(default_factory=list)
    experience: list[dict[str, Any]] = field(default_factory=list)
    education: list[dict[str, Any]] = field(default_factory=list)
    current_company: Optional[str] = None
    current_title: Optional[str] = None
    links: list[str] = field(default_factory=list)
    raw_metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Provenance — lineage tracking for every resolved field
# ---------------------------------------------------------------------------


@dataclass
class ProvenanceRecord:
    """Tracks the lineage of a single resolved field value.

    Every value in the canonical profile carries a provenance record
    so that downstream consumers (or debugging engineers) can trace
    any value back to its origin.

    Attributes:
        field_name:      The canonical field this record describes.
        source_type:     Which source category provided the value.
        source_path:     The specific file or URL.
        original_value:  The raw value before normalization.
        method:          How the value was selected during merge.
                         Examples: ``"direct"`` (single source, no conflict),
                         ``"trust_weight"`` (highest-weight source won),
                         ``"agreement"`` (multiple sources agreed),
                         ``"union"`` (array fields merged).
    """

    field_name: str
    source_type: SourceType
    source_path: str
    original_value: Any
    method: str


# ---------------------------------------------------------------------------
# FieldValue — value + confidence + provenance wrapper
# ---------------------------------------------------------------------------


@dataclass
class FieldValue:
    """Wraps a resolved field value with its confidence and provenance.

    This is the core design decision of the schema: every field on
    ``CanonicalProfile`` is a ``FieldValue``, not a bare value.  This
    makes confidence and provenance intrinsic to the data model rather
    than requiring a separate lookup table.

    Attributes:
        value:       The resolved, normalized value.  ``None`` when the
                     field could not be determined from any source.
        confidence:  Float in ``[0.0, 1.0]``.  ``0.0`` means the field
                     is missing or untrusted.  ``1.0`` means high
                     certainty (e.g. multiple sources agree on a
                     format-validated value).
        provenance:  One or more provenance records.  Scalar fields
                     typically have one record (the winning source).
                     Array fields have one record per contributing source.
    """

    value: Any = None
    confidence: float = 0.0
    provenance: list[ProvenanceRecord] = field(default_factory=list)


# ---------------------------------------------------------------------------
# CanonicalProfile — the single source of truth for one candidate
# ---------------------------------------------------------------------------


def _generate_profile_id() -> str:
    """Generate a unique profile identifier."""
    return str(uuid.uuid4())


def _current_timestamp() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CanonicalProfile:
    """The canonical, merged profile for a single candidate.

    Produced by the merge engine after entity resolution groups raw
    records and conflict resolution picks the best value per field.
    Every field is a ``FieldValue`` carrying its own confidence score
    and provenance trail.

    Attributes:
        id:                   Unique profile identifier (UUID).
        full_name:            Resolved candidate name.
        emails:               Resolved list of email addresses.
        phones:               Resolved list of phone numbers (E.164).
        location:             Resolved location (ISO country code).
        skills:               Resolved list of canonical skill names.
        experience:           Resolved list of experience entries.
        education:            Resolved list of education entries.
        current_company:      Resolved current employer.
        current_title:        Resolved current job title.
        links:                Resolved list of profile/portfolio URLs.
        overall_confidence:   Weighted average of field confidences.
        sources_used:         Paths of sources that contributed data.
        sources_failed:       Paths of sources that failed to parse.
        merge_timestamp:      ISO-8601 timestamp of when this profile
                              was created.
    """

    # Identity
    id: str = field(default_factory=_generate_profile_id)

    # Candidate fields — every one is a FieldValue
    full_name: FieldValue = field(default_factory=FieldValue)
    emails: FieldValue = field(default_factory=FieldValue)
    phones: FieldValue = field(default_factory=FieldValue)
    location: FieldValue = field(default_factory=FieldValue)
    skills: FieldValue = field(default_factory=FieldValue)
    experience: FieldValue = field(default_factory=FieldValue)
    education: FieldValue = field(default_factory=FieldValue)
    current_company: FieldValue = field(default_factory=FieldValue)
    current_title: FieldValue = field(default_factory=FieldValue)
    links: FieldValue = field(default_factory=FieldValue)

    # Profile-level metadata
    overall_confidence: float = 0.0
    sources_used: list[str] = field(default_factory=list)
    sources_failed: list[str] = field(default_factory=list)
    merge_timestamp: str = field(default_factory=_current_timestamp)
