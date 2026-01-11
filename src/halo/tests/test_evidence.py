"""
Tests for the evidence package module.

Tests:
- Evidence package compilation
- Provenance chain management
- Export functionality
"""

from datetime import datetime
from uuid import uuid4

import pytest

from halo.evidence import (
    EvidencePackage,
    EvidenceItem,
    PackageStatus,
    create_evidence_package,
    ProvenanceChain,
    ProvenanceEntry,
    verify_provenance,
    EvidenceExporter,
    ExportFormat,
)


class TestPackageStatus:
    """Tests for PackageStatus enum."""

    def test_status_values(self):
        """Test status values exist."""
        assert PackageStatus.DRAFT.value == "draft"
        assert PackageStatus.COMPILING.value == "compiling"
        assert PackageStatus.REVIEW.value == "review"
        assert PackageStatus.SEALED.value == "sealed"
        assert PackageStatus.EXPORTED.value == "exported"


class TestEvidenceItem:
    """Tests for EvidenceItem dataclass."""

    def test_item_creation(self):
        """Test creating an evidence item."""
        item = EvidenceItem(
            id=uuid4(),
            item_type="document",
            title="Company Registration",
            description="Company registration document from Bolagsverket",
            source="bolagsverket",
            source_timestamp=datetime.utcnow(),
            content_hash="sha256:abc123def456",
            metadata={"document_id": "BV-2024-001"},
        )

        assert item.item_type == "document"
        assert item.source == "bolagsverket"
        assert item.title == "Company Registration"

    def test_item_to_dict(self):
        """Test serializing item to dict."""
        item_id = uuid4()
        timestamp = datetime.utcnow()

        item = EvidenceItem(
            id=item_id,
            item_type="transaction",
            title="Transaction Record",
            description="Bank transaction record",
            source="bank_records",
            source_timestamp=timestamp,
            content_hash="sha256:def456",
        )

        data = item.to_dict()

        assert data["id"] == str(item_id)
        assert data["item_type"] == "transaction"
        assert data["source"] == "bank_records"
        assert data["title"] == "Transaction Record"

    def test_item_defaults(self):
        """Test default values for item."""
        item = EvidenceItem(
            id=uuid4(),
            item_type="entity",
            title="Entity Record",
            description="Entity data",
            source="halo",
            source_timestamp=datetime.utcnow(),
            content_hash="sha256:test",
        )

        assert item.metadata == {}
        assert item.provenance_id is None


