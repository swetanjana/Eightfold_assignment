"""
Confidence scoring engine.

Computes per-field and overall profile confidence scores for a
merged ``CanonicalProfile``.  Separated from the merger because
the confidence *formula* changes independently from the conflict
*policy*.

Scoring Model:
==============

+---------------------------+--------+---------------------------------------+
| Factor                    | Effect | Example                               |
+===========================+========+=======================================+
| Source baseline weight     | Start  | ATS: 0.9, CSV: 0.8, Resume: 0.7     |
+---------------------------+--------+---------------------------------------+
| Multi-source agreement    | +0.05  | 3 sources agree → +0.10              |
+---------------------------+--------+---------------------------------------+
| Format validation pass    | No Δ   | Phone matches E.164 → unchanged      |
+---------------------------+--------+---------------------------------------+
| Format validation fail    | −0.20  | Phone failed norm → 0.8 → 0.6       |
+---------------------------+--------+---------------------------------------+
| Field missing entirely    | = 0.0  | No email found → confidence 0.0      |
+---------------------------+--------+---------------------------------------+
| Overall profile           | Avg    | Weighted avg; critical fields 2x     |
+---------------------------+--------+---------------------------------------+
"""

from __future__ import annotations

import logging
import re

from schema.canonical import CanonicalProfile, FieldValue
from utils.constants import FIELD_CRITICALITY, MAX_CONFIDENCE

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Format validation patterns (for confidence adjustment)
# ---------------------------------------------------------------------------

_E164_PATTERN = re.compile(r"^\+\d{7,15}$")
_EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
_YYYY_MM_PATTERN = re.compile(r"^\d{4}-\d{2}$")


def score_profile(profile: CanonicalProfile) -> CanonicalProfile:
    """Compute per-field and overall confidence for a canonical profile.

    Adjusts the confidence scores that were initially set by the merger
    based on format validation checks.  Then computes the weighted
    overall profile confidence.

    Args:
        profile: A merged ``CanonicalProfile`` with initial confidence
                 scores from the merge engine.

    Returns:
        The same profile with updated confidence scores (mutated in place).
    """
    # --- Per-field format validation adjustments ---
    _validate_emails(profile.emails)
    _validate_phones(profile.phones)
    _validate_experience_dates(profile.experience)

    # --- Overall confidence computation ---
    field_scores: list[float] = []
    total_weight = 0.0

    for field_name, weight in FIELD_CRITICALITY.items():
        field_value: FieldValue = getattr(profile, field_name, None)
        
        # Check if the field is empty/missing
        is_empty = False
        if field_value is None or field_value.value is None:
            is_empty = True
        elif isinstance(field_value.value, (list, dict)) and not field_value.value:
            is_empty = True
        elif isinstance(field_value.value, str) and not field_value.value.strip():
            is_empty = True

        if is_empty:
            # Only penalize if it's a highly critical field (weight >= 2.0, e.g., name, emails)
            # Optional fields are simply excluded from the denominator.
            if weight >= 2.0:
                field_scores.append(0.0)
                total_weight += weight
        else:
            field_scores.append(field_value.confidence * weight)
            total_weight += weight

    if total_weight > 0:
        profile.overall_confidence = round(sum(field_scores) / total_weight, 4)
    else:
        profile.overall_confidence = 0.0

    logger.info(
        "Profile %s scored overall confidence: %.4f",
        profile.id[:8], profile.overall_confidence,
    )
    return profile


# ---------------------------------------------------------------------------
# Format validation helpers
# ---------------------------------------------------------------------------


def _validate_emails(field: FieldValue) -> None:
    """Adjust email confidence based on format validation."""
    if not field.value or not isinstance(field.value, list):
        return

    valid_count = sum(
        1 for email in field.value
        if isinstance(email, str) and _EMAIL_PATTERN.match(email)
    )
    total = len(field.value)

    if total > 0 and valid_count < total:
        # Some emails failed validation
        penalty = 0.1 * ((total - valid_count) / total)
        field.confidence = max(field.confidence - penalty, 0.0)
        field.confidence = round(field.confidence, 4)


def _validate_phones(field: FieldValue) -> None:
    """Adjust phone confidence based on E.164 format validation."""
    if not field.value or not isinstance(field.value, list):
        return

    valid_count = sum(
        1 for phone in field.value
        if isinstance(phone, str) and _E164_PATTERN.match(phone)
    )
    total = len(field.value)

    if total > 0 and valid_count < total:
        penalty = 0.2 * ((total - valid_count) / total)
        field.confidence = max(field.confidence - penalty, 0.0)
        field.confidence = round(field.confidence, 4)


def _validate_experience_dates(field: FieldValue) -> None:
    """Adjust experience confidence based on date format validation."""
    if not field.value or not isinstance(field.value, list):
        return

    total_dates = 0
    valid_dates = 0

    for entry in field.value:
        if not isinstance(entry, dict):
            continue
        for key in ("start_date", "end_date"):
            val = entry.get(key)
            if val and isinstance(val, str) and val != "Present":
                total_dates += 1
                if _YYYY_MM_PATTERN.match(val):
                    valid_dates += 1

    if total_dates > 0 and valid_dates < total_dates:
        penalty = 0.1 * ((total_dates - valid_dates) / total_dates)
        field.confidence = max(field.confidence - penalty, 0.0)
        field.confidence = round(field.confidence, 4)
