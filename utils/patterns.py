"""
Pre-compiled regex patterns shared across adapters and normalizers.

Compiling patterns once at import time and reusing them is both
cleaner (no duplicated regex strings) and faster (compiled patterns
skip the compilation step on each use).

All patterns are designed for extraction, not strict validation.
For example, ``EMAIL_PATTERN`` is intentionally broad to catch
emails embedded in prose — the normalizer downstream will validate
format correctness.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Contact information patterns
# ---------------------------------------------------------------------------

#: Matches most common email address formats.
#: Intentionally broad to catch emails in free text (resumes, notes).
EMAIL_PATTERN: re.Pattern[str] = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
)

#: Matches phone numbers in various formats:
#:   - +1 (555) 867-5309
#:   - 555-867-5309
#:   - (555) 867 5309
#:   - +91-98765-43210
#:   - 5558675309
#: Captures the full match; normalization handles cleanup.
PHONE_PATTERN: re.Pattern[str] = re.compile(
    r"(?:\+?\d{1,3}[\s\-.]?)?"       # optional country code
    r"(?:\(?\d{2,5}\)?[\s\-.]?)?"     # optional area code
    r"\d{3,5}"                        # first digit group
    r"[\s\-.]?"                       # separator
    r"\d{3,5}"                        # second digit group
    r"(?:[\s\-.]?\d{1,5})?",         # optional extension
)

# ---------------------------------------------------------------------------
# URL patterns
# ---------------------------------------------------------------------------

#: Matches http/https URLs.
URL_PATTERN: re.Pattern[str] = re.compile(
    r"https?://[^\s<>\"']+",
)

#: Matches GitHub profile URLs and extracts the username.
GITHUB_URL_PATTERN: re.Pattern[str] = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/([a-zA-Z0-9\-]+)",
)

#: Matches LinkedIn profile URLs.
LINKEDIN_URL_PATTERN: re.Pattern[str] = re.compile(
    r"(?:https?://)?(?:www\.)?linkedin\.com/in/([a-zA-Z0-9\-]+)",
)

# ---------------------------------------------------------------------------
# Date patterns — ordered from most specific to least specific
# ---------------------------------------------------------------------------

#: Matches "January 2022", "Jan 2022", "Feb. 2023"
MONTH_YEAR_PATTERN: re.Pattern[str] = re.compile(
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|"
    r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\.?\s+(\d{4})",
    re.IGNORECASE,
)

#: Matches "01/2022", "12-2023", "06.2024"
NUMERIC_MONTH_YEAR_PATTERN: re.Pattern[str] = re.compile(
    r"(\d{1,2})[/\-.](\d{4})",
)

#: Matches ISO dates "2022-01-15", "2022-01"
ISO_DATE_PATTERN: re.Pattern[str] = re.compile(
    r"(\d{4})-(\d{2})(?:-\d{2})?",
)

#: Matches standalone year "2022"
YEAR_ONLY_PATTERN: re.Pattern[str] = re.compile(
    r"^(\d{4})$",
)

# ---------------------------------------------------------------------------
# Resume section headers — used by the PDF adapter to detect sections
# ---------------------------------------------------------------------------

#: Common section header keywords found in resumes.
RESUME_SECTION_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*(?:experience|work\s*experience|employment|"
    r"education|skills|technical\s*skills|"
    r"projects|certifications|summary|objective|"
    r"awards|publications|languages)\s*:?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
