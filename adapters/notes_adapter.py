"""
Recruiter notes (plain text) adapter.

Reads a free-text .txt file containing a recruiter's informal notes
about candidates.  This is the most unstructured source in the
pipeline — there is no schema, no consistent formatting, and the
same file may describe multiple candidates separated by blank lines
or headings.

Extraction Strategy:
    1. Split text into candidate blocks (separated by blank lines
       or lines containing "---").
    2. For each block, extract:
       - Name: first non-empty line (heuristic).
       - Emails: regex extraction.
       - Phones: regex extraction.
       - Skills: lines containing "skills" keyword.
       - Notes: everything else → raw_metadata.
    3. Return one RawCandidateRecord per block.

This adapter carries the lowest trust weight (0.5) because recruiter
notes are paraphrased observations, not validated data.
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
# Block splitting
# ---------------------------------------------------------------------------

#: Pattern that separates candidate blocks in a notes file.
_BLOCK_SEPARATOR = re.compile(r"\n\s*(?:---+|\*\*\*+|===+)\s*\n")

#: Pattern to detect skill-listing lines.
_SKILLS_LINE_PATTERN = re.compile(
    r"(?:skills?|tech(?:nolog(?:y|ies))?|stack)\s*[:;]\s*(.+)",
    re.IGNORECASE,
)

#: Pattern to detect company/role mentions.
_COMPANY_PATTERN = re.compile(
    r"(?:works?\s+at|currently\s+at|employed\s+(?:at|by)|company)\s*[:;]?\s*(.+)",
    re.IGNORECASE,
)

_TITLE_PATTERN = re.compile(
    r"(?:role|title|position)\s*[:;]?\s*(.+)",
    re.IGNORECASE,
)

_LOCATION_PATTERN = re.compile(
    r"(?:location|based\s+in|located\s+in|from|city)\s*[:;]?\s*(.+)",
    re.IGNORECASE,
)


class NotesAdapter(BaseAdapter):
    """Adapter for recruiter notes in plain text files.

    Splits the file into candidate blocks and extracts structured
    data using regex heuristics.  This is inherently lossy — we
    extract what we can and store everything else in raw_metadata
    for debugging.
    """

    @property
    def source_type(self) -> SourceType:
        return SourceType.RECRUITER_NOTES

    def extract(self, source_path: str) -> list[RawCandidateRecord]:
        """Extract candidate records from a recruiter notes file.

        Args:
            source_path: Path to the .txt file.

        Returns:
            List of ``RawCandidateRecord`` objects, one per candidate
            block.  Returns empty list on parse failure.
        """
        path = Path(source_path)
        if not path.exists():
            logger.warning("Notes file not found: %s", source_path)
            return []

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                text = path.read_text(encoding="latin-1")
            except Exception:
                logger.exception("Failed to read notes file: %s", source_path)
                return []

        if not text.strip():
            logger.warning("Empty notes file: %s", source_path)
            return []

        # Split into candidate blocks
        blocks = _BLOCK_SEPARATOR.split(text)
        if len(blocks) == 1:
            # No explicit separators — try splitting on double newlines
            # that look like they separate distinct candidates
            blocks = re.split(r"\n\s*\n\s*\n", text)

        records: list[RawCandidateRecord] = []
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            record = self._parse_block(block, source_path)
            if record is not None:
                records.append(record)

        logger.info(
            "Notes adapter extracted %d records from %s",
            len(records), source_path,
        )
        return records

    def _parse_block(
        self,
        block: str,
        source_path: str,
    ) -> RawCandidateRecord | None:
        """Parse a single candidate block from recruiter notes."""
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not lines:
            return None

        # --- Contact info extraction ---
        emails = list(set(EMAIL_PATTERN.findall(block)))
        phone_matches = PHONE_PATTERN.findall(block)
        phones = list(set(
            m for m in phone_matches
            if sum(c.isdigit() for c in m) >= 7
        ))
        urls = list(set(URL_PATTERN.findall(block)))

        # --- Name: first line that doesn't look like metadata ---
        full_name = None
        for line in lines:
            # Skip lines that are clearly metadata
            if EMAIL_PATTERN.search(line):
                continue
            if _SKILLS_LINE_PATTERN.match(line):
                continue
            if _COMPANY_PATTERN.match(line):
                continue
            if _TITLE_PATTERN.match(line):
                continue
            if _LOCATION_PATTERN.match(line):
                continue
            if line.startswith("+") or line.startswith("("):
                continue
            # First "clean" line is likely the name
            # Only if it's reasonably short (names are short)
            if len(line) < 60:
                full_name = line.rstrip(":")
                break

        # --- Skills ---
        skills: list[str] = []
        for line in lines:
            match = _SKILLS_LINE_PATTERN.match(line)
            if match:
                raw_skills = match.group(1)
                skills.extend(
                    s.strip()
                    for s in re.split(r"[,;|/]+", raw_skills)
                    if s.strip()
                )

        # --- Company ---
        current_company = None
        for line in lines:
            match = _COMPANY_PATTERN.match(line)
            if match:
                current_company = match.group(1).strip().rstrip(".")
                break

        # --- Title ---
        current_title = None
        for line in lines:
            match = _TITLE_PATTERN.match(line)
            if match:
                current_title = match.group(1).strip().rstrip(".")
                break

        # --- Location ---
        location = None
        for line in lines:
            match = _LOCATION_PATTERN.match(line)
            if match:
                location = match.group(1).strip().rstrip(".")
                break

        # Skip blocks with no identifying information at all
        if not full_name and not emails:
            return None

        return RawCandidateRecord(
            source_type=self.source_type,
            source_path=source_path,
            full_name=full_name,
            emails=emails,
            phones=phones,
            location=location,
            skills=skills,
            current_company=current_company,
            current_title=current_title,
            links=urls,
            raw_metadata={"raw_block": block},
        )
