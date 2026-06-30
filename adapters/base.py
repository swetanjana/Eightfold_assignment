"""
Abstract base class for all source adapters.

Every adapter inherits from ``BaseAdapter`` and implements the
``extract`` method.  This guarantees a uniform contract: the
orchestrator calls ``adapter.extract(path)`` without knowing
which adapter it's talking to.

Adding a new source type requires:
    1. Create a new file (e.g. ``linkedin_adapter.py``).
    2. Inherit from ``BaseAdapter``.
    3. Implement ``extract()`` and ``source_type``.
    4. Register it in ``adapters/__init__.py``.
    Zero changes to existing code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from schema.canonical import RawCandidateRecord
    from utils.constants import SourceType


class BaseAdapter(ABC):
    """Abstract base class for source-specific data extractors.

    Subclasses must implement:
        - ``extract(source_path)`` — read one source, return raw records.
        - ``source_type``          — the ``SourceType`` enum value.
    """

    @abstractmethod
    def extract(self, source_path: str) -> list[RawCandidateRecord]:
        """Read a source file and extract candidate records.

        Args:
            source_path: Absolute or relative path to the source file.

        Returns:
            A list of ``RawCandidateRecord`` objects — one per candidate
            found in the source.  Returns an empty list if the source
            cannot be parsed (never raises on bad input).
        """

    @property
    @abstractmethod
    def source_type(self) -> SourceType:
        """The source type this adapter handles."""
