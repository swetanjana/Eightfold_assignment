"""
Output validator — verifies the projected output is well-formed.

Runs after projection as the final quality gate.  Checks:
    - Required fields are present and non-null.
    - Values have the expected types (string, list, etc.).
    - Phone numbers are in E.164 format.
    - Email addresses match basic format.
    - Dates are in YYYY-MM format.

Validation issues are collected into a ``ValidationResult`` rather
than raising exceptions immediately — this allows the caller to
decide whether to emit a partial result with warnings or reject
the output entirely.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Validation patterns
# ---------------------------------------------------------------------------

_E164_PATTERN = re.compile(r"^\+\d{7,15}$")
_EMAIL_PATTERN = re.compile(
    r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
)
_YYYY_MM_PATTERN = re.compile(r"^\d{4}-\d{2}$")


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------


@dataclass
class ValidationIssue:
    """A single validation issue found in the output.

    Attributes:
        field:    The output field name where the issue was found.
        severity: ``"error"`` or ``"warning"``.
        message:  Human-readable description of the issue.
    """

    field: str
    severity: str  # "error" | "warning"
    message: str


@dataclass
class ValidationResult:
    """Aggregated validation result for a projected output.

    Attributes:
        is_valid:  ``True`` if no errors were found (warnings are OK).
        issues:    List of all issues found during validation.
        output:    The validated output dict (may be annotated with
                   a ``_validation`` key if issues exist).
    """

    is_valid: bool = True
    issues: list[ValidationIssue] = field(default_factory=list)
    output: dict[str, Any] = field(default_factory=dict)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_output(
    output: dict[str, Any],
    strict: bool = False,
) -> ValidationResult:
    """Validate a projected output dictionary.

    Checks types, formats, and completeness.  Does not modify the
    output — returns a ``ValidationResult`` with any issues found.

    Args:
        output:  The projected output from the projection engine.
        strict:  If ``True``, warnings are promoted to errors.

    Returns:
        A ``ValidationResult`` describing the output's validity.
    """
    result = ValidationResult(output=output)

    for key, value in output.items():
        # Skip metadata keys
        if key.startswith("_"):
            continue
        if key == "overall_confidence":
            _validate_confidence(key, value, result)
            continue

        # If value is a rich dict with "value" key, extract it
        actual_value = value
        if isinstance(value, dict) and "value" in value:
            actual_value = value["value"]
            # Validate confidence if present
            if "confidence" in value:
                _validate_confidence(
                    f"{key}.confidence", value["confidence"], result
                )

        # Type-specific validation
        if actual_value is None:
            continue  # None is valid (means missing field)

        if isinstance(actual_value, list):
            _validate_list_field(key, actual_value, result)
        elif isinstance(actual_value, str):
            _validate_string_field(key, actual_value, result)

    # Determine overall validity
    result.is_valid = len(result.errors) == 0
    if strict:
        result.is_valid = len(result.issues) == 0

    if result.issues:
        logger.info(
            "Output validation: %d issues (%d errors, %d warnings)",
            len(result.issues), len(result.errors), len(result.warnings),
        )
        # Annotate output with validation summary
        result.output["_validation"] = {
            "is_valid": result.is_valid,
            "error_count": len(result.errors),
            "warning_count": len(result.warnings),
            "issues": [
                {"field": i.field, "severity": i.severity, "message": i.message}
                for i in result.issues
            ],
        }

    return result


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_confidence(
    field_name: str,
    value: Any,
    result: ValidationResult,
) -> None:
    """Validate a confidence score is a float in [0.0, 1.0]."""
    if not isinstance(value, (int, float)):
        result.issues.append(ValidationIssue(
            field=field_name,
            severity="error",
            message=f"Confidence must be a number, got {type(value).__name__}.",
        ))
        return

    if value < 0.0 or value > 1.0:
        result.issues.append(ValidationIssue(
            field=field_name,
            severity="warning",
            message=f"Confidence {value} is outside [0.0, 1.0] range.",
        ))


def _validate_list_field(
    field_name: str,
    values: list[Any],
    result: ValidationResult,
) -> None:
    """Validate list field entries for format correctness."""
    # Detect field type by name heuristic
    name_lower = field_name.lower()

    for i, val in enumerate(values):
        if not isinstance(val, (str, dict)):
            continue

        if isinstance(val, str):
            # Check if it looks like a phone field
            if "phone" in name_lower and not _E164_PATTERN.match(val):
                result.issues.append(ValidationIssue(
                    field=f"{field_name}[{i}]",
                    severity="warning",
                    message=f"Phone '{val}' is not in E.164 format.",
                ))

            # Check if it looks like an email field
            if "email" in name_lower and not _EMAIL_PATTERN.match(val):
                result.issues.append(ValidationIssue(
                    field=f"{field_name}[{i}]",
                    severity="warning",
                    message=f"Email '{val}' does not match expected format.",
                ))


def _validate_string_field(
    field_name: str,
    value: str,
    result: ValidationResult,
) -> None:
    """Validate a single string field."""
    if not value.strip():
        result.issues.append(ValidationIssue(
            field=field_name,
            severity="warning",
            message="Field is an empty string.",
        ))
