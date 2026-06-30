"""
Comprehensive tests for normalizer functions.

Tests are organized by normalizer module with parametrized cases
covering:
    - Standard valid inputs
    - Edge cases (empty strings, None, whitespace)
    - Malformed inputs (garbage text, partial formats)
    - Deduplication in batch functions
"""

from __future__ import annotations

import pytest

from normalizers.phone import normalize_phone, normalize_phones
from normalizers.date import normalize_date, normalize_dates_in_experience
from normalizers.location import normalize_country, parse_location
from normalizers.skills import normalize_skill, normalize_skills


# ===================================================================
# Phone Normalizer Tests
# ===================================================================


class TestNormalizePhone:
    """Unit tests for ``normalize_phone``."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            # Standard US formats
            ("(555) 867-5309", "+15558675309"),
            ("555-867-5309", "+15558675309"),
            ("555.867.5309", "+15558675309"),
            ("5558675309", "+15558675309"),
            ("+1 555 867 5309", "+15558675309"),
            ("+15558675309", "+15558675309"),

            # International formats
            ("+91-98765-43210", "+919876543210"),
            ("+44 20 7946 0958", "+442079460958"),

            # With extra whitespace
            ("  (555) 867-5309  ", "+15558675309"),
        ],
        ids=[
            "parens-dash", "dash-only", "dots", "digits-only",
            "plus-spaces", "e164-already",
            "india", "uk",
            "whitespace-padded",
        ],
    )
    def test_valid_phones(self, raw: str, expected: str) -> None:
        assert normalize_phone(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            None,
            "",
            "   ",
            "not-a-phone",
            "abc",
            "12",  # too short
        ],
        ids=["none", "empty", "whitespace", "garbage", "letters", "too-short"],
    )
    def test_invalid_phones_return_none(self, raw: str | None) -> None:
        assert normalize_phone(raw) is None


class TestNormalizePhones:
    """Unit tests for ``normalize_phones`` (batch + dedup)."""

    def test_deduplication(self) -> None:
        """Same number in different formats should produce one result."""
        raw_list = ["(555) 867-5309", "+15558675309", "555-867-5309"]
        result = normalize_phones(raw_list)
        assert result == ["+15558675309"]

    def test_mixed_valid_and_invalid(self) -> None:
        """Invalid entries are silently dropped."""
        raw_list = ["(555) 867-5309", "garbage", "+91-98765-43210"]
        result = normalize_phones(raw_list)
        assert "+15558675309" in result
        assert "+919876543210" in result
        assert len(result) == 2

    def test_empty_list(self) -> None:
        assert normalize_phones([]) == []


# ===================================================================
# Date Normalizer Tests
# ===================================================================


class TestNormalizeDate:
    """Unit tests for ``normalize_date``."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            # Month name + year
            ("January 2022", "2022-01"),
            ("Jan 2022", "2022-01"),
            ("december 2023", "2023-12"),
            ("Feb. 2024", "2024-02"),

            # Numeric month/year
            ("01/2022", "2022-01"),
            ("12-2023", "2023-12"),
            ("06.2024", "2024-06"),

            # ISO format
            ("2022-01-15", "2022-01"),
            ("2022-01", "2022-01"),

            # Year only
            ("2022", "2022"),

            # Present tokens
            ("Present", "Present"),
            ("current", "Present"),
            ("Now", "Present"),
            ("ongoing", "Present"),
        ],
        ids=[
            "month-name-full", "month-name-short", "month-name-lower",
            "month-name-dot",
            "numeric-slash", "numeric-dash", "numeric-dot",
            "iso-full", "iso-month",
            "year-only",
            "present-cap", "current-lower", "now-cap", "ongoing-lower",
        ],
    )
    def test_valid_dates(self, raw: str, expected: str) -> None:
        assert normalize_date(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [None, "", "   ", "garbage", "not-a-date"],
        ids=["none", "empty", "whitespace", "garbage", "text"],
    )
    def test_invalid_dates_return_none(self, raw: str | None) -> None:
        assert normalize_date(raw) is None


class TestNormalizeDatesInExperience:
    """Tests for ``normalize_dates_in_experience``."""

    def test_normalizes_both_dates(self) -> None:
        exp = [{"company": "Google", "start_date": "Jan 2020", "end_date": "Present"}]
        result = normalize_dates_in_experience(exp)
        assert result[0]["start_date"] == "2020-01"
        assert result[0]["end_date"] == "Present"

    def test_handles_missing_dates(self) -> None:
        exp = [{"company": "Google"}]
        result = normalize_dates_in_experience(exp)
        assert "start_date" not in result[0]

    def test_empty_list(self) -> None:
        assert normalize_dates_in_experience([]) == []


