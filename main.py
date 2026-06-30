"""
Multi-Source Candidate Data Transformer
========================================

CLI entry point and pipeline orchestrator.

Pipeline stages (executed in order):
    1. Detect source files in the input directory.
    2. Extract raw candidate records using source-specific adapters.
    3. Normalize all fields (phone → E.164, date → YYYY-MM, etc.).
    4. Resolve entities — group records describing the same candidate.
    5. Merge each group into one canonical profile with provenance.
    6. Score confidence — per-field and overall.
    7. Project the canonical profile using the runtime configuration.
    8. Validate the projected output.
    9. Emit JSON to the output directory.

Usage:
    python main.py --input-dir sample_inputs/ --config sample_configs/default_config.json
    python main.py --input-dir sample_inputs/ --config sample_configs/custom_config.json --output-dir output/
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import click

from adapters import get_adapter
from engine.confidence import score_profile
from engine.merger import merge_cluster
from engine.projector import ProjectionError, project
from engine.resolver import resolve_entities
from normalizers import normalize_record
from schema.canonical import RawCandidateRecord
from schema.config import ProjectionConfig
from validators.output_validator import validate_output

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pipeline")


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------


def _discover_sources(input_dir: Path) -> list[Path]:
    """Find all supported source files in the input directory.

    Supported extensions: .csv, .json, .pdf, .txt
    """
    supported = {".csv", ".json", ".pdf", ".txt"}
    sources = sorted(
        p for p in input_dir.iterdir()
        if p.is_file() and p.suffix.lower() in supported
    )
    logger.info("Discovered %d source files in %s", len(sources), input_dir)
    for s in sources:
        logger.info("  -> %s", s.name)
    return sources


def _extract_all(sources: list[Path]) -> tuple[list[RawCandidateRecord], list[str]]:
    """Extract raw records from all source files.

    Returns:
        A tuple of (records, failed_sources).
    """
    all_records: list[RawCandidateRecord] = []
    failed_sources: list[str] = []

    for source_path in sources:
        adapter = get_adapter(source_path)
        if adapter is None:
            logger.warning("No adapter for file type: %s", source_path.suffix)
            failed_sources.append(str(source_path))
            continue

        try:
            records = adapter.extract(str(source_path))
            all_records.extend(records)
            logger.info(
                "Extracted %d records from %s (%s)",
                len(records), source_path.name, adapter.source_type.value,
            )
        except Exception:
            logger.exception("Adapter failed for %s", source_path)
            failed_sources.append(str(source_path))

    return all_records, failed_sources


def _normalize_all(records: list[RawCandidateRecord]) -> list[RawCandidateRecord]:
    """Apply normalization to all raw records."""
    normalized = []
    for record in records:
        try:
            normalized.append(normalize_record(record))
        except Exception:
            logger.exception(
                "Normalization failed for record from %s — skipping",
                record.source_path,
            )
    logger.info("Normalized %d / %d records", len(normalized), len(records))
    return normalized


def _load_config(config_path: Path) -> ProjectionConfig:
    """Load and validate the runtime projection configuration."""
    with open(config_path, encoding="utf-8") as f:
        raw = json.load(f)
    config = ProjectionConfig.model_validate(raw)
    logger.info(
        "Loaded config: %d fields, on_missing=%s",
        len(config.fields), config.on_missing,
    )
    return config


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.option(
    "--input-dir",
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="Directory containing source files (CSV, JSON, PDF).",
)
@click.option(
    "--config",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to the runtime projection configuration JSON.",
)
@click.option(
    "--output-dir",
    default="output",
    type=click.Path(file_okay=False),
    help="Directory to write output JSON files. Created if it doesn't exist.",
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    default=False,
    help="Enable debug logging.",
)
def main(input_dir: str, config: str, output_dir: str, verbose: bool) -> None:
    """Multi-Source Candidate Data Transformer.

    Ingests candidate profiles from multiple structured and unstructured
    sources, normalizes fields, resolves entities, merges into canonical
    profiles with provenance and confidence, and projects output according
    to the provided runtime configuration.
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    input_path = Path(input_dir)
    config_path = Path(config)
    output_path = Path(output_dir)

    click.echo("=" * 60)
    click.echo("  Multi-Source Candidate Data Transformer")
    click.echo("=" * 60)
    click.echo()

    # --- Stage 1: Load configuration ---
    click.echo("> Loading projection configuration...")
    try:
        proj_config = _load_config(config_path)
    except Exception as e:
        click.echo(f"[X] Failed to load config: {e}", err=True)
        sys.exit(1)

    # --- Stage 2: Discover sources ---
    click.echo("> Discovering source files...")
    sources = _discover_sources(input_path)
    if not sources:
        click.echo("[X] No supported source files found.", err=True)
        sys.exit(1)

    # --- Stage 3: Extract ---
    click.echo("> Extracting raw records...")
    raw_records, failed_sources = _extract_all(sources)
    click.echo(f"  Extracted {len(raw_records)} records ({len(failed_sources)} sources failed)")

    if not raw_records:
        click.echo("[X] No records extracted from any source.", err=True)
        sys.exit(1)

    # --- Stage 4: Normalize ---
    click.echo("> Normalizing fields...")
    normalized_records = _normalize_all(raw_records)

    # --- Stage 5: Resolve entities ---
    click.echo("> Resolving entities...")
    clusters = resolve_entities(normalized_records)
    click.echo(f"  Identified {len(clusters)} unique candidates")

    # --- Stage 6: Merge ---
    click.echo("> Merging profiles...")
    profiles = []
    for cluster in clusters:
        profile = merge_cluster(cluster)
        profile.sources_failed = failed_sources
        profiles.append(profile)

    # --- Stage 7: Score confidence ---
    click.echo("> Scoring confidence...")
    profiles = [score_profile(p) for p in profiles]

    # --- Stage 8: Project ---
    click.echo("> Projecting output...")
    projected_outputs: list[dict[str, Any]] = []
    for profile in profiles:
        try:
            output = project(profile, proj_config)
            projected_outputs.append(output)
        except ProjectionError as e:
            click.echo(f"  [!] Projection failed for profile {profile.id[:8]}: {e}")

    # --- Stage 9: Validate ---
    click.echo("> Validating output...")
    validated_outputs: list[dict[str, Any]] = []
    for output in projected_outputs:
        result = validate_output(output)
        validated_outputs.append(result.output)
        if not result.is_valid:
            click.echo(f"  [!] Validation issues: {len(result.errors)} errors, {len(result.warnings)} warnings")

    # --- Stage 10: Emit ---
    click.echo("> Writing output...")
    output_path.mkdir(parents=True, exist_ok=True)

    # Write individual profiles
    for i, output in enumerate(validated_outputs):
        filename = f"candidate_{i + 1}.json"
        filepath = output_path / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False, default=str)
        click.echo(f"  -> {filepath}")

    # Write combined output
    combined_path = output_path / "all_candidates.json"
    with open(combined_path, "w", encoding="utf-8") as f:
        json.dump(validated_outputs, f, indent=2, ensure_ascii=False, default=str)
    click.echo(f"  -> {combined_path}")

    click.echo()
    click.echo("=" * 60)
    click.echo(f"  [OK] Pipeline complete: {len(validated_outputs)} profiles emitted")
    click.echo("=" * 60)


if __name__ == "__main__":
    main()
