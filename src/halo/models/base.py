"""
Base class for Archeron Ontology ORM models.

This Base is separate from the legacy halo.db.Base to avoid
class name conflicts between legacy and ontology-aligned models.
"""

from sqlalchemy.orm import DeclarativeBase


class OntologyBase(DeclarativeBase):
    """Base class for all Archeron Ontology models.

    All ontology-aligned models (Entity, Fact, Mention, Provenance, etc.)
    use tables prefixed with 'onto_' to distinguish from legacy tables.
    """

    pass