# ===================================================================
# Location Normalizer Tests
# ===================================================================


class TestNormalizeCountry:
    """Unit tests for ``normalize_country``."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("United States", "US"),
            ("USA", "US"),
            ("usa", "US"),
            ("US", "US"),
            ("India", "IN"),
            ("United Kingdom", "GB"),
            ("UK", "GB"),
            ("Canada", "CA"),
            ("Germany", "DE"),
        ],
        ids=[
            "full-name", "abbreviation-upper", "abbreviation-lower",
            "iso-code", "india", "uk-full", "uk-short", "canada", "germany",
        ],
    )
    def test_valid_countries(self, raw: str, expected: str) -> None:
        assert normalize_country(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [None, "", "   ", "Narnia", "unknown-place"],
        ids=["none", "empty", "whitespace", "fantasy", "unknown"],
    )
    def test_unknown_countries_return_none(self, raw: str | None) -> None:
        assert normalize_country(raw) is None


class TestParseLocation:
    """Unit tests for ``parse_location``."""

    def test_city_comma_country(self) -> None:
        loc = parse_location("San Francisco, US")
        assert loc.city == "San Francisco"
        assert loc.country_code == "US"

    def test_city_comma_country_name(self) -> None:
        loc = parse_location("Bangalore, India")
        assert loc.city == "Bangalore"
        assert loc.country_code == "IN"

    def test_city_comma_state(self) -> None:
        loc = parse_location("San Francisco, California")
        assert loc.city == "San Francisco"
        assert loc.country_code == "US"

    def test_city_comma_state_abbr(self) -> None:
        loc = parse_location("New York, NY")
        assert loc.city == "New York"
        assert loc.country_code == "US"

    def test_city_space_country(self) -> None:
        """No comma — last word is tested as a country."""
        loc = parse_location("San Francisco US")
        assert loc.city == "San Francisco"
        assert loc.country_code == "US"

    def test_known_city_alone(self) -> None:
        loc = parse_location("Bangalore")
        assert loc.city == "Bangalore"
        assert loc.country_code == "IN"

    def test_country_alone(self) -> None:
        loc = parse_location("India")
        assert loc.country_code == "IN"

    def test_none_input(self) -> None:
        loc = parse_location(None)
        assert loc.country_code is None
        assert loc.city is None

    def test_empty_string(self) -> None:
        loc = parse_location("")
        assert loc.country_code is None


# ===================================================================
# Skill Normalizer Tests
# ===================================================================


class TestNormalizeSkill:
    """Unit tests for ``normalize_skill``."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("ML", "Machine Learning"),
            ("machine learning", "Machine Learning"),
            ("Machine-Learning", "Machine Learning"),
            ("Python3", "Python"),
            ("python", "Python"),
            ("reactjs", "React"),
            ("React.js", "React"),
            ("JS", "JavaScript"),
            ("k8s", "Kubernetes"),
            ("tensorflow", "TensorFlow"),
            ("sklearn", "scikit-learn"),
            ("gcp", "GCP"),
            ("aws", "AWS"),
        ],
        ids=[
            "ml-abbrev", "ml-lower", "ml-hyphen",
            "python3", "python-lower",
            "reactjs", "react-dot-js",
            "js", "k8s", "tensorflow", "sklearn", "gcp", "aws",
        ],
    )
    def test_known_aliases(self, raw: str, expected: str) -> None:
        assert normalize_skill(raw) == expected

    def test_unknown_skill_title_cased(self) -> None:
        """Unknown skills should be title-cased, not dropped."""
        assert normalize_skill("some-unknown-skill") == "Some-Unknown-Skill"

    @pytest.mark.parametrize(
        "raw",
        [None, "", "   "],
        ids=["none", "empty", "whitespace"],
    )
    def test_invalid_returns_none(self, raw: str | None) -> None:
        assert normalize_skill(raw) is None


class TestNormalizeSkills:
    """Unit tests for ``normalize_skills`` (batch + dedup)."""

    def test_deduplication(self) -> None:
        """Same skill in different forms should appear once."""
        result = normalize_skills(["Python", "python3", "ML", "Machine Learning"])
        assert result == ["Python", "Machine Learning"]

    def test_preserves_order(self) -> None:
        """First occurrence is kept."""
        result = normalize_skills(["ML", "Python", "machine learning"])
        assert result[0] == "Machine Learning"
        assert result[1] == "Python"

    def test_empty_list(self) -> None:
        assert normalize_skills([]) == []

    def test_mixed_known_and_unknown(self) -> None:
        result = normalize_skills(["Python", "SomeFramework", "JS"])
        assert "Python" in result
        assert "Someframework" in result
        assert "JavaScript" in result