class TestEvidencePackage:
    """Tests for EvidencePackage dataclass."""

    def test_package_creation(self):
        """Test creating an evidence package."""
        case_id = uuid4()
        package = EvidencePackage(
            id=uuid4(),
            case_id=case_id,
            title="Investigation Package",
            status=PackageStatus.DRAFT,
            created_at=datetime.utcnow(),
            created_by="analyst_1",
        )

        assert package.case_id == case_id
        assert package.title == "Investigation Package"
        assert len(package.items) == 0

    def test_package_add_item(self):
        """Test adding item to package."""
        package = EvidencePackage(
            id=uuid4(),
            case_id=uuid4(),
            title="Test Package",
            status=PackageStatus.DRAFT,
            created_at=datetime.utcnow(),
            created_by="analyst_1",
        )

        item = EvidenceItem(
            id=uuid4(),
            item_type="document",
            title="Test Document",
            description="Test item",
            source="test",
            source_timestamp=datetime.utcnow(),
            content_hash="sha256:test",
        )

        package.add_item(item)

        assert len(package.items) == 1

    def test_package_cannot_add_to_sealed(self):
        """Test cannot add items to sealed package."""
        package = EvidencePackage(
            id=uuid4(),
            case_id=uuid4(),
            title="Sealed Package",
            status=PackageStatus.SEALED,
            created_at=datetime.utcnow(),
            created_by="analyst_1",
        )

        item = EvidenceItem(
            id=uuid4(),
            item_type="document",
            title="New Document",
            description="Should fail",
            source="test",
            source_timestamp=datetime.utcnow(),
            content_hash="sha256:test",
        )

        with pytest.raises(ValueError, match="Cannot add items to a sealed package"):
            package.add_item(item)

    def test_package_seal(self):
        """Test sealing a package."""
        package = EvidencePackage(
            id=uuid4(),
            case_id=uuid4(),
            title="Package to Seal",
            status=PackageStatus.DRAFT,
            created_at=datetime.utcnow(),
            created_by="analyst_1",
        )

        item = EvidenceItem(
            id=uuid4(),
            item_type="document",
            title="Evidence",
            description="Evidence item",
            source="test",
            source_timestamp=datetime.utcnow(),
            content_hash="sha256:evidence",
        )
        package.add_item(item)

        package.seal(sealed_by="supervisor_1")

        assert package.status == PackageStatus.SEALED
        assert package.sealed_at is not None
        assert package.sealed_by == "supervisor_1"
        assert package.package_hash is not None

    def test_package_cannot_seal_twice(self):
        """Test cannot seal already sealed package."""
        package = EvidencePackage(
            id=uuid4(),
            case_id=uuid4(),
            title="Already Sealed",
            status=PackageStatus.SEALED,
            created_at=datetime.utcnow(),
            created_by="analyst_1",
            sealed_at=datetime.utcnow(),
            sealed_by="supervisor_1",
            package_hash="sha256:sealed",
        )

        with pytest.raises(ValueError, match="Package is already sealed"):
            package.seal(sealed_by="supervisor_2")

    def test_package_verify_integrity(self):
        """Test verifying package integrity."""
        package = EvidencePackage(
            id=uuid4(),
            case_id=uuid4(),
            title="Integrity Test",
            status=PackageStatus.DRAFT,
            created_at=datetime.utcnow(),
            created_by="analyst_1",
        )

        item = EvidenceItem(
            id=uuid4(),
            item_type="document",
            title="Doc",
            description="Test",
            source="test",
            source_timestamp=datetime.utcnow(),
            content_hash="sha256:content",
        )
        package.add_item(item)
        package.seal(sealed_by="supervisor")

        assert package.verify_integrity() is True

    def test_package_to_dict(self):
        """Test serializing package to dict."""
        package_id = uuid4()
        case_id = uuid4()

        package = EvidencePackage(
            id=package_id,
            case_id=case_id,
            title="Serialization Test",
            status=PackageStatus.DRAFT,
            created_at=datetime.utcnow(),
            created_by="analyst_1",
            summary="Test summary",
        )

        data = package.to_dict()

        assert data["id"] == str(package_id)
        assert data["case_id"] == str(case_id)
        assert data["status"] == "draft"
        assert data["summary"] == "Test summary"


class TestProvenanceEntry:
    """Tests for ProvenanceEntry dataclass."""

    def test_entry_creation(self):
        """Test creating a provenance entry."""
        entry = ProvenanceEntry(
            id=uuid4(),
            timestamp=datetime.utcnow(),
            action="created",
            actor="analyst_1",
            previous_hash=None,
            entry_hash="sha256:abc123",
            details={"event": "package_created"},
        )

        assert entry.action == "created"
        assert entry.actor == "analyst_1"
        assert entry.previous_hash is None

    def test_entry_to_dict(self):
        """Test serializing entry to dict."""
        entry_id = uuid4()
        timestamp = datetime.utcnow()

        entry = ProvenanceEntry(
            id=entry_id,
            timestamp=timestamp,
            action="item_added",
            actor="analyst_1",
            previous_hash="sha256:prev",
            entry_hash="sha256:current",
            details={"item_id": "abc123"},
        )

        data = entry.to_dict()

        assert data["id"] == str(entry_id)
        assert data["action"] == "item_added"
        assert data["actor"] == "analyst_1"


