"""
Adapters package — source-specific data extraction.

Each adapter reads one source format and produces a list of
``RawCandidateRecord`` objects.  Adapters do NOT normalize,
merge, score, or project data.  Their only job is extraction.

The ``get_adapter`` factory function selects the correct adapter
based on file extension.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from adapters.base import BaseAdapter
from adapters.csv_adapter import CSVAdapter
from adapters.ats_adapter import ATSAdapter
from adapters.resume_adapter import ResumeAdapter
from utils.constants import EXTENSION_SOURCE_MAP, SourceType


_ADAPTER_REGISTRY: dict[SourceType, type[BaseAdapter]] = {
    SourceType.CSV: CSVAdapter,
    SourceType.ATS_JSON: ATSAdapter,
    SourceType.RESUME_PDF: ResumeAdapter,
}


def get_adapter(file_path: str | Path) -> Optional[BaseAdapter]:
    """Return the appropriate adapter for a given file path.

    Args:
        file_path: Path to the source file.

    Returns:
        An adapter instance, or ``None`` if the file type is not supported.
    """
    ext = Path(file_path).suffix.lower()
    source_type = EXTENSION_SOURCE_MAP.get(ext)
    if source_type is None:
        return None
    adapter_cls = _ADAPTER_REGISTRY.get(source_type)
    if adapter_cls is None:
        return None
    return adapter_cls()
