"""
ATS (Applicant Tracking System) JSON adapter.

Reads a JSON blob exported from an ATS like Greenhouse, Lever, or
Workday.  ATS data is semi-structured — it's valid JSON with a
consistent shape, but the field names don't match our canonical
schema and the contact info is nested.

This adapter maps the ATS-specific field paths to our internal
field names.  Because ATS data is entered through validated forms,
it carries the highest trust weight (0.9) in the pipeline.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from adapters.base import BaseAdapter
from schema.canonical import RawCandidateRecord
from utils.constants import SourceType

logger = logging.getLogger(__name__)


class ATSAdapter(BaseAdapter):
    """Adapter for ATS JSON exports.

    Expects a JSON file containing either:
        - A JSON array of candidate objects, or
        - A single candidate object.

    Each candidate object is mapped to a ``RawCandidateRecord``
    using a deterministic field-path mapping.
    """

    @property
    def source_type(self) -> SourceType:
        return SourceType.ATS_JSON

    def extract(self, source_path: str) -> list[RawCandidateRecord]:
        """Extract candidate records from an ATS JSON file.

        Args:
            source_path: Path to the JSON file.

        Returns:
            List of ``RawCandidateRecord`` objects.
            Returns empty list on parse failure.
        """
        path = Path(source_path)
        if not path.exists():
            logger.warning("ATS JSON file not found: %s", source_path)
            return []

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.exception("Failed to parse ATS JSON: %s", source_path)
            return []

        # Handle both single object and array
        if isinstance(data, dict):
            candidates = [data]
        elif isinstance(data, list):
            candidates = data
        else:
            logger.warning("Unexpected JSON root type in %s: %s", source_path, type(data))
            return []

        records: list[RawCandidateRecord] = []
        for i, obj in enumerate(candidates):
            if not isinstance(obj, dict):
                logger.debug("Skipping non-dict entry at index %d in %s", i, source_path)
                continue
            record = self._parse_candidate(obj, source_path)
            if record is not None:
                records.append(record)

        logger.info(
            "ATS adapter extracted %d records from %s", len(records), source_path
        )
        return records

    def _parse_candidate(
        self,
        obj: dict[str, Any],
        source_path: str,
    ) -> RawCandidateRecord | None:
        """Map an ATS candidate object to a RawCandidateRecord."""

        # --- Name ---
        full_name = (
            obj.get("applicant_name")
            or obj.get("candidate_name")
            or obj.get("full_name")
            or obj.get("name")
        )

        # --- Contact info (may be nested) ---
        contact = obj.get("contact", {})
        if not isinstance(contact, dict):
            contact = {}

        emails: list[str] = []
        email = contact.get("email") or contact.get("mail") or obj.get("email")
        if email and isinstance(email, str):
            emails = [email.strip()]
        elif isinstance(email, list):
            emails = [e.strip() for e in email if isinstance(e, str)]

        phones: list[str] = []
        phone = contact.get("phone") or contact.get("telephone") or obj.get("phone")
        if phone and isinstance(phone, str):
            phones = [str(phone).strip()]
        elif isinstance(phone, (int, float)):
            phones = [str(int(phone))]
        elif isinstance(phone, list):
            phones = [str(p).strip() for p in phone]

        # --- Company & Title ---
        current_company = (
            obj.get("current_employer")
            or obj.get("current_company")
            or obj.get("company")
        )
        current_title = (
            obj.get("position_applied")
            or obj.get("current_title")
            or obj.get("title")
            or obj.get("job_title")
        )

        # --- Skills ---
        skills_raw = (
            obj.get("skills_list")
            or obj.get("skills")
            or obj.get("technical_skills")
            or []
        )
        if isinstance(skills_raw, str):
            skills = [s.strip() for s in skills_raw.split(",") if s.strip()]
        elif isinstance(skills_raw, list):
            skills = [str(s).strip() for s in skills_raw if s]
        else:
            skills = []

        # --- Location ---
        location = obj.get("location") or obj.get("city")
        if isinstance(location, dict):
            # Handle {"city": "SF", "country": "US"} structure
            parts = [
                location.get("city", ""),
                location.get("state", ""),
                location.get("country", ""),
            ]
            location = ", ".join(p for p in parts if p)

        # --- Experience ---
        experience = obj.get("experience", [])
        if not isinstance(experience, list):
            experience = []
        experience = [
            self._normalize_experience_entry(e)
            for e in experience
            if isinstance(e, dict)
        ]

        # --- Education ---
        education = obj.get("education", [])
        if not isinstance(education, list):
            education = []
        education = [
            self._normalize_education_entry(e)
            for e in education
            if isinstance(e, dict)
        ]

        # --- Links ---
        links: list[str] = []
        for key in ("linkedin", "github", "portfolio", "website", "links"):
            val = obj.get(key)
            if isinstance(val, str) and val.strip():
                links.append(val.strip())
            elif isinstance(val, list):
                links.extend(str(v).strip() for v in val if v)

        # Skip if no identifying info
        if not full_name and not emails:
            logger.debug("ATS entry has no name or email — skipping")
            return None

        return RawCandidateRecord(
            source_type=self.source_type,
            source_path=source_path,
            full_name=full_name,
            emails=emails,
            phones=phones,
            location=location if isinstance(location, str) else None,
            skills=skills,
            experience=experience,
            education=education,
            current_company=current_company,
            current_title=current_title,
            links=links,
            raw_metadata={"original_object": obj},
        )

    @staticmethod
    def _normalize_experience_entry(entry: dict[str, Any]) -> dict[str, Any]:
        """Standardize experience entry keys."""
        return {
            "company": entry.get("company") or entry.get("organization", ""),
            "title": entry.get("title") or entry.get("role") or entry.get("position", ""),
            "start_date": entry.get("start_date") or entry.get("from", ""),
            "end_date": entry.get("end_date") or entry.get("to", ""),
        }

    @staticmethod
    def _normalize_education_entry(entry: dict[str, Any]) -> dict[str, Any]:
        """Standardize education entry keys."""
        return {
            "institution": entry.get("institution") or entry.get("school") or entry.get("university", ""),
            "degree": entry.get("degree") or entry.get("qualification", ""),
            "year": entry.get("year") or entry.get("graduation_year", ""),
        }
