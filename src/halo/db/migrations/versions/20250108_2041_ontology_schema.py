"""
Add Archeron Ontology schema tables.

This migration creates the following ontology-aligned tables:
- onto_entities: Core entity table (persons, companies, addresses)
- onto_entity_identifiers: Entity identifiers (personnummer, orgnummer, etc.)
- onto_person_attributes: Person-specific attributes
- onto_company_attributes: Company-specific attributes
- onto_address_attributes: Address-specific attributes
- onto_facts: Assertions about entities with temporality
- onto_mentions: Raw observations before entity resolution
- onto_resolution_decisions: Resolution audit trail
- onto_provenances: Source and extraction tracking
- onto_source_authority: Source authority configuration
- onto_audit_log: Ontology-specific audit events

Revision ID: ontology_schema_001
Revises: 20250101_0001_initial_schema
Create Date: 2025-01-08 20:41:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'ontology_schema_001'
down_revision: Union[str, None] = None  # Set to initial migration revision if exists
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum types
    op.execute("CREATE TYPE entity_type_enum AS ENUM ('PERSON', 'COMPANY', 'ADDRESS')")
    op.execute("CREATE TYPE entity_status_enum AS ENUM ('ACTIVE', 'MERGED', 'SPLIT', 'ANONYMIZED')")
    op.execute("CREATE TYPE identifier_type_enum AS ENUM ('PERSONNUMMER', 'SAMORDNINGSNUMMER', 'ORGANISATIONSNUMMER', 'POSTAL_CODE', 'PROPERTY_ID')")
    op.execute("CREATE TYPE fact_type_enum AS ENUM ('ATTRIBUTE', 'RELATIONSHIP')")
    op.execute("CREATE TYPE resolution_status_enum AS ENUM ('PENDING', 'AUTO_MATCHED', 'HUMAN_MATCHED', 'AUTO_REJECTED', 'HUMAN_REJECTED')")
    op.execute("CREATE TYPE source_type_enum AS ENUM ('BOLAGSVERKET_HVD', 'BOLAGSVERKET_ANNUAL_REPORT', 'ALLABOLAG_SCRAPE', 'MANUAL_ENTRY', 'DERIVED_COMPUTATION')")
    op.execute("CREATE TYPE actor_type_enum AS ENUM ('SYSTEM', 'USER', 'API')")

    # onto_entities table
    op.create_table(
        'onto_entities',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('entity_type', sa.Enum('PERSON', 'COMPANY', 'ADDRESS', name='entity_type_enum', create_type=False), nullable=False),
        sa.Column('canonical_name', sa.Text(), nullable=False),
        sa.Column('resolution_confidence', sa.Float(), nullable=False, server_default='1.0'),
        sa.Column('status', sa.Enum('ACTIVE', 'MERGED', 'SPLIT', 'ANONYMIZED', name='entity_status_enum', create_type=False), nullable=False, server_default='ACTIVE'),
        sa.Column('merged_into', postgresql.UUID(as_uuid=True), sa.ForeignKey('onto_entities.id'), nullable=True),
        sa.Column('split_from', postgresql.UUID(as_uuid=True), sa.ForeignKey('onto_entities.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('anonymized_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('resolution_confidence >= 0 AND resolution_confidence <= 1', name='check_resolution_confidence'),
    )
    op.create_index('idx_entities_type', 'onto_entities', ['entity_type'], postgresql_where=sa.text("status = 'ACTIVE'"))
    op.create_index('idx_entities_merged', 'onto_entities', ['merged_into'], postgresql_where=sa.text('merged_into IS NOT NULL'))

    # onto_provenances table (needed before entity_identifiers and facts)
    op.create_table(
        'onto_provenances',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('source_type', sa.Enum('BOLAGSVERKET_HVD', 'BOLAGSVERKET_ANNUAL_REPORT', 'ALLABOLAG_SCRAPE', 'MANUAL_ENTRY', 'DERIVED_COMPUTATION', name='source_type_enum', create_type=False), nullable=False),
        sa.Column('source_id', sa.Text(), nullable=False),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('source_document_hash', sa.Text(), nullable=True),
        sa.Column('extraction_method', sa.Text(), nullable=False),
        sa.Column('extraction_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('extraction_system_version', sa.Text(), nullable=False),
        sa.Column('derived_from', postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True),
        sa.Column('derivation_rule', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_provenance_source', 'onto_provenances', ['source_type', 'source_id'])

    # onto_entity_identifiers table
    op.create_table(
        'onto_entity_identifiers',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('onto_entities.id'), nullable=False),
        sa.Column('identifier_type', sa.Enum('PERSONNUMMER', 'SAMORDNINGSNUMMER', 'ORGANISATIONSNUMMER', 'POSTAL_CODE', 'PROPERTY_ID', name='identifier_type_enum', create_type=False), nullable=False),
        sa.Column('identifier_value', sa.Text(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='1.0'),
        sa.Column('provenance_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('onto_provenances.id'), nullable=False),
        sa.Column('valid_from', sa.Date(), nullable=True),
        sa.Column('valid_to', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('entity_id', 'identifier_type', 'identifier_value', name='uq_entity_identifier'),
    )
    op.create_index('idx_identifiers_lookup', 'onto_entity_identifiers', ['identifier_type', 'identifier_value'])
    op.create_index('idx_identifiers_entity', 'onto_entity_identifiers', ['entity_id'])

    # onto_person_attributes table
    op.create_table(
        'onto_person_attributes',
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('onto_entities.id'), primary_key=True),
        sa.Column('birth_year', sa.Integer(), nullable=True),
        sa.Column('birth_date', sa.Date(), nullable=True),
        sa.Column('gender', sa.String(10), nullable=True),
        sa.Column('company_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('active_directorship_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('network_cluster_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('risk_score', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('risk_factors', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('first_seen', sa.Date(), nullable=True),
        sa.Column('last_activity', sa.Date(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.CheckConstraint('risk_score >= 0 AND risk_score <= 1', name='check_person_risk_score'),
    )

    # onto_company_attributes table
    op.create_table(
        'onto_company_attributes',
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('onto_entities.id'), primary_key=True),
        sa.Column('legal_form', sa.String(20), nullable=True),
        sa.Column('status', sa.String(30), nullable=False, server_default='UNKNOWN'),
        sa.Column('registration_date', sa.Date(), nullable=True),
        sa.Column('dissolution_date', sa.Date(), nullable=True),
        sa.Column('sni_codes', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('sni_primary', sa.String(10), nullable=True),
        sa.Column('latest_revenue', sa.Integer(), nullable=True),
        sa.Column('latest_employees', sa.Integer(), nullable=True),
        sa.Column('latest_assets', sa.Integer(), nullable=True),
        sa.Column('financial_year_end', sa.Date(), nullable=True),
        sa.Column('director_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('director_change_velocity', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('network_cluster_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('risk_score', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('risk_factors', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('shell_indicators', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('ownership_opacity_score', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('last_filing_date', sa.Date(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.CheckConstraint('risk_score >= 0 AND risk_score <= 1', name='check_company_risk_score'),
    )
    op.create_index('idx_company_status', 'onto_company_attributes', ['status'])
    op.create_index('idx_company_sni', 'onto_company_attributes', ['sni_primary'])
    op.create_index('idx_company_risk', 'onto_company_attributes', ['risk_score'], postgresql_where=sa.text('risk_score > 0.5'))

    # onto_address_attributes table
    op.create_table(
        'onto_address_attributes',
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('onto_entities.id'), primary_key=True),
        sa.Column('street', sa.Text(), nullable=False),
        sa.Column('street_number', sa.Text(), nullable=True),
        sa.Column('postal_code', sa.String(10), nullable=False),
        sa.Column('city', sa.Text(), nullable=False),
        sa.Column('municipality', sa.String(50), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('geocode_confidence', sa.Float(), nullable=True),
        sa.Column('vulnerable_area', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('vulnerability_level', sa.String(20), nullable=True),
        sa.Column('company_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('person_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_registration_hub', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('idx_address_postal', 'onto_address_attributes', ['postal_code'])
    op.create_index('idx_address_vulnerable', 'onto_address_attributes', ['vulnerable_area'], postgresql_where=sa.text("vulnerable_area = TRUE"))

    # onto_facts table
    op.create_table(
        'onto_facts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('fact_type', sa.Enum('ATTRIBUTE', 'RELATIONSHIP', name='fact_type_enum', create_type=False), nullable=False),
        sa.Column('subject_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('onto_entities.id'), nullable=False),
        sa.Column('predicate', sa.Text(), nullable=False),
        sa.Column('value_text', sa.Text(), nullable=True),
        sa.Column('value_int', sa.Integer(), nullable=True),
        sa.Column('value_float', sa.Float(), nullable=True),
        sa.Column('value_date', sa.Date(), nullable=True),
        sa.Column('value_bool', sa.Boolean(), nullable=True),
        sa.Column('value_json', postgresql.JSONB(), nullable=True),
        sa.Column('object_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('onto_entities.id'), nullable=True),
        sa.Column('relationship_attributes', postgresql.JSONB(), nullable=True),
        sa.Column('valid_from', sa.Date(), nullable=False),
        sa.Column('valid_to', sa.Date(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('provenance_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('onto_provenances.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('superseded_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('onto_facts.id'), nullable=True),
        sa.Column('superseded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_derived', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('derivation_rule', sa.Text(), nullable=True),
        sa.Column('derived_from', postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True),
        sa.CheckConstraint('confidence >= 0 AND confidence <= 1', name='check_fact_confidence'),
        sa.CheckConstraint("(fact_type != 'RELATIONSHIP') OR (object_id IS NOT NULL)", name='check_relationship_has_object'),
        sa.CheckConstraint("(fact_type != 'RELATIONSHIP') OR (predicate IN ('DIRECTOR_OF', 'SHAREHOLDER_OF', 'REGISTERED_AT', 'SAME_AS'))", name='check_valid_relationship_predicate'),
    )
    op.create_index('idx_facts_subject', 'onto_facts', ['subject_id', 'predicate'], postgresql_where=sa.text('superseded_by IS NULL'))
    op.create_index('idx_facts_object', 'onto_facts', ['object_id', 'predicate'], postgresql_where=sa.text('superseded_by IS NULL AND object_id IS NOT NULL'))
    op.create_index('idx_facts_temporal', 'onto_facts', ['valid_from', 'valid_to'], postgresql_where=sa.text('superseded_by IS NULL'))
    op.create_index('idx_facts_derived', 'onto_facts', ['is_derived', 'derivation_rule'], postgresql_where=sa.text('is_derived = TRUE'))

    # onto_mentions table
    op.create_table(
        'onto_mentions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('mention_type', sa.Text(), nullable=False),
        sa.Column('surface_form', sa.Text(), nullable=False),
        sa.Column('normalized_form', sa.Text(), nullable=False),
        sa.Column('extracted_personnummer', sa.Text(), nullable=True),
        sa.Column('extracted_orgnummer', sa.Text(), nullable=True),
        sa.Column('extracted_attributes', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('provenance_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('onto_provenances.id'), nullable=False),
        sa.Column('document_location', sa.Text(), nullable=True),
        sa.Column('resolution_status', sa.Enum('PENDING', 'AUTO_MATCHED', 'HUMAN_MATCHED', 'AUTO_REJECTED', 'HUMAN_REJECTED', name='resolution_status_enum', create_type=False), nullable=False, server_default='PENDING'),
        sa.Column('resolved_to', postgresql.UUID(as_uuid=True), sa.ForeignKey('onto_entities.id'), nullable=True),
        sa.Column('resolution_confidence', sa.Float(), nullable=True),
        sa.Column('resolution_method', sa.Text(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_by', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("mention_type IN ('PERSON', 'COMPANY', 'ADDRESS')", name='check_mention_type'),
        sa.CheckConstraint("(resolution_confidence IS NULL) OR (resolution_confidence >= 0 AND resolution_confidence <= 1)", name='check_resolution_confidence'),
    )
    op.create_index('idx_mentions_pending', 'onto_mentions', ['mention_type'], postgresql_where=sa.text("resolution_status = 'PENDING'"))
    op.create_index('idx_mentions_resolved', 'onto_mentions', ['resolved_to'], postgresql_where=sa.text('resolved_to IS NOT NULL'))

    # onto_resolution_decisions table
    op.create_table(
        'onto_resolution_decisions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('mention_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('onto_mentions.id'), nullable=False),
        sa.Column('candidate_entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('onto_entities.id'), nullable=False),
        sa.Column('overall_score', sa.Float(), nullable=False),
        sa.Column('feature_scores', postgresql.JSONB(), nullable=False),
        sa.Column('decision', sa.Text(), nullable=False),
        sa.Column('decision_reason', sa.Text(), nullable=True),
        sa.Column('reviewer_id', sa.Text(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint('overall_score >= 0 AND overall_score <= 1', name='check_overall_score'),
        sa.CheckConstraint("decision IN ('AUTO_MATCH', 'AUTO_REJECT', 'HUMAN_MATCH', 'HUMAN_REJECT', 'PENDING_REVIEW')", name='check_decision_value'),
    )
    op.create_index('idx_resolution_pending', 'onto_resolution_decisions', ['decision'], postgresql_where=sa.text("decision = 'PENDING_REVIEW'"))

    # onto_source_authority table
    op.create_table(
        'onto_source_authority',
        sa.Column('source_type', sa.Enum('BOLAGSVERKET_HVD', 'BOLAGSVERKET_ANNUAL_REPORT', 'ALLABOLAG_SCRAPE', 'MANUAL_ENTRY', 'DERIVED_COMPUTATION', name='source_type_enum', create_type=False), primary_key=True),
        sa.Column('fact_predicate', sa.Text(), primary_key=True),
        sa.Column('authority_level', sa.Integer(), nullable=False),
        sa.CheckConstraint('authority_level > 0', name='check_authority_level_positive'),
    )

    # onto_audit_log table
    op.create_table(
        'onto_audit_log',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('event_timestamp', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('event_type', sa.Text(), nullable=False),
        sa.Column('actor_type', sa.Enum('SYSTEM', 'USER', 'API', name='actor_type_enum', create_type=False), nullable=False),
        sa.Column('actor_id', sa.Text(), nullable=True),
        sa.Column('target_type', sa.Text(), nullable=True),
        sa.Column('target_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('event_data', postgresql.JSONB(), nullable=False),
        sa.Column('request_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('ip_address', postgresql.INET(), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
    )
    op.create_index('idx_audit_timestamp', 'onto_audit_log', ['event_timestamp'])
    op.create_index('idx_audit_target', 'onto_audit_log', ['target_type', 'target_id'])
    op.create_index('idx_audit_actor', 'onto_audit_log', ['actor_type', 'actor_id'])
    op.create_index('idx_audit_event_type', 'onto_audit_log', ['event_type'])

    # Insert default source authorities
    op.execute("""
        INSERT INTO onto_source_authority (source_type, fact_predicate, authority_level) VALUES
        ('BOLAGSVERKET_HVD', 'DIRECTOR_OF', 1),
        ('BOLAGSVERKET_HVD', 'REGISTERED_AT', 1),
        ('BOLAGSVERKET_HVD', 'SHAREHOLDER_OF', 2),
        ('BOLAGSVERKET_ANNUAL_REPORT', 'SHAREHOLDER_OF', 1),
        ('ALLABOLAG_SCRAPE', 'DIRECTOR_OF', 2),
        ('ALLABOLAG_SCRAPE', 'SHAREHOLDER_OF', 3)
    """)


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table('onto_audit_log')
    op.drop_table('onto_source_authority')
    op.drop_table('onto_resolution_decisions')
    op.drop_table('onto_mentions')
    op.drop_table('onto_facts')
    op.drop_table('onto_address_attributes')
    op.drop_table('onto_company_attributes')
    op.drop_table('onto_person_attributes')
    op.drop_table('onto_entity_identifiers')
    op.drop_table('onto_provenances')
    op.drop_table('onto_entities')

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS actor_type_enum")
    op.execute("DROP TYPE IF EXISTS source_type_enum")
    op.execute("DROP TYPE IF EXISTS resolution_status_enum")
    op.execute("DROP TYPE IF EXISTS fact_type_enum")
    op.execute("DROP TYPE IF EXISTS identifier_type_enum")
    op.execute("DROP TYPE IF EXISTS entity_status_enum")
    op.execute("DROP TYPE IF EXISTS entity_type_enum")
