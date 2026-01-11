"""Initial schema for Halo platform

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum types
    op.execute("CREATE TYPE entitytype AS ENUM ('person', 'company', 'property', 'vehicle')")
    op.execute(
        """CREATE TYPE relationshiptype AS ENUM (
            'owner', 'board_member', 'ceo', 'employee', 'beneficial_owner',
            'family', 'spouse', 'business_partner',
            'subsidiary', 'parent', 'supplier', 'customer',
            'owns_property', 'registered_at', 'owns_vehicle'
        )"""
    )

    # Create entities table
    op.create_table(
        "entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "entity_type",
            sa.Enum(
                "person",
                "company",
                "property",
                "vehicle",
                name="entitytype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("personnummer", sa.String(12), unique=True, index=True),
        sa.Column("organisationsnummer", sa.String(12), unique=True, index=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("attributes", postgresql.JSONB, server_default="{}"),
        sa.Column("sources", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    # Create cases table (needed before audit_log due to FK)
    op.create_table(
        "cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_number", sa.String(50), unique=True, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("status", sa.String(20), server_default="open"),
        sa.Column("assigned_to", sa.String(100)),
        sa.Column("entity_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), server_default="{}"),
        sa.Column("alert_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), server_default="{}"),
        sa.Column("notes", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime),
    )

    # Create entity_relationships table
    op.create_table(
        "entity_relationships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "from_entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("entities.id"),
            nullable=False,
        ),
        sa.Column(
            "to_entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("entities.id"),
            nullable=False,
        ),
        sa.Column(
            "relationship_type",
            sa.Enum(
                "owner",
                "board_member",
                "ceo",
                "employee",
                "beneficial_owner",
                "family",
                "spouse",
                "business_partner",
                "subsidiary",
                "parent",
                "supplier",
                "customer",
                "owns_property",
                "registered_at",
                "owns_vehicle",
                name="relationshiptype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("attributes", postgresql.JSONB, server_default="{}"),
        sa.Column("confidence", sa.Float, server_default="1.0"),
        sa.Column("valid_from", sa.DateTime),
        sa.Column("valid_to", sa.DateTime),
        sa.Column("source", sa.String(100)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_relationships_from", "entity_relationships", ["from_entity_id"])
    op.create_index("idx_relationships_to", "entity_relationships", ["to_entity_id"])
    op.create_index("idx_relationships_type", "entity_relationships", ["relationship_type"])

    # Create documents table
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(500)),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("source_url", sa.Text),
        sa.Column("document_type", sa.String(50)),
        sa.Column("raw_text", sa.Text, nullable=False),
        sa.Column("language", sa.String(10), server_default="sv"),
        sa.Column("entities_extracted", postgresql.JSONB, server_default="{}"),
        sa.Column("sentiment_scores", postgresql.JSONB, server_default="{}"),
        sa.Column("threat_indicators", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("summary", sa.Text),
        sa.Column("processed", sa.Boolean, server_default="false"),
        sa.Column("processed_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    # Create document_entity_mentions table
    op.create_table(
        "document_entity_mentions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id"),
            nullable=False,
        ),
        sa.Column(
            "entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("entities.id"),
            nullable=False,
        ),
        sa.Column("start_char", sa.Integer),
        sa.Column("end_char", sa.Integer),
        sa.Column("mention_text", sa.String(500)),
        sa.Column("confidence", sa.Float, server_default="1.0"),
    )

    # Create transactions table
    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("transaction_id", sa.String(100), unique=True, index=True),
        sa.Column("timestamp", sa.DateTime, nullable=False, index=True),
        sa.Column("from_entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("entities.id")),
        sa.Column("to_entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("entities.id")),
        sa.Column("from_account", sa.String(50)),
        sa.Column("to_account", sa.String(50)),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("currency", sa.String(3), server_default="SEK"),
        sa.Column("transaction_type", sa.String(50)),
        sa.Column("description", sa.Text),
        sa.Column("risk_score", sa.Float),
        sa.Column("risk_factors", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_transactions_timestamp", "transactions", ["timestamp"])
    op.create_index("idx_transactions_from", "transactions", ["from_entity_id"])
    op.create_index("idx_transactions_to", "transactions", ["to_entity_id"])

    # Create alerts table
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("entity_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), server_default="{}"),
        sa.Column("transaction_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), server_default="{}"),
        sa.Column("confidence", sa.Float, nullable=False),
        # Human-in-loop compliance fields
        sa.Column("tier", sa.Integer, server_default="2"),
        sa.Column("affects_person", sa.Boolean, server_default="true"),
        sa.Column("acknowledged_by", sa.String(100)),
        sa.Column("acknowledged_at", sa.DateTime),
        sa.Column("approved_by", sa.String(100)),
        sa.Column("approved_at", sa.DateTime),
        sa.Column("approval_decision", sa.String(20)),
        sa.Column("approval_justification", sa.Text),
        sa.Column("review_displayed_at", sa.DateTime),
        sa.Column("review_duration_seconds", sa.Float),
        # Legacy fields
        sa.Column("status", sa.String(20), server_default="open"),
        sa.Column("resolution_notes", sa.Text),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_alerts_status", "alerts", ["status"])
    op.create_index("idx_alerts_severity", "alerts", ["severity"])
    op.create_index("idx_alerts_tier", "alerts", ["tier"])
    op.create_index(
        "idx_alerts_pending_review", "alerts", ["tier", "acknowledged_at", "approved_at"]
    )

    # Create audit_log table
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(100), nullable=False),
        sa.Column("user_name", sa.String(255), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True)),
        sa.Column("details", postgresql.JSONB, server_default="{}"),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id")),
        sa.Column("justification", sa.Text),
        sa.Column("timestamp", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("user_agent", sa.String(500)),
    )
    op.create_index("idx_audit_user", "audit_log", ["user_id"])
    op.create_index("idx_audit_timestamp", "audit_log", ["timestamp"])
    op.create_index("idx_audit_resource", "audit_log", ["resource_type", "resource_id"])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table("audit_log")
    op.drop_table("alerts")
    op.drop_table("transactions")
    op.drop_table("document_entity_mentions")
    op.drop_table("documents")
    op.drop_table("entity_relationships")
    op.drop_table("cases")
    op.drop_table("entities")

    # Drop enum types
    op.execute("DROP TYPE relationshiptype")
    op.execute("DROP TYPE entitytype")