class TestProvenanceChain:
    """Tests for provenance chain management."""

    def test_chain_creation(self):
        """Test creating a provenance chain."""
        item_id = uuid4()
        chain = ProvenanceChain(item_id=item_id)

        assert chain.item_id == item_id
        assert len(chain.entries) == 0

    def test_add_entry(self):
        """Test adding entry to chain."""
        chain = ProvenanceChain(item_id=uuid4())

        entry = chain.add_entry(
            action="created",
            actor="analyst_1",
            details={"event": "package_created"},
        )

        assert len(chain.entries) == 1
        assert entry.action == "created"
        assert entry.previous_hash is None  # First entry

    def test_chain_linking(self):
        """Test entries are properly linked."""
        chain = ProvenanceChain(item_id=uuid4())

        entry1 = chain.add_entry(
            action="created",
            actor="analyst_1",
        )

        entry2 = chain.add_entry(
            action="item_added",
            actor="analyst_1",
            details={"item": "doc1"},
        )

        # Second entry should reference first entry's hash
        assert entry2.previous_hash == entry1.entry_hash

    def test_chain_verify_valid(self):
        """Test verifying a valid chain."""
        chain = ProvenanceChain(item_id=uuid4())

        chain.add_entry(
            action="created",
            actor="analyst_1",
        )

        chain.add_entry(
            action="item_added",
            actor="analyst_1",
        )

        assert chain.verify() is True

    def test_chain_get_chain_hash(self):
        """Test getting chain hash."""
        chain = ProvenanceChain(item_id=uuid4())

        # Empty chain has no hash
        assert chain.get_chain_hash() is None

        entry = chain.add_entry(
            action="created",
            actor="analyst_1",
        )

        assert chain.get_chain_hash() == entry.entry_hash

    def test_chain_to_dict(self):
        """Test serializing chain to dict."""
        item_id = uuid4()
        chain = ProvenanceChain(item_id=item_id)

        chain.add_entry(
            action="created",
            actor="analyst_1",
        )

        data = chain.to_dict()

        assert data["item_id"] == str(item_id)
        assert len(data["entries"]) == 1
        assert data["is_valid"] is True


class TestVerifyProvenance:
    """Tests for verify_provenance function."""

    def test_verify_valid_chain(self):
        """Test verifying a valid chain."""
        chain = ProvenanceChain(item_id=uuid4())

        chain.add_entry(
            action="created",
            actor="analyst_1",
        )

        chain.add_entry(
            action="item_added",
            actor="analyst_1",
        )

        is_valid, errors = verify_provenance(chain)

        assert is_valid is True
        assert len(errors) == 0

    def test_verify_empty_chain(self):
        """Test verifying empty chain is valid."""
        chain = ProvenanceChain(item_id=uuid4())

        is_valid, errors = verify_provenance(chain)

        assert is_valid is True
        assert len(errors) == 0


class TestCreateEvidencePackage:
    """Tests for create_evidence_package function."""

    def test_create_basic_package(self):
        """Test creating a basic evidence package."""
        case_id = uuid4()

        package = create_evidence_package(
            case_id=case_id,
            title="Test Package",
            created_by="analyst_1",
        )

        assert package.case_id == case_id
        assert package.title == "Test Package"
        assert package.status == PackageStatus.DRAFT

    def test_create_package_with_summary(self):
        """Test creating package with summary."""
        package = create_evidence_package(
            case_id=uuid4(),
            title="Investigation Package",
            created_by="analyst_1",
            summary="Summary of evidence for case XYZ",
        )

        assert package.summary == "Summary of evidence for case XYZ"

    def test_create_package_with_metadata(self):
        """Test creating package with metadata."""
        package = create_evidence_package(
            case_id=uuid4(),
            title="Metadata Test",
            created_by="analyst_1",
            metadata={"priority": "high", "category": "fraud"},
        )

        assert package.metadata["priority"] == "high"


class TestExportFormat:
    """Tests for export format enum."""

    def test_export_formats(self):
        """Test export format values."""
        assert ExportFormat.JSON.value == "json"
        assert ExportFormat.PDF.value == "pdf"
        assert ExportFormat.XML.value == "xml"
        assert ExportFormat.CSV.value == "csv"


