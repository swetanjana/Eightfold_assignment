"""
Engine package — core transformation logic.

Contains the pipeline's processing stages:
    - Entity resolution (grouping records by candidate identity)
    - Merge engine (conflict resolution + provenance)
    - Confidence scoring
    - Output projection
"""
