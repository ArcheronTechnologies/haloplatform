"""
Add ontology support tables.

Creates supporting tables for:
- Derivation rules (nightly computation configuration)
- Resolution configuration (auto-match thresholds)
- Validation ground truth (accuracy measurement)
- Alerts (real-time detection)

Revision ID: ontology_support_001
Revises: ontology_schema_001
Create Date: 2025-01-08 21:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'ontology_support_001'
down_revision: Union[str, None] = 'ontology_schema_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create derivation rule type enum
    op.execute("""
        CREATE TYPE derivation_rule_type AS ENUM (
            'RISK_SCORE', 'NETWORK_CLUSTER', 'SHELL_INDICATOR', 'VELOCITY', 'ADDRESS_STATS'
        )
    """)

    # Create ground truth type enum
    op.execute("""
        CREATE TYPE ground_truth_type AS ENUM (
            'PERSONNUMMER_MATCH', 'ORGNUMMER_MATCH', 'SYNTHETIC', 'EKOBROTTSMYNDIGHETEN'
        )
    """)

    # Derivation rules table - configures nightly derived fact computation
    op.create_table(
        'onto_derivation_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('rule_name', sa.Text(), nullable=False, unique=True),
        sa.Column('rule_type', sa.Enum('RISK_SCORE', 'NETWORK_CLUSTER', 'SHELL_INDICATOR', 'VELOCITY', 'ADDRESS_STATS',
                                       name='derivation_rule_type', create_type=False), nullable=False),
        sa.Column('rule_definition', postgresql.JSONB(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('idx_derivation_rules_active', 'onto_derivation_rules', ['rule_type'], postgresql_where=sa.text('active = TRUE'))

    # Resolution configuration - thresholds for auto-match/reject
    op.create_table(
        'onto_resolution_config',
        sa.Column('mention_type', sa.String(20), primary_key=True),
        sa.Column('auto_match_threshold', sa.Float(), nullable=False),
        sa.Column('human_review_min', sa.Float(), nullable=False),
        sa.Column('auto_reject_threshold', sa.Float(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint('auto_match_threshold > human_review_min', name='check_match_threshold'),
        sa.CheckConstraint('human_review_min >= auto_reject_threshold', name='check_review_threshold'),
    )

    # Insert default resolution thresholds per ontology spec
    op.execute("""
        INSERT INTO onto_resolution_config (mention_type, auto_match_threshold, human_review_min, auto_reject_threshold)
        VALUES
            ('PERSON', 0.95, 0.60, 0.60),
            ('COMPANY', 0.95, 0.60, 0.60),
            ('ADDRESS', 0.90, 0.50, 0.50)
    """)

    # Validation ground truth - for measuring resolution accuracy
    op.create_table(
        'onto_validation_ground_truth',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('ground_truth_type', sa.Enum('PERSONNUMMER_MATCH', 'ORGNUMMER_MATCH', 'SYNTHETIC', 'EKOBROTTSMYNDIGHETEN',
                                               name='ground_truth_type', create_type=False), nullable=False),
        sa.Column('entity_a_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('onto_entities.id'), nullable=False),
        sa.Column('entity_b_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('onto_entities.id'), nullable=False),
        sa.Column('is_same_entity', sa.Boolean(), nullable=False),
        sa.Column('source_reference', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_ground_truth_type', 'onto_validation_ground_truth', ['ground_truth_type'])

    # Alerts table - for real-time pattern detection
    op.create_table(
        'onto_alerts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('alert_type', sa.String(50), nullable=False),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('onto_entities.id'), nullable=False),
        sa.Column('risk_score', sa.Float(), nullable=False),
        sa.Column('alert_data', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('status', sa.String(20), nullable=False, server_default='NEW'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledged_by', sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('NEW', 'ACKNOWLEDGED', 'INVESTIGATED', 'DISMISSED')", name='check_alert_status'),
        sa.CheckConstraint('risk_score >= 0 AND risk_score <= 1', name='check_alert_risk_score'),
    )
    op.create_index('idx_alerts_new', 'onto_alerts', ['alert_type', 'created_at'], postgresql_where=sa.text("status = 'NEW'"))
    op.create_index('idx_alerts_entity', 'onto_alerts', ['entity_id'])

    # Derivation job runs - track nightly computation
    op.create_table(
        'onto_derivation_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='RUNNING'),
        sa.Column('entities_processed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('facts_created', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('errors', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('metrics', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.CheckConstraint("status IN ('RUNNING', 'COMPLETED', 'FAILED')", name='check_run_status'),
    )
    op.create_index('idx_derivation_runs_status', 'onto_derivation_runs', ['status', 'started_at'])

    # Insert default derivation rules
    op.execute("""
        INSERT INTO onto_derivation_rules (id, rule_name, rule_type, rule_definition, version, active)
        VALUES
            (gen_random_uuid(), 'person_risk_score', 'RISK_SCORE',
             '{"entity_type": "PERSON", "weights": {"high_velocity_director": 0.3, "shell_company_director": 0.4, "vulnerable_area": 0.2, "many_companies": 0.1}}',
             1, true),
            (gen_random_uuid(), 'company_risk_score', 'RISK_SCORE',
             '{"entity_type": "COMPANY", "weights": {"shell_indicators": 0.4, "high_director_turnover": 0.3, "no_employees": 0.2, "no_revenue": 0.1}}',
             1, true),
            (gen_random_uuid(), 'director_velocity', 'VELOCITY',
             '{"window_days": 365, "min_changes": 3}',
             1, true),
            (gen_random_uuid(), 'shell_company_indicators', 'SHELL_INDICATOR',
             '{"max_employees": 1, "max_revenue": 500000, "min_age_days": 365}',
             1, true),
            (gen_random_uuid(), 'address_registration_hub', 'ADDRESS_STATS',
             '{"min_companies": 10, "max_persons": 2}',
             1, true)
    """)


def downgrade() -> None:
    op.drop_table('onto_derivation_runs')
    op.drop_table('onto_alerts')
    op.drop_table('onto_validation_ground_truth')
    op.drop_table('onto_resolution_config')
    op.drop_table('onto_derivation_rules')

    op.execute("DROP TYPE IF EXISTS ground_truth_type")
    op.execute("DROP TYPE IF EXISTS derivation_rule_type")
