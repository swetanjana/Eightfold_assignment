"""
Phone number normalization to E.164 format.

E.164 is the international standard for phone number formatting:
    +[country code][subscriber number]
    Example: +15558675309

This module uses the ``phonenumbers`` library for robust parsing
rather than brittle hand-rolled regex.  The library handles:
    - Country code detection and insertion
    - Parentheses, dashes, spaces, and dots removal
    - National vs. international format conversion
    - Validation that the number is plausible

If the ``phonenumbers`` library cannot parse the input, the function
returns ``None`` rather than guessing — following the principle that
"wrong-but-confident is worse than honestly-empty."
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import phonenumbers

logger = logging.getLogger(__name__)

#: Default country code used when a phone number has no country prefix.
#: US is used as the default because the sample data is US-centric.
#: This is configurable per deployment.
DEFAULT_REGION: str = "US"


def normalize_phone(
    raw: str | None,
    default_region: str = DEFAULT_REGION,
) -> Optional[str]:
    """Normalize a raw phone string to E.164 format.

    Args:
        raw:             The raw phone number string from any source.
                         May contain parentheses, dashes, spaces, country
                         codes, or other formatting.
        default_region:  ISO 3166-1 alpha-2 country code to assume when
                         the number has no country prefix.

    Returns:
        The phone number in E.164 format (e.g. ``"+15558675309"``),
        or ``None`` if the input could not be parsed into a valid number.

    Examples:
        >>> normalize_phone("(555) 867-5309")
        '+15558675309'
        >>> normalize_phone("+91-98765-43210")
        '+919876543210'
        >>> normalize_phone("not-a-phone")
        None
        >>> normalize_phone("")
        None
        >>> normalize_phone(None)
        None
    """
    if not raw or not isinstance(raw, str):
        return None

    cleaned = raw.strip()
    if not cleaned:
        return None

    try:
        parsed = phonenumbers.parse(cleaned, default_region)
    except phonenumbers.NumberParseException:
        logger.debug("Failed to parse phone number: %r", raw)
        return None

    if not phonenumbers.is_possible_number(parsed):
        logger.debug("Phone number is not possible: %r", raw)
        return None

    return phonenumbers.format_number(
        parsed, phonenumbers.PhoneNumberFormat.E164
    )


def normalize_phones(
    raw_list: list[str],
    default_region: str = DEFAULT_REGION,
) -> list[str]:
    """Normalize a list of raw phone strings, dropping unparseable ones.

    Args:
        raw_list:        List of raw phone number strings.
        default_region:  Default country code for numbers without prefixes.

    Returns:
        Deduplicated list of phone numbers in E.164 format.
        Order is preserved (first occurrence kept).
    """
    seen: set[str] = set()
    result: list[str] = []

    for raw in raw_list:
        normalized = normalize_phone(raw, default_region)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)

    return result
