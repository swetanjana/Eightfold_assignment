"""
Merge engine — conflict resolution and provenance generation.

Takes a cluster of ``RawCandidateRecord`` objects (all describing the
same candidate) and produces one ``CanonicalProfile`` with a resolved
value, confidence score, and provenance record for every field.

Conflict Resolution Policy (documented and deterministic):
==========================================================

+------------------+------------------------------------------------+
| Field Type       | Strategy                                       |
+==================+================================================+
| Scalar fields    | Highest trust weight wins.  Ties broken by     |
| (name, title,    | completeness (longer non-null value).           |
| company,         |                                                |
| location)        |                                                |
+------------------+------------------------------------------------+
| Array fields     | Union + deduplicate after normalization.        |
| (emails, phones, |                                                |
| links)           |                                                |
+------------------+------------------------------------------------+
| Collection       | Union + deduplicate by compound key             |
| fields           | (company+title for experience,                  |
| (skills,         | institution+degree for education).              |
| experience,      |                                                |
| education)       |                                                |
+------------------+------------------------------------------------+
| Missing fields   | Left as None with confidence 0.0.              |
|                  | "Wrong-but-confident is worse than              |
|                  | honestly-empty."                                |
+------------------+------------------------------------------------+
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from schema.canonical import (
    CanonicalProfile,
    FieldValue,
    ProvenanceRecord,
    RawCandidateRecord,
)
from utils.constants import SOURCE_TRUST_WEIGHTS, SourceType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scalar fields (single-value, highest-trust-weight wins)
# ---------------------------------------------------------------------------

_SCALAR_FIELDS: list[str] = [
    "full_name",
    "current_company",
    "current_title",
    "location",
]

# ---------------------------------------------------------------------------
# Array fields (union + dedup)
# ---------------------------------------------------------------------------

_ARRAY_FIELDS: list[str] = [
    "emails",
    "phones",
    "links",
]

# ---------------------------------------------------------------------------
# Collection fields (union + dedup by compound key)
# ---------------------------------------------------------------------------

_COLLECTION_FIELDS: list[str] = [
    "skills",
    "experience",
    "education",
]


def merge_cluster(
    records: list[RawCandidateRecord],
) -> CanonicalProfile:
    """Merge a cluster of records into one canonical profile.

    Args:
        records: List of ``RawCandidateRecord`` objects, all
                 representing the same candidate.

    Returns:
        A ``CanonicalProfile`` with resolved values, confidence
        scores, and provenance records for every field.
    """
    if not records:
        return CanonicalProfile()

    # Sort records by trust weight (highest first) for deterministic
    # tie-breaking.
    sorted_records = sorted(
        records,
        key=lambda r: SOURCE_TRUST_WEIGHTS.get(r.source_type, 0.0),
        reverse=True,
    )

    profile = CanonicalProfile()

    # Track which sources contributed
    profile.sources_used = list(set(r.source_path for r in records))

    # --- Resolve scalar fields ---
    for field_name in _SCALAR_FIELDS:
        field_value = _resolve_scalar(field_name, sorted_records)
        setattr(profile, field_name, field_value)

    # --- Resolve array fields ---
    for field_name in _ARRAY_FIELDS:
        field_value = _resolve_array(field_name, sorted_records)
        setattr(profile, field_name, field_value)

    # --- Resolve collection fields ---
    profile.skills = _resolve_skills(sorted_records)
    profile.experience = _resolve_experience(sorted_records)
    profile.education = _resolve_education(sorted_records)

    return profile


# ---------------------------------------------------------------------------
# Scalar resolution
# ---------------------------------------------------------------------------


def _resolve_scalar(
    field_name: str,
    records: list[RawCandidateRecord],
) -> FieldValue:
    """Resolve a scalar field across multiple records.

    Strategy: pick the value from the highest-trust-weight source.
    If weights are tied, prefer the longer (more complete) value.
    """
    candidates: list[tuple[Any, RawCandidateRecord]] = []

    for record in records:
        value = getattr(record, field_name, None)
        if value is not None and (not isinstance(value, str) or value.strip()):
            candidates.append((value, record))

    if not candidates:
        # Field missing from all sources
        return FieldValue(
            value=None,
            confidence=0.0,
            provenance=[],
        )

    if len(candidates) == 1:
        # Single source — no conflict
        value, record = candidates[0]
        return FieldValue(
            value=value,
            confidence=SOURCE_TRUST_WEIGHTS.get(record.source_type, 0.5),
            provenance=[
                ProvenanceRecord(
                    field_name=field_name,
                    source_type=record.source_type,
                    source_path=record.source_path,
                    original_value=value,
                    method="direct",
                )
            ],
        )

    # Multiple sources — check for agreement
    normalized_values: dict[str, list[tuple[Any, RawCandidateRecord]]] = {}
    for value, record in candidates:
        norm_key = str(value).strip().lower()
        normalized_values.setdefault(norm_key, []).append((value, record))

    if len(normalized_values) == 1:
        # All sources agree
        value, record = candidates[0]
        # Use the value from the highest-trust source (list is pre-sorted)
        return FieldValue(
            value=value,
            confidence=min(
                SOURCE_TRUST_WEIGHTS.get(record.source_type, 0.5) + 0.05 * (len(candidates) - 1),
                1.0,
            ),
            provenance=[
                ProvenanceRecord(
                    field_name=field_name,
                    source_type=record.source_type,
                    source_path=record.source_path,
                    original_value=value,
                    method="agreement",
                )
            ],
        )

    # Sources disagree — highest trust weight wins
    # Records are pre-sorted by trust weight, so first candidate wins
    winner_value, winner_record = candidates[0]

    # If trust weights are equal among top candidates, prefer completeness
    top_weight = SOURCE_TRUST_WEIGHTS.get(winner_record.source_type, 0.0)
    tied_candidates = [
        (v, r) for v, r in candidates
        if SOURCE_TRUST_WEIGHTS.get(r.source_type, 0.0) == top_weight
    ]
    if len(tied_candidates) > 1:
        # Break tie by completeness (string length)
        winner_value, winner_record = max(
            tied_candidates,
            key=lambda x: len(str(x[0])),
        )

    logger.debug(
        "Conflict on '%s': chose '%s' from %s over %d other sources",
        field_name, winner_value, winner_record.source_type.value,
        len(candidates) - 1,
    )

    return FieldValue(
        value=winner_value,
        confidence=SOURCE_TRUST_WEIGHTS.get(winner_record.source_type, 0.5),
        provenance=[
            ProvenanceRecord(
                field_name=field_name,
                source_type=winner_record.source_type,
                source_path=winner_record.source_path,
                original_value=winner_value,
                method="trust_weight",
            )
        ],
    )


# ---------------------------------------------------------------------------
# Array resolution (union + dedup)
# ---------------------------------------------------------------------------


def _resolve_array(
    field_name: str,
    records: list[RawCandidateRecord],
) -> FieldValue:
    """Resolve an array field by unioning values from all sources."""
    all_values: list[Any] = []
    provenance_records: list[ProvenanceRecord] = []
    seen: set[str] = set()

    for record in records:
        values = getattr(record, field_name, []) or []
        source_contributed = False

        for val in values:
            norm_key = str(val).strip().lower()
            if norm_key:
                if norm_key not in seen:
                    seen.add(norm_key)
                    all_values.append(val)
                source_contributed = True

        if source_contributed:
            provenance_records.append(
                ProvenanceRecord(
                    field_name=field_name,
                    source_type=record.source_type,
                    source_path=record.source_path,
                    original_value=values,
                    method="union",
                )
            )

    if not all_values:
        return FieldValue(value=[], confidence=0.0, provenance=[])

    # Confidence: highest source weight + agreement bonus
    max_weight = max(
        (SOURCE_TRUST_WEIGHTS.get(r.source_type, 0.5) for r in provenance_records),
        default=0.0,
    )
    confidence = min(max_weight + 0.05 * (len(provenance_records) - 1), 1.0)

    return FieldValue(
        value=all_values,
        confidence=confidence,
        provenance=provenance_records,
    )


# ---------------------------------------------------------------------------
# Skills resolution
# ---------------------------------------------------------------------------


def _resolve_skills(
    records: list[RawCandidateRecord],
) -> FieldValue:
    """Union and deduplicate skills from all sources."""
    all_skills: list[str] = []
    provenance_records: list[ProvenanceRecord] = []
    seen: set[str] = set()

    for record in records:
        skills = record.skills or []
        source_contributed = False

        for skill in skills:
            norm_key = skill.strip().lower()
            if norm_key:
                if norm_key not in seen:
                    seen.add(norm_key)
                    all_skills.append(skill)
                source_contributed = True

        if source_contributed:
            provenance_records.append(
                ProvenanceRecord(
                    field_name="skills",
                    source_type=record.source_type,
                    source_path=record.source_path,
                    original_value=skills,
                    method="union",
                )
            )

    if not all_skills:
        return FieldValue(value=[], confidence=0.0, provenance=[])

    max_weight = max(
        (SOURCE_TRUST_WEIGHTS.get(p.source_type, 0.5) for p in provenance_records),
        default=0.0,
    )
    confidence = min(max_weight + 0.05 * (len(provenance_records) - 1), 1.0)

    return FieldValue(
        value=all_skills,
        confidence=confidence,
        provenance=provenance_records,
    )


# ---------------------------------------------------------------------------
# Experience resolution
# ---------------------------------------------------------------------------


def _experience_key(entry: dict[str, Any]) -> str:
    """Generate a deduplication key for an experience entry."""
    company = str(entry.get("company", "")).strip().lower()
    title = str(entry.get("title", "")).strip().lower()
    if not company and not title:
        return ""
    return f"{company}::{title}"


def _resolve_experience(
    records: list[RawCandidateRecord],
) -> FieldValue:
    """Union and deduplicate experience entries by company+title."""
    all_entries: list[dict[str, Any]] = []
    provenance_records: list[ProvenanceRecord] = []
    seen_keys: set[str] = set()

    for record in records:
        entries = record.experience or []
        source_contributed = False

        for entry in entries:
            key = _experience_key(entry)
            if key:
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_entries.append(entry)
                source_contributed = True

        if source_contributed:
            provenance_records.append(
                ProvenanceRecord(
                    field_name="experience",
                    source_type=record.source_type,
                    source_path=record.source_path,
                    original_value=entries,
                    method="union",
                )
            )

    if not all_entries:
        return FieldValue(value=[], confidence=0.0, provenance=[])

    max_weight = max(
        (SOURCE_TRUST_WEIGHTS.get(p.source_type, 0.5) for p in provenance_records),
        default=0.0,
    )
    confidence = min(max_weight + 0.05 * (len(provenance_records) - 1), 1.0)

    return FieldValue(
        value=all_entries,
        confidence=confidence,
        provenance=provenance_records,
    )


# ---------------------------------------------------------------------------
# Education resolution
# ---------------------------------------------------------------------------


def _education_key(entry: dict[str, Any]) -> str:
    """Generate a deduplication key for an education entry."""
    institution = str(entry.get("institution", "")).strip().lower()
    degree = str(entry.get("degree", "")).strip().lower()
    if not institution and not degree:
        return ""
    return f"{institution}::{degree}"


def _resolve_education(
    records: list[RawCandidateRecord],
) -> FieldValue:
    """Union and deduplicate education entries by institution+degree."""
    all_entries: list[dict[str, Any]] = []
    provenance_records: list[ProvenanceRecord] = []
    seen_keys: set[str] = set()

    for record in records:
        entries = record.education or []
        source_contributed = False

        for entry in entries:
            key = _education_key(entry)
            if key:
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_entries.append(entry)
                source_contributed = True

        if source_contributed:
            provenance_records.append(
                ProvenanceRecord(
                    field_name="education",
                    source_type=record.source_type,
                    source_path=record.source_path,
                    original_value=entries,
                    method="union",
                )
            )

    if not all_entries:
        return FieldValue(value=[], confidence=0.0, provenance=[])

    max_weight = max(
        (SOURCE_TRUST_WEIGHTS.get(p.source_type, 0.5) for p in provenance_records),
        default=0.0,
    )
    confidence = min(max_weight + 0.05 * (len(provenance_records) - 1), 1.0)

    return FieldValue(
        value=all_entries,
        confidence=confidence,
        provenance=provenance_records,
    )
