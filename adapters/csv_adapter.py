"""
Recruiter CSV export adapter.

Reads a CSV file exported by a recruiter from their contact management
tool or spreadsheet.  CSV is the most structured source — every row
has predictable columns — but column names vary between exports.

This adapter handles column name variations by mapping common header
synonyms to canonical field names before extraction.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

from adapters.base import BaseAdapter
from schema.canonical import RawCandidateRecord
from utils.constants import SourceType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column name synonyms → canonical field mapping
# ---------------------------------------------------------------------------

#: Maps common CSV column header variations to our internal field names.
#: Headers are lowercased and stripped before lookup.
_COLUMN_MAP: dict[str, str] = {
    # Name variations
    "name": "full_name",
    "full_name": "full_name",
    "full name": "full_name",
    "candidate_name": "full_name",
    "candidate name": "full_name",
    "applicant_name": "full_name",
    "applicant name": "full_name",

    # Email variations
    "email": "email",
    "emails": "email",
    "email_address": "email",
    "email address": "email",
    "e-mail": "email",
    "mail": "email",

    # Phone variations
    "phone": "phone",
    "phones": "phone",
    "phone_number": "phone",
    "phone number": "phone",
    "telephone": "phone",
    "mobile": "phone",
    "contact": "phone",

    # Company variations
    "company": "current_company",
    "current_company": "current_company",
    "current company": "current_company",
    "employer": "current_company",
    "organization": "current_company",

    # Title variations
    "title": "current_title",
    "current_title": "current_title",
    "current title": "current_title",
    "job_title": "current_title",
    "job title": "current_title",
    "position": "current_title",
    "role": "current_title",

    # Skills variations
    "skills": "skills",
    "skill": "skills",
    "technical_skills": "skills",
    "technical skills": "skills",
    "competencies": "skills",

    # Location variations
    "location": "location",
    "city": "location",
    "address": "location",
    "region": "location",
}


class CSVAdapter(BaseAdapter):
    """Adapter for recruiter CSV exports.

    Reads a CSV file, maps columns to canonical fields, and produces
    one ``RawCandidateRecord`` per row.  Rows with no usable data
    (no name, no email) are silently skipped.
    """

    @property
    def source_type(self) -> SourceType:
        return SourceType.CSV

    def extract(self, source_path: str) -> list[RawCandidateRecord]:
        """Extract candidate records from a CSV file.

        Args:
            source_path: Path to the CSV file.

        Returns:
            List of ``RawCandidateRecord`` objects, one per row.
            Returns empty list on parse failure.
        """
        path = Path(source_path)
        if not path.exists():
            logger.warning("CSV file not found: %s", source_path)
            return []

        records: list[RawCandidateRecord] = []

        try:
            with open(path, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames is None:
                    logger.warning("CSV has no headers: %s", source_path)
                    return []

                # Build a mapping from CSV column index to our field name
                header_map: dict[str, str] = {}
                for col in reader.fieldnames:
                    canonical = _COLUMN_MAP.get(col.strip().lower())
                    if canonical:
                        header_map[col] = canonical

                for row_num, row in enumerate(reader, start=2):
                    record = self._parse_row(row, header_map, source_path)
                    if record is not None:
                        records.append(record)
                    else:
                        logger.debug(
                            "Skipped empty row %d in %s", row_num, source_path
                        )

        except Exception:
            logger.exception("Failed to parse CSV: %s", source_path)
            return []

        logger.info(
            "CSV adapter extracted %d records from %s", len(records), source_path
        )
        return records

    def _parse_row(
        self,
        row: dict[str, str],
        header_map: dict[str, str],
        source_path: str,
    ) -> RawCandidateRecord | None:
        """Parse a single CSV row into a RawCandidateRecord.

        Returns ``None`` if the row has no useful data.
        """
        # Map CSV columns to our field names
        mapped: dict[str, str] = {}
        for csv_col, canonical_field in header_map.items():
            value = row.get(csv_col, "").strip()
            if value:
                mapped[canonical_field] = value

        # Skip rows with no identifying information
        if not mapped.get("full_name") and not mapped.get("email"):
            return None

        # Parse skills: "Python, ML, TensorFlow" → ["Python", "ML", "TensorFlow"]
        skills: list[str] = []
        if "skills" in mapped:
            skills = [
                s.strip()
                for s in mapped["skills"].split(",")
                if s.strip()
            ]

        # Build emails list
        emails: list[str] = []
        if "email" in mapped:
            emails = [mapped["email"].strip()]

        # Build phones list
        phones: list[str] = []
        if "phone" in mapped:
            phones = [mapped["phone"].strip()]

        return RawCandidateRecord(
            source_type=self.source_type,
            source_path=source_path,
            full_name=mapped.get("full_name"),
            emails=emails,
            phones=phones,
            location=mapped.get("location"),
            skills=skills,
            current_company=mapped.get("current_company"),
            current_title=mapped.get("current_title"),
            raw_metadata={"original_row": dict(row)},
        )
