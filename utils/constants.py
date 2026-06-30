"""
Pipeline-wide constants and enumerations.

This module is the single source of truth for values that are
referenced across multiple modules: source type identifiers,
trust weights, and default confidence values.  Centralizing
them here prevents duplication and ensures that a policy change
(e.g. increasing resume trust weight) requires editing exactly
one line.
"""

from __future__ import annotations

from enum import Enum


# ---------------------------------------------------------------------------
# Source type enumeration
# ---------------------------------------------------------------------------


class SourceType(str, Enum):
    """Identifies the category of a data source.

    Inherits from ``str`` so that enum values serialize cleanly to
    JSON (``"csv"`` instead of ``"SourceType.CSV"``).
    """

    CSV = "csv"
    ATS_JSON = "ats_json"
    RESUME_PDF = "resume_pdf"
    RECRUITER_NOTES = "recruiter_notes"


# ---------------------------------------------------------------------------
# Trust weights — used by the merge engine for conflict resolution
# ---------------------------------------------------------------------------

#: Default trust weights per source type.  Higher values mean the
#: source is considered more authoritative.
#:
#: Reasoning:
#:   ATS JSON (0.9)  — Data entered through a validated application
#:                      form by the candidate or HR.  Highest trust.
#:   CSV (0.8)       — Recruiter-curated export.  Generally reliable
#:                      but manually assembled, so slightly less trusted.
#:   Resume PDF (0.7) — Self-reported by the candidate.  Candidates
#:                      occasionally embellish or use inconsistent formats.
#:   Recruiter Notes (0.5) — Free-text observations.  Useful context but
#:                      prone to paraphrasing and interpretation errors.
SOURCE_TRUST_WEIGHTS: dict[SourceType, float] = {
    SourceType.CSV: 0.8,
    SourceType.ATS_JSON: 0.9,
    SourceType.RESUME_PDF: 0.7,
    SourceType.RECRUITER_NOTES: 0.5,
}


# ---------------------------------------------------------------------------
# File extension → source type mapping
# ---------------------------------------------------------------------------

#: Maps file extensions to source types for automatic detection.
EXTENSION_SOURCE_MAP: dict[str, SourceType] = {
    ".csv": SourceType.CSV,
    ".json": SourceType.ATS_JSON,
    ".pdf": SourceType.RESUME_PDF,
    ".txt": SourceType.RECRUITER_NOTES,
}


# ---------------------------------------------------------------------------
# Confidence defaults
# ---------------------------------------------------------------------------

#: Confidence assigned to a field that is entirely missing from all sources.
MISSING_FIELD_CONFIDENCE: float = 0.0

#: Maximum confidence a field can reach.
MAX_CONFIDENCE: float = 1.0

#: Bonus added per additional source that agrees on a field value.
AGREEMENT_BONUS: float = 0.05

#: Penalty applied when a value fails format validation after normalization.
FORMAT_FAILURE_PENALTY: float = 0.2

#: Weights for critical vs. non-critical fields when computing
#: overall profile confidence.  Critical fields (name, emails) are
#: weighted 2x because a profile without them is nearly useless.
FIELD_CRITICALITY: dict[str, float] = {
    "full_name": 2.0,
    "emails": 2.0,
    "phones": 1.5,
    "location": 1.0,
    "skills": 1.5,
    "experience": 1.0,
    "education": 1.0,
    "current_company": 1.0,
    "current_title": 1.0,
    "links": 0.5,
}
