"""
Location normalization to ISO 3166-1 alpha-2 country codes.

Raw location data arrives in many formats:
    - "United States", "USA", "US", "America"
    - "Bangalore, India"
    - "San Francisco, California"
    - "New York, NY, US"
    - "London, UK"

This module provides:
    1. ``normalize_country`` — maps a country string to its ISO alpha-2 code.
    2. ``parse_location``    — extracts city and country from a free-text
                               location string.

The approach is a deterministic dictionary lookup.  No geocoding APIs
or network calls.  The dictionary covers common variations; unknown
inputs return ``None``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Country alias → ISO alpha-2 mapping
# ---------------------------------------------------------------------------

_COUNTRY_ALIASES: dict[str, str] = {
    # Full names
    "united states": "US",
    "united states of america": "US",
    "america": "US",
    "india": "IN",
    "united kingdom": "GB",
    "great britain": "GB",
    "england": "GB",
    "canada": "CA",
    "germany": "DE",
    "france": "FR",
    "australia": "AU",
    "japan": "JP",
    "china": "CN",
    "brazil": "BR",
    "singapore": "SG",
    "israel": "IL",
    "netherlands": "NL",
    "ireland": "IE",
    "sweden": "SE",
    "switzerland": "CH",
    "south korea": "KR",
    "spain": "ES",
    "italy": "IT",

    # Common abbreviations
    "usa": "US",
    "us": "US",
    "uk": "GB",
    "u.s.": "US",
    "u.s.a.": "US",
    "u.k.": "GB",

    # ISO codes (passthrough)
    "in": "IN",
    "gb": "GB",
    "ca": "CA",
    "de": "DE",
    "fr": "FR",
    "au": "AU",
    "jp": "JP",
    "cn": "CN",
    "br": "BR",
    "sg": "SG",
    "il": "IL",
    "nl": "NL",
    "ie": "IE",
    "se": "SE",
    "ch": "CH",
    "kr": "KR",
    "es": "ES",
    "it": "IT",
}


# ---------------------------------------------------------------------------
# US state abbreviation → state name (for parsing "New York, NY")
# ---------------------------------------------------------------------------

_US_STATE_ABBREVIATIONS: dict[str, str] = {
    "al": "Alabama", "ak": "Alaska", "az": "Arizona", "ar": "Arkansas",
    "ca": "California", "co": "Colorado", "ct": "Connecticut",
    "de": "Delaware", "fl": "Florida", "ga": "Georgia", "hi": "Hawaii",
    "id": "Idaho", "il": "Illinois", "in": "Indiana", "ia": "Iowa",
    "ks": "Kansas", "ky": "Kentucky", "la": "Louisiana", "me": "Maine",
    "md": "Maryland", "ma": "Massachusetts", "mi": "Michigan",
    "mn": "Minnesota", "ms": "Mississippi", "mo": "Missouri",
    "mt": "Montana", "ne": "Nebraska", "nv": "Nevada",
    "nh": "New Hampshire", "nj": "New Jersey", "nm": "New Mexico",
    "ny": "New York", "nc": "North Carolina", "nd": "North Dakota",
    "oh": "Ohio", "ok": "Oklahoma", "or": "Oregon", "pa": "Pennsylvania",
    "ri": "Rhode Island", "sc": "South Carolina", "sd": "South Dakota",
    "tn": "Tennessee", "tx": "Texas", "ut": "Utah", "vt": "Vermont",
    "va": "Virginia", "wa": "Washington", "wv": "West Virginia",
    "wi": "Wisconsin", "wy": "Wyoming", "dc": "District of Columbia",
}

#: Reverse mapping: state name → abbreviation (for detection)
_US_STATE_NAMES: dict[str, str] = {
    v.lower(): k.upper() for k, v in _US_STATE_ABBREVIATIONS.items()
}

#: Major cities → country code mapping for common unambiguous cities.
_CITY_COUNTRY_MAP: dict[str, str] = {
    "san francisco": "US", "new york": "US", "los angeles": "US",
    "seattle": "US", "austin": "US", "chicago": "US", "boston": "US",
    "denver": "US", "portland": "US", "miami": "US",
    "bangalore": "IN", "bengaluru": "IN", "mumbai": "IN",
    "hyderabad": "IN", "delhi": "IN", "new delhi": "IN",
    "pune": "IN", "chennai": "IN",
    "london": "GB", "manchester": "GB", "edinburgh": "GB",
    "toronto": "CA", "vancouver": "CA", "montreal": "CA",
    "berlin": "DE", "munich": "DE",
    "paris": "FR", "lyon": "FR",
    "tokyo": "JP", "osaka": "JP",
    "sydney": "AU", "melbourne": "AU",
    "singapore": "SG",
    "tel aviv": "IL",
    "amsterdam": "NL",
    "dublin": "IE",
    "stockholm": "SE",
    "zurich": "CH",
    "seoul": "KR",
    "beijing": "CN", "shanghai": "CN", "shenzhen": "CN",
    "sao paulo": "BR",
}


# ---------------------------------------------------------------------------
# Parsed location result
# ---------------------------------------------------------------------------


@dataclass
class ParsedLocation:
    """Structured representation of a parsed location.

    Attributes:
        city:         City name, if identified.
        region:       State or region, if identified.
        country_code: ISO 3166-1 alpha-2 country code, if identified.
        raw:          The original input string.
    """

    city: Optional[str] = None
    region: Optional[str] = None
    country_code: Optional[str] = None
    raw: Optional[str] = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def normalize_country(raw: str | None) -> Optional[str]:
    """Map a country name or abbreviation to its ISO 3166-1 alpha-2 code.

    Args:
        raw: A country string (e.g. "United States", "USA", "IN").

    Returns:
        The ISO alpha-2 code (e.g. ``"US"``), or ``None`` if unrecognized.

    Examples:
        >>> normalize_country("United States")
        'US'
        >>> normalize_country("usa")
        'US'
        >>> normalize_country("India")
        'IN'
        >>> normalize_country("unknown-place")
        None
    """
    if not raw or not isinstance(raw, str):
        return None

    cleaned = raw.strip().lower()
    if not cleaned:
        return None

    return _COUNTRY_ALIASES.get(cleaned)


def parse_location(raw: str | None) -> ParsedLocation:
    """Parse a free-text location string into structured components.

    Attempts to extract city and country from strings like:
        - "San Francisco, US"
        - "Bangalore, India"
        - "New York, NY"
        - "San Francisco, California"

    The algorithm splits on commas and tries to resolve the last
    segment as a country, then the second-to-last as a US state,
    then falls back to city-based country inference.

    Args:
        raw: A free-text location string.

    Returns:
        A ``ParsedLocation`` with whatever components could be identified.

    Examples:
        >>> loc = parse_location("San Francisco, US")
        >>> loc.city, loc.country_code
        ('San Francisco', 'US')

        >>> loc = parse_location("Bangalore India")
        >>> loc.country_code
        'IN'
    """
    result = ParsedLocation(raw=raw)

    if not raw or not isinstance(raw, str):
        return result

    cleaned = raw.strip()
    if not cleaned:
        return result

    # Split on commas; fall back to space-separated tokens for
    # inputs like "San Francisco US" (no comma).
    parts = [p.strip() for p in cleaned.split(",") if p.strip()]

    if len(parts) == 1:
        # No comma — try splitting by spaces and testing the last word
        # as a country.  E.g. "San Francisco US" → city="San Francisco", country="US"
        words = cleaned.rsplit(maxsplit=1)
        if len(words) == 2:
            maybe_country = normalize_country(words[1])
            if maybe_country:
                result.city = words[0].strip()
                result.country_code = maybe_country
                return result

        # Try the whole string as a country
        country = normalize_country(cleaned)
        if country:
            result.country_code = country
            return result

        # Try as a known city
        city_lower = cleaned.lower()
        if city_lower in _CITY_COUNTRY_MAP:
            result.city = cleaned
            result.country_code = _CITY_COUNTRY_MAP[city_lower]
            return result

        # Can't parse — store raw city
        result.city = cleaned
        return result

    # Multiple parts — try the last part as a country
    last = parts[-1]
    country = normalize_country(last)

    if country:
        result.country_code = country
        if len(parts) >= 3:
            result.city = parts[0]
            result.region = parts[1]
        elif len(parts) == 2:
            result.city = parts[0]
        return result

    # Last part might be a US state name or abbreviation
    last_lower = last.lower()
    if last_lower in _US_STATE_ABBREVIATIONS:
        result.region = last.upper()
        result.country_code = "US"
        if len(parts) >= 2:
            result.city = parts[0]
        return result

    if last_lower in _US_STATE_NAMES:
        result.region = _US_STATE_NAMES[last_lower]
        result.country_code = "US"
        if len(parts) >= 2:
            result.city = parts[0]
        return result

    # Try city-based inference on the first part
    first_lower = parts[0].lower()
    if first_lower in _CITY_COUNTRY_MAP:
        result.city = parts[0]
        result.country_code = _CITY_COUNTRY_MAP[first_lower]
        if len(parts) >= 2:
            result.region = parts[1]
        return result

    # Fallback: store what we have
    result.city = parts[0]
    if len(parts) >= 2:
        result.region = parts[-1]

    logger.debug("Could not resolve country from location: %r", raw)
    return result
