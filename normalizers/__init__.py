"""
Normalizers package — stateless field standardization functions.

Each module contains pure functions that convert raw field values
into a single standard format.  They have no side effects, no
shared state, and are independently unit-testable.

The ``normalize_record`` function applies all normalizations to
a ``RawCandidateRecord``, preparing it for entity resolution
and merging.
"""

from __future__ import annotations

from schema.canonical import RawCandidateRecord
from normalizers.phone import normalize_phones
from normalizers.date import normalize_dates_in_experience
from normalizers.location import parse_location
from normalizers.skills import normalize_skills


def normalize_record(record: RawCandidateRecord) -> RawCandidateRecord:
    """Apply all normalizations to a raw candidate record.

    Normalizes fields in-place for efficiency:
        - Emails: lowercased and stripped.
        - Phones: converted to E.164 format (invalid ones dropped).
        - Skills: mapped to canonical names, deduplicated.
        - Location: parsed into structured form with ISO country code.
        - Experience dates: converted to YYYY-MM format.

    Args:
        record: A ``RawCandidateRecord`` from any adapter.

    Returns:
        The same record with normalized field values.
    """
    # Normalize emails (lowercase for consistent matching)
    record.emails = [
        e.strip().lower()
        for e in record.emails
        if e and e.strip()
    ]

    # Normalize phones to E.164
    record.phones = normalize_phones(record.phones)

    # Normalize skills to canonical forms
    record.skills = normalize_skills(record.skills)

    # Normalize location
    if record.location:
        parsed = parse_location(record.location)
        if parsed.country_code:
            parts: list[str] = []
            if parsed.city:
                parts.append(parsed.city)
            if parsed.region:
                parts.append(parsed.region)
            parts.append(parsed.country_code)
            record.location = ", ".join(parts)

    # Normalize experience dates
    if record.experience:
        normalize_dates_in_experience(record.experience)

    # Strip whitespace from name
    if record.full_name:
        record.full_name = record.full_name.strip()

    # Strip whitespace from company/title
    if record.current_company:
        record.current_company = record.current_company.strip()
    if record.current_title:
        record.current_title = record.current_title.strip()

    return record
