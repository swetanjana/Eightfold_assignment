"""
Date normalization to YYYY-MM format.

The assignment requires all dates to be standardized to ``YYYY-MM``
format.  Raw dates arrive in many representations:

    - "January 2022", "Jan 2022"     (month name + year)
    - "01/2022", "12-2023", "06.2024" (numeric month/year)
    - "2022-01-15", "2022-01"         (ISO format)
    - "2022"                          (year only)
    - "Present", "Current"            (special tokens)

This module handles all of these deterministically using compiled
regex patterns and a month-name lookup table — no ``dateutil`` or
other heavy parsing libraries needed.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from utils.patterns import (
    ISO_DATE_PATTERN,
    MONTH_YEAR_PATTERN,
    NUMERIC_MONTH_YEAR_PATTERN,
    YEAR_ONLY_PATTERN,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Month name → number mapping
# ---------------------------------------------------------------------------

_MONTH_MAP: dict[str, str] = {
    "jan": "01", "january": "01",
    "feb": "02", "february": "02",
    "mar": "03", "march": "03",
    "apr": "04", "april": "04",
    "may": "05",
    "jun": "06", "june": "06",
    "jul": "07", "july": "07",
    "aug": "08", "august": "08",
    "sep": "09", "september": "09",
    "oct": "10", "october": "10",
    "nov": "11", "november": "11",
    "dec": "12", "december": "12",
}

#: Tokens that indicate "currently employed" — not a real date.
_PRESENT_TOKENS: set[str] = {"present", "current", "now", "ongoing"}


def normalize_date(raw: str | None) -> Optional[str]:
    """Normalize a raw date string to YYYY-MM format.

    Args:
        raw: The raw date string from any source.

    Returns:
        The date in ``"YYYY-MM"`` format, ``"Present"`` for current
        employment tokens, or ``None`` if the input could not be parsed.

    Examples:
        >>> normalize_date("January 2022")
        '2022-01'
        >>> normalize_date("Jan 2022")
        '2022-01'
        >>> normalize_date("01/2022")
        '2022-01'
        >>> normalize_date("2022-01-15")
        '2022-01'
        >>> normalize_date("2022-01")
        '2022-01'
        >>> normalize_date("2022")
        '2022'
        >>> normalize_date("Present")
        'Present'
        >>> normalize_date("garbage")
        None
        >>> normalize_date(None)
        None
    """
    if not raw or not isinstance(raw, str):
        return None

    cleaned = raw.strip()
    if not cleaned:
        return None

    # Check for "Present" / "Current" tokens
    if cleaned.lower() in _PRESENT_TOKENS:
        return "Present"

    # Try: "January 2022", "Jan 2022"
    match = MONTH_YEAR_PATTERN.search(cleaned)
    if match:
        month_str = match.group(1).lower().rstrip(".")
        year = match.group(2)
        month_num = _MONTH_MAP.get(month_str)
        if month_num:
            return f"{year}-{month_num}"

    # Try: "01/2022", "12-2023"
    match = NUMERIC_MONTH_YEAR_PATTERN.search(cleaned)
    if match:
        month = match.group(1).zfill(2)
        year = match.group(2)
        if 1 <= int(month) <= 12:
            return f"{year}-{month}"

    # Try: "2022-01-15", "2022-01"
    match = ISO_DATE_PATTERN.search(cleaned)
    if match:
        year = match.group(1)
        month = match.group(2)
        if 1 <= int(month) <= 12:
            return f"{year}-{month}"

    # Try: standalone "2022"
    match = YEAR_ONLY_PATTERN.search(cleaned)
    if match:
        return match.group(1)

    logger.debug("Failed to parse date: %r", raw)
    return None


def normalize_dates_in_experience(
    experience: list[dict],
) -> list[dict]:
    """Normalize start_date and end_date in a list of experience dicts.

    Modifies dicts in-place for efficiency.  If a date field is missing
    or unparseable, it is set to ``None``.

    Args:
        experience: List of experience dicts with optional ``start_date``
                    and ``end_date`` keys.

    Returns:
        The same list with dates normalized.
    """
    for entry in experience:
        if "start_date" in entry:
            entry["start_date"] = normalize_date(entry["start_date"])
        if "end_date" in entry:
            entry["end_date"] = normalize_date(entry["end_date"])
    return experience
