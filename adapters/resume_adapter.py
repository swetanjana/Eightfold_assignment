"""
Resume PDF adapter.

Extracts candidate data from a PDF resume using ``pypdf`` for text
extraction and regex patterns for structured field detection.

Resumes are the hardest source to parse because they are pure prose
with no enforced schema.  This adapter uses a deterministic,
heuristic approach:

    1. Extract raw text from all PDF pages.
    2. Use regex to find emails, phone numbers, and URLs.
    3. Detect section headers ("Experience", "Education", "Skills").
    4. Parse content within detected sections.
    5. Use the first non-empty line as the candidate name (common
       resume convention).

No LLM or AI calls — all extraction is rule-based and deterministic.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from adapters.base import BaseAdapter
from schema.canonical import RawCandidateRecord
from utils.constants import SourceType
from utils.patterns import EMAIL_PATTERN, PHONE_PATTERN, URL_PATTERN

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Section detection patterns
# ---------------------------------------------------------------------------

_SECTION_HEADERS: dict[str, re.Pattern[str]] = {
    "experience": re.compile(
        r"^\s*(?:work\s*|professional\s*)?experience\s*:?\s*$", re.IGNORECASE
    ),
    "education": re.compile(
        r"^\s*education\s*:?\s*$", re.IGNORECASE
    ),
    "skills": re.compile(
        r"^\s*(?:technical\s*|core\s*)?skills\s*:?\s*$", re.IGNORECASE
    ),
    "summary": re.compile(
        r"^\s*(?:summary|objective|profile|about(?: me)?)\s*:?\s*$", re.IGNORECASE
    ),
    "projects": re.compile(
        r"^\s*(?:personal\s*|academic\s*)?projects?\s*:?\s*$", re.IGNORECASE
    ),
    "certifications": re.compile(
        r"^\s*certifications?\s*:?\s*$", re.IGNORECASE
    ),
    "achievements": re.compile(
        r"^\s*(?:achievements|awards|honors)\s*:?\s*$", re.IGNORECASE
    ),
    "leadership": re.compile(
        r"^\s*(?:leadership(?: & communication)?|extracurriculars|activities)\s*:?\s*$", re.IGNORECASE
    ),
    "languages": re.compile(
        r"^\s*languages\s*:?\s*$", re.IGNORECASE
    ),
    "interests": re.compile(
        r"^\s*(?:interests|hobbies)\s*:?\s*$", re.IGNORECASE
    ),
}

#: Pattern to detect experience entries like "Company — Title" or "Company | Title"
_EXPERIENCE_LINE_PATTERN: re.Pattern[str] = re.compile(
    r"^(.+?)\s*[—\-|,]\s*(.+?)$"
)

#: Pattern to detect date ranges like "Jan 2020 – Present" or "2019 - 2022"
_DATE_RANGE_PATTERN: re.Pattern[str] = re.compile(
    r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}"
    r"|(?:\d{1,2}/\d{4})"
    r"|(?:\d{4}))"
    r"\s*[-–—to]+\s*"
    r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}"
    r"|(?:\d{1,2}/\d{4})"
    r"|(?:\d{4})"
    r"|Present|Current|Now)",
    re.IGNORECASE,
)


class ResumeAdapter(BaseAdapter):
    """Adapter for resume files (PDF).

    Uses ``pypdf`` for text extraction and regex for field detection.
    Falls back gracefully if ``pypdf`` is not installed or the PDF
    is unreadable.
    """

    @property
    def source_type(self) -> SourceType:
        return SourceType.RESUME_PDF

    def extract(self, source_path: str) -> list[RawCandidateRecord]:
        """Extract candidate data from a resume PDF.

        Args:
            source_path: Path to the PDF file.

        Returns:
            A list with one ``RawCandidateRecord``, or an empty list
            if the file cannot be parsed.
        """
        path = Path(source_path)
        if not path.exists():
            logger.warning("Resume file not found: %s", source_path)
            return []

        text = self._extract_text(path)
        if not text:
            logger.warning("No text extracted from resume: %s", source_path)
            return []

        record = self._parse_resume_text(text, source_path)
        if record is None:
            return []

        logger.info("Resume adapter extracted 1 record from %s", source_path)
        return [record]

    def _extract_text(self, path: Path) -> str:
        """Extract raw text from a PDF file."""
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            pages: list[str] = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    pages.append(page_text)
            return "\n".join(pages)

        except ImportError:
            logger.error(
                "pypdf is not installed — cannot parse PDF resumes. "
                "Install with: pip install pypdf"
            )
            return ""
        except Exception:
            logger.exception("Failed to extract text from PDF: %s", path)
            return ""

    def _parse_resume_text(
        self,
        text: str,
        source_path: str,
    ) -> RawCandidateRecord | None:
        """Parse extracted resume text into a RawCandidateRecord."""

        lines = text.split("\n")
        non_empty_lines = [line.strip() for line in lines if line.strip()]

        if not non_empty_lines:
            return None

        # --- Contact info extraction (regex-based) ---
        emails = list(set(EMAIL_PATTERN.findall(text)))
        phone_matches = PHONE_PATTERN.findall(text)
        # Filter phone matches: must have at least 7 digits
        phones = list(set(
            m for m in phone_matches
            if sum(c.isdigit() for c in m) >= 7
        ))
        urls = list(set(URL_PATTERN.findall(text)))

        # --- Name extraction ---
        # Convention: first non-empty line of a resume is the name,
        # unless it looks like an email or phone
        full_name = None
        for line in non_empty_lines:
            # Skip lines that are contact info
            if EMAIL_PATTERN.search(line) and len(line) < 60:
                continue
            if line.startswith("+") or line.startswith("("):
                continue
            if line.lower() in ("resume", "curriculum vitae", "cv"):
                continue
            full_name = line.strip()
            break

        # --- Section parsing ---
        sections = self._detect_sections(non_empty_lines)

        # --- Skills ---
        skills: list[str] = []
        if "skills" in sections:
            skills = self._parse_skills_section(sections["skills"])

        # --- Experience ---
        experience: list[dict[str, Any]] = []
        if "experience" in sections:
            experience = self._parse_experience_section(sections["experience"])

        # --- Education ---
        education: list[dict[str, Any]] = []
        if "education" in sections:
            education = self._parse_education_section(sections["education"])

        # --- Current Company & Title (derived from experience) ---
        current_company = None
        current_title = None
        if experience:
            current_company = experience[0].get("company")
            current_title = experience[0].get("title")

        # --- Location ---
        # Try to find a location in the header area (first few lines)
        location = self._detect_location(non_empty_lines[:6])

        return RawCandidateRecord(
            source_type=self.source_type,
            source_path=source_path,
            full_name=full_name,
            emails=emails,
            phones=phones,
            location=location,
            skills=skills,
            experience=experience,
            education=education,
            current_company=current_company,
            current_title=current_title,
            links=urls,
            raw_metadata={"extracted_text_length": len(text)},
        )

    def _detect_sections(
        self,
        lines: list[str],
    ) -> dict[str, list[str]]:
        """Detect section boundaries and group lines by section."""
        sections: dict[str, list[str]] = {}
        current_section: str | None = None

        for line in lines:
            # Check if this line is a section header
            detected = False
            for section_name, pattern in _SECTION_HEADERS.items():
                if pattern.match(line):
                    current_section = section_name
                    sections[section_name] = []
                    detected = True
                    break

            if not detected and current_section is not None:
                sections[current_section].append(line)

        return sections

    def _parse_skills_section(self, lines: list[str]) -> list[str]:
        """Extract individual skills from a skills section.

        Handles formats like:
            - "Python, Java, Go, SQL"
            - "Python | Java | Go"
            - "• Python  • Java  • Go"
            - One skill per line
        """
        skills: list[str] = []

        for line in lines:
            # Check if this line looks like the start of a new section
            if any(p.match(line) for p in _SECTION_HEADERS.values()):
                break

            # Try splitting by common delimiters
            cleaned = line.strip()
            if not cleaned:
                continue

            # Remove bullet characters
            cleaned = re.sub(r"^[\•\-\*\>\▪\►]\s*", "", cleaned)

            # Skip lines that look like long sentences (not a list of skills)
            if len(cleaned) > 100 or len(cleaned.split()) > 15:
                continue

            # Split by comma, pipe, semicolon, or bullet
            parts = re.split(r"[,|;•\•]+", cleaned)
            for part in parts:
                skill = part.strip().strip("•-* ")
                # ensure skill is not a full sentence (e.g. no more than 4 words)
                if skill and len(skill) > 1 and len(skill.split()) <= 4:
                    skills.append(skill)

        return skills

    def _parse_experience_section(
        self,
        lines: list[str],
    ) -> list[dict[str, Any]]:
        """Extract experience entries from an experience section."""
        entries: list[dict[str, Any]] = []
        current_entry: dict[str, Any] | None = None

        for line in lines:
            # Check for new section start
            if any(p.match(line) for p in _SECTION_HEADERS.values()):
                break

            # Look for date ranges
            date_match = _DATE_RANGE_PATTERN.search(line)

            # Look for "Company — Title" patterns
            exp_match = _EXPERIENCE_LINE_PATTERN.match(
                _DATE_RANGE_PATTERN.sub("", line).strip()
            )

            if date_match or exp_match:
                # Start a new experience entry
                if current_entry:
                    entries.append(current_entry)

                current_entry = {
                    "company": "",
                    "title": "",
                    "start_date": "",
                    "end_date": "",
                }

                if exp_match:
                    current_entry["company"] = exp_match.group(1).strip()
                    current_entry["title"] = exp_match.group(2).strip()

                if date_match:
                    current_entry["start_date"] = date_match.group(1).strip()
                    current_entry["end_date"] = date_match.group(2).strip()

        # Don't forget the last entry
        if current_entry:
            entries.append(current_entry)

        return entries

    def _parse_education_section(
        self,
        lines: list[str],
    ) -> list[dict[str, Any]]:
        """Extract education entries from an education section."""
        entries: list[dict[str, Any]] = []

        combined = " ".join(lines)
        # Look for patterns like "University Name, Degree, Year"
        # This is a simplified heuristic
        current: dict[str, Any] = {}

        for line in lines:
            if any(p.match(line) for p in _SECTION_HEADERS.values()):
                break

            # Look for a year
            year_match = re.search(r"\b(19|20)\d{2}\b", line)

            if year_match and current.get("institution"):
                current["year"] = year_match.group()
                entries.append(current)
                current = {}
            elif not current.get("institution"):
                current["institution"] = line.strip()
                current["degree"] = ""
                current["year"] = ""
                if year_match:
                    current["year"] = year_match.group()
            else:
                # Likely the degree line
                current["degree"] = line.strip()
                if year_match:
                    current["year"] = year_match.group()

        # Don't forget the last entry
        if current.get("institution"):
            entries.append(current)

        return entries

    @staticmethod
    def _detect_location(header_lines: list[str]) -> str | None:
        """Try to detect location from the resume header area.

        Many resumes include city, state in the first few lines
        alongside the name and contact info.
        """
        # Common location indicators
        location_pattern = re.compile(
            r"\b(?:San Francisco|New York|Los Angeles|Seattle|Austin|"
            r"Chicago|Boston|Denver|Portland|Miami|"
            r"Bangalore|Bengaluru|Mumbai|Hyderabad|Delhi|Pune|Chennai|"
            r"London|Toronto|Vancouver|Berlin|Paris|Tokyo|Sydney|"
            r"Singapore|Tel Aviv|Amsterdam|Dublin)\b",
            re.IGNORECASE,
        )

        for line in header_lines:
            # Skip lines that are clearly name or email
            if EMAIL_PATTERN.search(line):
                continue
            if location_pattern.search(line):
                return line.strip()

        return None
