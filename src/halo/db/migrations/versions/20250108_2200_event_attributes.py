"""Add EVENT entity type and event_attributes table.

Revision ID: 20250108_2200_event
Revises: 20250108_2100_ontology_support
Create Date: 2025-01-08

Adds:
- EVENT to entity_type_enum
- onto_event_attributes table for event-specific attributes
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY


# revision identifiers
revision = "20250108_2200_event"
down_revision = "20250108_2100_ontology_support"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add EVENT to entity type enum
    op.execute("ALTER TYPE entity_type_enum ADD VALUE IF NOT EXISTS 'EVENT'")

    # Create event_attributes table
    op.create_table(
        "onto_event_attributes",
        sa.Column(
            "entity_id",
            UUID(as_uuid=True),
            sa.ForeignKey("onto_entities.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        # Event classification
        sa.Column("event_type", sa.String(50), nullable=False),  # REGISTRATION, DIRECTOR_CHANGE, etc.
        sa.Column("event_subtype", sa.String(50), nullable=True),
        # Temporal
        sa.Column("event_date", sa.Date, nullable=False),
        sa.Column("event_timestamp", sa.DateTime(timezone=True), nullable=True),
        # Source document
        sa.Column("source_document_id", UUID(as_uuid=True), nullable=True),
        sa.Column("source_reference", sa.Text, nullable=True),
        # Related entities
        sa.Column("involved_entity_ids", ARRAY(UUID(as_uuid=True)), nullable=True),
        # Event-specific data (flexible)
        sa.Column("event_data", JSONB, nullable=True, server_default="{}"),
        # Risk indicators
        sa.Column("risk_score", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("risk_indicators", ARRAY(sa.Text), nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Create indexes
    op.create_index(
        "ix_onto_event_attributes_event_type",
        "onto_event_attributes",
        ["event_type"],
    )
    op.create_index(
        "ix_onto_event_attributes_event_date",
        "onto_event_attributes",
        ["event_date"],
    )
    op.create_index(
        "ix_onto_event_attributes_risk_score",
        "onto_event_attributes",
        ["risk_score"],
    )

    # Add comment
    op.execute(
        """
        COMMENT ON TABLE onto_event_attributes IS
        'Event-specific attributes for EVENT entity type. Events represent temporal occurrences like company registrations, director changes, or transactions.';
        """
    )


def downgrade() -> None:
    op.drop_index("ix_onto_event_attributes_risk_score")
    op.drop_index("ix_onto_event_attributes_event_date")
    op.drop_index("ix_onto_event_attributes_event_type")
    op.drop_table("onto_event_attributes")
    # Note: Cannot easily remove enum value in PostgreSQL
