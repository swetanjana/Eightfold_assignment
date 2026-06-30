"""
Entity resolution — grouping raw records that describe the same candidate.

Before merging, we must answer: "Which of these records describe the
same person?"  This module groups ``RawCandidateRecord`` objects into
clusters where each cluster represents one unique candidate.

Match key strategy:
    1. **Email (primary)**: Two records sharing any email address are
       the same person.  Email is the strongest match key because
       it is nearly unique to an individual.
    2. **Phone (secondary)**: If emails don't overlap, two records
       sharing a phone number are the same person.

We deliberately avoid matching on name alone — common names (e.g.
"Alex Johnson") would cause false merges across unrelated candidates.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from schema.canonical import RawCandidateRecord

logger = logging.getLogger(__name__)


def resolve_entities(
    records: list[RawCandidateRecord],
) -> list[list[RawCandidateRecord]]:
    """Group raw records into candidate clusters.

    Records sharing any email or phone are placed in the same cluster.
    Records with no matching keys become singleton clusters.

    Uses a union-find (disjoint set) approach to handle transitive
    matches: if record A shares an email with B, and B shares a phone
    with C, then A, B, and C are all the same candidate.

    Args:
        records: List of raw candidate records from all sources.

    Returns:
        A list of clusters, where each cluster is a list of records
        that describe the same candidate.

    Examples:
        >>> from schema.canonical import RawCandidateRecord
        >>> from utils.constants import SourceType
        >>> r1 = RawCandidateRecord(SourceType.CSV, "a.csv", emails=["x@y.com"])
        >>> r2 = RawCandidateRecord(SourceType.ATS_JSON, "b.json", emails=["x@y.com"])
        >>> r3 = RawCandidateRecord(SourceType.CSV, "c.csv", emails=["z@y.com"])
        >>> groups = resolve_entities([r1, r2, r3])
        >>> len(groups)
        2
    """
    if not records:
        return []

    n = len(records)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]  # path compression
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    # Build indexes: key → list of record indices
    email_index: dict[str, list[int]] = defaultdict(list)
    phone_index: dict[str, list[int]] = defaultdict(list)

    for idx, record in enumerate(records):
        for email in record.emails:
            key = email.strip().lower()
            if key:
                email_index[key].append(idx)

        for phone in record.phones:
            key = phone.strip()
            if key:
                phone_index[key].append(idx)

    # Union records that share an email
    for indices in email_index.values():
        for i in range(1, len(indices)):
            union(indices[0], indices[i])

    # Union records that share a phone
    for indices in phone_index.values():
        for i in range(1, len(indices)):
            union(indices[0], indices[i])

    # Group records by their root parent
    clusters: dict[int, list[int]] = defaultdict(list)
    for idx in range(n):
        root = find(idx)
        clusters[root].append(idx)

    result = [
        [records[idx] for idx in group]
        for group in clusters.values()
    ]

    logger.info(
        "Entity resolution: %d records → %d unique candidates",
        n, len(result),
    )
    return result
