"""
Tests for the graph schema module.
"""

import pytest
from datetime import date, datetime

from halo.graph.schema import (
    Person,
    Company,
    Address,
    Property,
    BankAccount,
    Document,
)


class TestPerson:
    """Tests for Person node type."""

    def test_person_creation_defaults(self):
        """Test person creation with default values."""
        person = Person()

        assert person.id is not None
        assert len(person.id) == 36  # UUID format
        assert person.personnummer is None
        assert person.names == []
        assert person.addresses == []
        assert person.risk_score == 0.0
        assert person.flags == []

    def test_person_with_data(self):
        """Test person creation with data."""
        person = Person(
            personnummer="198501011234",
            names=[{"name": "Johan Svensson", "source": "skatteverket", "observed_at": "2024-01-01"}],
            dob=date(1985, 1, 1),
            nationality="SE",
            risk_score=0.5
        )

        assert person.personnummer == "198501011234"
        assert len(person.names) == 1
        assert person.names[0]["name"] == "Johan Svensson"
        assert person.dob == date(1985, 1, 1)
        assert person.nationality == "SE"
        assert person.risk_score == 0.5

    def test_person_display_name(self):
        """Test display name property."""
        # Empty names
        person = Person()
        assert person.display_name == "Unknown"

        # With names
        person = Person(names=[
            {"name": "Old Name", "observed_at": "2020-01-01"},
            {"name": "Current Name", "observed_at": "2024-01-01"},
        ])
        assert person.display_name == "Current Name"

    def test_person_pep_status(self):
        """Test PEP status property."""
        person = Person()
        assert person.is_pep is False

        person = Person(pep_status={"is_pep": True, "position": "Riksdagsledamot"})
        assert person.is_pep is True

    def test_person_sanctions_hit(self):
        """Test sanctions hit detection."""
        person = Person()
        assert person.has_sanctions_hit is False

        person = Person(sanctions_matches=[
            {"list": "UN", "match_score": 0.5}  # Below threshold
        ])
        assert person.has_sanctions_hit is False

        person = Person(sanctions_matches=[
            {"list": "UN", "match_score": 0.95}  # Above threshold
        ])
        assert person.has_sanctions_hit is True


class TestCompany:
    """Tests for Company node type."""

    def test_company_creation_defaults(self):
        """Test company creation with defaults."""
        company = Company()

        assert company.id is not None
        assert company.orgnr == ""
        assert company.names == []
        assert company.legal_form == ""
        assert company.risk_score == 0.0
        assert company.shell_score == 0.0

    def test_company_with_data(self):
        """Test company creation with data."""
        company = Company(
            orgnr="5560125790",
            names=[{"name": "Test AB", "type": "FORETAGSNAMN", "from": "2020-01-01"}],
            legal_form="AB",
            status={"code": "active", "text": "Aktiv"},
            f_skatt={"registered": True},
            vat={"registered": True},
            employees={"count": 50, "as_of": "2024-01-01"}
        )

        assert company.orgnr == "5560125790"
        assert company.legal_form == "AB"
        assert company.has_f_skatt is True
        assert company.has_vat is True
        assert company.employee_count == 50

    def test_company_display_name(self):
        """Test company display name."""
        company = Company()
        assert company.display_name == "Unknown"

        company = Company(names=[
            {"name": "Old Name AB", "from": "2020-01-01", "to": "2023-01-01"},
            {"name": "Current Name AB", "from": "2023-01-01"},
        ])
        assert company.display_name == "Current Name AB"

    def test_company_is_active(self):
        """Test active status detection."""
        company = Company(status={"code": "active"})
        assert company.is_active is True

        company = Company(status={"code": "dissolved"})
        assert company.is_active is False

    def test_company_tax_status(self):
        """Test tax registration status."""
        company = Company()
        assert company.has_f_skatt is False
        assert company.has_vat is False

        company = Company(
            f_skatt={"registered": True},
            vat={"registered": False}
        )
        assert company.has_f_skatt is True
        assert company.has_vat is False


class TestAddress:
    """Tests for Address node type."""

    def test_address_creation(self):
        """Test address creation."""
        address = Address()

        assert address.id is not None
        assert address.raw_strings == []
        assert address.normalized == {}
        assert address.type == "unknown"
        assert address.registration_count == 0

    def test_address_with_data(self):
        """Test address with data."""
        address = Address(
            raw_strings=["Storgatan 1, 111 22 Stockholm"],
            normalized={
                "street": "Storgatan",
                "number": "1",
                "postal_code": "111 22",
                "city": "Stockholm"
            },
            type="commercial",
            registration_count=3
        )

        assert "Storgatan" in address.display_address
        assert "Stockholm" in address.display_address
        assert address.is_virtual is False
        assert address.is_high_density is False

    def test_address_virtual(self):
        """Test virtual address detection."""
        address = Address(type="virtual")
        assert address.is_virtual is True

    def test_address_high_density(self):
        """Test high density detection."""
        address = Address(registration_count=3)
        assert address.is_high_density is False

        address = Address(registration_count=10)
        assert address.is_high_density is True


class TestProperty:
    """Tests for Property node type."""

    def test_property_creation(self):
        """Test property creation."""
        prop = Property(
            fastighet_id="STOCKHOLM 1:1",
            type="residential",
            size=150.0,
            owners=[{"entity_id": "person-123", "share": 100}]
        )

        assert prop.fastighet_id == "STOCKHOLM 1:1"
        assert prop.type == "residential"
        assert prop.size == 150.0
        assert len(prop.owners) == 1


class TestBankAccount:
    """Tests for BankAccount node type."""

    def test_bank_account_creation(self):
        """Test bank account creation."""
        account = BankAccount(
            iban="SE1234567890123456789012",
            bank="Swedbank",
            holder_id="company-123",
            holder_type="company",
            type="current"
        )

        assert account.iban == "SE1234567890123456789012"
        assert account.bank == "Swedbank"
        assert account.holder_type == "company"


class TestDocument:
    """Tests for Document node type."""

    def test_document_creation(self):
        """Test document creation."""
        doc = Document(
            type="annual_report",
            entity_refs=[{"entity_id": "company-123", "entity_type": "Company"}],
            source="bolagsverket",
            date=date(2024, 6, 30)
        )

        assert doc.type == "annual_report"
        assert len(doc.entity_refs) == 1
        assert doc.source == "bolagsverket"