class TestEvidenceExporter:
    """Tests for EvidenceExporter class."""

    @pytest.fixture
    def sample_package(self):
        """Create a sample package for testing."""
        package = EvidencePackage(
            id=uuid4(),
            case_id=uuid4(),
            title="Export Test Package",
            status=PackageStatus.DRAFT,
            created_at=datetime.utcnow(),
            created_by="analyst_1",
            summary="Package for export testing",
        )

        item = EvidenceItem(
            id=uuid4(),
            item_type="document",
            title="Test Document",
            description="A test document for export",
            source="test_source",
            source_timestamp=datetime.utcnow(),
            content_hash="sha256:testcontent",
        )
        package.add_item(item)

        return package

    def test_exporter_initialization(self):
        """Test exporter initializes correctly."""
        exporter = EvidenceExporter()
        assert exporter is not None

    def test_export_to_json(self, sample_package):
        """Test exporting to JSON format."""
        exporter = EvidenceExporter()
        result = exporter.export(sample_package, ExportFormat.JSON)

        assert result is not None
        assert result.format == ExportFormat.JSON
        assert result.content_type == "application/json"
        assert result.filename.endswith(".json")

    def test_export_to_csv(self, sample_package):
        """Test exporting to CSV format."""
        exporter = EvidenceExporter()
        result = exporter.export(sample_package, ExportFormat.CSV)

        assert result is not None
        assert result.format == ExportFormat.CSV
        assert result.content_type == "text/csv"

    def test_export_to_xml(self, sample_package):
        """Test exporting to XML format."""
        exporter = EvidenceExporter()
        result = exporter.export(sample_package, ExportFormat.XML)

        assert result is not None
        assert result.format == ExportFormat.XML
        assert result.content_type == "application/xml"

    def test_export_to_pdf(self, sample_package):
        """Test exporting to PDF format."""
        exporter = EvidenceExporter()
        result = exporter.export(sample_package, ExportFormat.PDF)

        assert result is not None
        assert result.format == ExportFormat.PDF
        assert result.content_type == "application/pdf"

    def test_export_result_fields(self, sample_package):
        """Test export result has all expected fields."""
        exporter = EvidenceExporter()
        result = exporter.export(sample_package, ExportFormat.JSON)

        assert result.format is not None
        assert result.filename is not None
        assert result.content is not None
        assert result.content_type is not None
        assert result.exported_at is not None
        assert result.package_hash is not None


class TestEvidenceWorkflow:
    """Tests for complete evidence workflow."""

    def test_full_evidence_workflow(self):
        """Test complete evidence compilation workflow."""
        case_id = uuid4()

        # 1. Create package
        package = create_evidence_package(
            case_id=case_id,
            title="Fraud Investigation Evidence",
            created_by="analyst_1",
            summary="Evidence collection for fraud case",
        )

        assert package.status == PackageStatus.DRAFT

        # 2. Create provenance chain
        chain = ProvenanceChain(item_id=package.id)
        chain.add_entry(
            action="created",
            actor="analyst_1",
            details={"event": "package_created"},
        )

        # 3. Add evidence items
        item1 = EvidenceItem(
            id=uuid4(),
            item_type="document",
            title="Company Registration",
            description="Company registration from Bolagsverket",
            source="bolagsverket",
            source_timestamp=datetime.utcnow(),
            content_hash="sha256:doc1content",
        )

        package.add_item(item1)
        chain.add_entry(
            action="item_added",
            actor="analyst_1",
            details={"item_id": str(item1.id), "item_title": item1.title},
        )

        # 4. Add more items
        item2 = EvidenceItem(
            id=uuid4(),
            item_type="detection",
            title="Anomaly Detection Result",
            description="Shell company detection result",
            source="halo_intelligence",
            source_timestamp=datetime.utcnow(),
            content_hash="sha256:detection1",
        )

        package.add_item(item2)
        chain.add_entry(
            action="item_added",
            actor="analyst_1",
            details={"item_id": str(item2.id), "item_title": item2.title},
        )

        # 5. Verify provenance
        is_valid, errors = verify_provenance(chain)
        assert is_valid is True

        # 6. Seal package
        package.seal(sealed_by="supervisor_1")
        chain.add_entry(
            action="sealed",
            actor="supervisor_1",
            details={"package_hash": package.package_hash},
        )

        assert package.status == PackageStatus.SEALED
        assert package.verify_integrity() is True

        # 7. Export
        exporter = EvidenceExporter()
        exported = exporter.export(package, ExportFormat.JSON)

        assert exported is not None
        assert len(package.items) == 2

    def test_evidence_chain_of_custody(self):
        """Test maintaining chain of custody."""
        # Create evidence item
        item_id = uuid4()
        chain = ProvenanceChain(item_id=item_id)

        # Track creation
        chain.add_entry(
            action="created",
            actor="system",
            details={"source": "bolagsverket_api"},
        )

        # Track access
        chain.add_entry(
            action="accessed",
            actor="analyst_1",
            details={"purpose": "review"},
        )

        # Track modification
        chain.add_entry(
            action="annotated",
            actor="analyst_1",
            details={"annotation": "Verified company registration"},
        )

        # Track inclusion in package
        chain.add_entry(
            action="packaged",
            actor="analyst_1",
            details={"package_id": str(uuid4())},
        )

        # Verify complete chain
        assert chain.verify() is True
        assert len(chain.entries) == 4

        # Chain should be linkable
        for i in range(1, len(chain.entries)):
            assert chain.entries[i].previous_hash == chain.entries[i-1].entry_hash
