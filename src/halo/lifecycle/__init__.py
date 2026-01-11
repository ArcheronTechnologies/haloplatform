"""
Entity lifecycle operations aligned with Archeron Ontology.

Provides operations for:
- Merge: Combine duplicate entities (creates SAME_AS relationship)
- Split: Separate incorrectly merged entities
- Anonymize: GDPR-compliant data erasure while preserving structure
"""

from halo.lifecycle.merge import EntityMerger, MergeResult
from halo.lifecycle.split import EntitySplitter, SplitResult
from halo.lifecycle.anonymize import EntityAnonymizer, AnonymizationResult

__all__ = [
    "EntityMerger",
    "MergeResult",
    "EntitySplitter",
    "SplitResult",
    "EntityAnonymizer",
    "AnonymizationResult",
]
