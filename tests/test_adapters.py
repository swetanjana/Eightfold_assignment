"""
Tests for source adapters.

Validates that each adapter correctly extracts fields from its
respective source format and produces well-formed RawCandidateRecord
objects.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from adapters.csv_adapter import CSVAdapter
from adapters.ats_adapter import ATSAdapter
from schema.canonical import RawCandidateRecord
from utils.constants import SourceType


# ===================================================================
# CSV Adapter Tests
# ===================================================================


class TestCSVAdapter:
    """Tests for the Recruiter CSV adapter."""

    def _write_csv(self, tmp_path: Path, content: str) -> Path:
        filepath = tmp_path / "test.csv"
        filepath.write_text(content, encoding="utf-8")
        return filepath

    def test_extracts_basic_record(self, tmp_path: Path) -> None:
        csv_content = "name,email,phone,current_company,title,skills,location\nAlice Smith,alice@test.com,555-123-4567,Google,Engineer,\"Python, ML\",San Francisco US\n"
        path = self._write_csv(tmp_path, csv_content)

        adapter = CSVAdapter()
        records = adapter.extract(str(path))

        assert len(records) == 1
        r = records[0]
        assert r.source_type == SourceType.CSV
        assert r.full_name == "Alice Smith"
        assert r.emails == ["alice@test.com"]
        assert r.phones == ["555-123-4567"]
        assert r.current_company == "Google"
        assert r.current_title == "Engineer"
        assert "Python" in r.skills
        assert "ML" in r.skills
        assert r.location == "San Francisco US"

    def test_extracts_multiple_rows(self, tmp_path: Path) -> None:
        csv_content = (
            "name,email,phone\n"
            "Alice,alice@test.com,111\n"
            "Bob,bob@test.com,222\n"
        )
        path = self._write_csv(tmp_path, csv_content)

        records = CSVAdapter().extract(str(path))
        assert len(records) == 2
        assert records[0].full_name == "Alice"
        assert records[1].full_name == "Bob"

    def test_skips_empty_rows(self, tmp_path: Path) -> None:
        csv_content = "name,email\n,\nAlice,alice@test.com\n"
        path = self._write_csv(tmp_path, csv_content)

        records = CSVAdapter().extract(str(path))
        assert len(records) == 1
        assert records[0].full_name == "Alice"

    def test_handles_missing_columns(self, tmp_path: Path) -> None:
        """Columns not in the synonym map are ignored gracefully."""
        csv_content = "name,email,unknown_col\nAlice,alice@test.com,foo\n"
        path = self._write_csv(tmp_path, csv_content)

        records = CSVAdapter().extract(str(path))
        assert len(records) == 1
        assert records[0].full_name == "Alice"

    def test_handles_column_name_variations(self, tmp_path: Path) -> None:
        csv_content = "candidate_name,email_address,employer\nAlice,alice@test.com,Google\n"
        path = self._write_csv(tmp_path, csv_content)

        records = CSVAdapter().extract(str(path))
        assert len(records) == 1
        assert records[0].full_name == "Alice"
        assert records[0].current_company == "Google"

    def test_returns_empty_on_nonexistent_file(self) -> None:
        records = CSVAdapter().extract("/nonexistent/path.csv")
        assert records == []

    def test_returns_empty_on_malformed_csv(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.csv"
        path.write_bytes(b"\x80\x81\x82")  # invalid UTF-8
        records = CSVAdapter().extract(str(path))
        # Should return empty or whatever it can parse — not crash
        assert isinstance(records, list)

    def test_source_type_property(self) -> None:
        assert CSVAdapter().source_type == SourceType.CSV


# ===================================================================
# ATS JSON Adapter Tests
# ===================================================================


class TestATSAdapter:
    """Tests for the ATS JSON adapter."""

    def _write_json(self, tmp_path: Path, data: object) -> Path:
        filepath = tmp_path / "test.json"
        filepath.write_text(json.dumps(data), encoding="utf-8")
        return filepath

    def test_extracts_single_candidate(self, tmp_path: Path) -> None:
        data = {
            "applicant_name": "Alice Smith",
            "contact": {"email": "alice@test.com", "phone": "+15551234567"},
            "current_employer": "Google",
            "skills_list": ["Python", "ML"],
            "location": "San Francisco",
            "experience": [
                {"company": "Google", "title": "Engineer", "start_date": "Jan 2020", "end_date": "Present"}
            ],
            "education": [
                {"institution": "MIT", "degree": "BS CS", "year": "2019"}
            ],
        }
        path = self._write_json(tmp_path, data)

        records = ATSAdapter().extract(str(path))
        assert len(records) == 1
        r = records[0]
        assert r.source_type == SourceType.ATS_JSON
        assert r.full_name == "Alice Smith"
        assert r.emails == ["alice@test.com"]
        assert r.phones == ["+15551234567"]
        assert r.current_company == "Google"
        assert "Python" in r.skills
        assert len(r.experience) == 1
        assert r.experience[0]["company"] == "Google"

    def test_extracts_array_of_candidates(self, tmp_path: Path) -> None:
        data = [
            {"applicant_name": "Alice", "contact": {"email": "a@t.com"}},
            {"applicant_name": "Bob", "contact": {"email": "b@t.com"}},
        ]
        path = self._write_json(tmp_path, data)

        records = ATSAdapter().extract(str(path))
        assert len(records) == 2

    def test_handles_missing_contact_block(self, tmp_path: Path) -> None:
        data = {"applicant_name": "Alice"}
        path = self._write_json(tmp_path, data)

        records = ATSAdapter().extract(str(path))
        assert len(records) == 1
        assert records[0].emails == []
        assert records[0].phones == []

    def test_skips_entries_without_name_or_email(self, tmp_path: Path) -> None:
        data = [{"skills_list": ["Python"]}, {"applicant_name": "Alice"}]
        path = self._write_json(tmp_path, data)

        records = ATSAdapter().extract(str(path))
        # First entry has no name and no email → skipped
        assert len(records) == 1
        assert records[0].full_name == "Alice"

    def test_returns_empty_on_invalid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("{invalid json content", encoding="utf-8")

        records = ATSAdapter().extract(str(path))
        assert records == []

    def test_returns_empty_on_nonexistent_file(self) -> None:
        records = ATSAdapter().extract("/nonexistent/path.json")
        assert records == []

    def test_source_type_property(self) -> None:
        assert ATSAdapter().source_type == SourceType.ATS_JSON

    def test_handles_skills_as_string(self, tmp_path: Path) -> None:
        data = {"applicant_name": "Alice", "skills_list": "Python, ML, Go"}
        path = self._write_json(tmp_path, data)

        records = ATSAdapter().extract(str(path))
        assert len(records) == 1
        assert "Python" in records[0].skills
        assert "ML" in records[0].skills
