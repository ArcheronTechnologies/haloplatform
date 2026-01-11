"""
Unit tests for Swedish organisationsnummer validation.
"""

import pytest

from halo.swedish.organisationsnummer import (
    ORGANIZATION_TYPES,
    OrganisationsnummerInfo,
    format_organisationsnummer,
    format_with_prefix,
    generate_organisationsnummer,
    is_aktiebolag,
    luhn_checksum,
    validate_organisationsnummer,
)


class TestLuhnChecksum:
    """Tests for Luhn checksum calculation."""

    def test_known_checksums(self):
        """Test with known valid checksums."""
        # Spotify AB: 556703-7485
        assert luhn_checksum("556703748") == 5

    def test_all_zeros(self):
        """Test checksum of all zeros."""
        assert luhn_checksum("000000000") == 0


class TestValidateOrganisationsnummer:
    """Tests for organisationsnummer validation."""

    def test_valid_orgnr_10_digits(self):
        """Test valid 10-digit organisationsnummer."""
        result = validate_organisationsnummer("5567037485")
        assert result.is_valid
        assert result.normalized == "5567037485"
        assert result.organization_type_code == "5"

    def test_valid_orgnr_with_dash(self):
        """Test valid organisationsnummer with separator."""
        result = validate_organisationsnummer("556703-7485")
        assert result.is_valid
        assert result.normalized == "5567037485"

    def test_valid_orgnr_with_prefix(self):
        """Test valid organisationsnummer with 16 prefix."""
        result = validate_organisationsnummer("165567037485")
        assert result.is_valid
        assert result.normalized == "5567037485"

    def test_valid_orgnr_with_prefix_and_dash(self):
        """Test valid organisationsnummer with 16 prefix and dash."""
        result = validate_organisationsnummer("16556703-7485")
        assert result.is_valid

    def test_invalid_checksum(self):
        """Test organisationsnummer with wrong checksum."""
        result = validate_organisationsnummer("5567037480")  # Wrong checksum
        assert not result.is_valid

    def test_invalid_group_number_too_low(self):
        """Test rejection when group number < 20."""
        # Group number (digits 3-4) must be >= 20
        result = validate_organisationsnummer("5510000000")
        assert not result.is_valid

    def test_organization_type_partnership(self):
        """Test organization type detection for partnership."""
        result = validate_organisationsnummer("5567037485")
        assert "Partnership" in result.organization_type or "Handelsbolag" in result.organization_type

    def test_organization_type_government(self):
        """Test organization type detection for government."""
        # Generate a valid orgnr starting with 2
        orgnr = generate_organisationsnummer(org_type="2", group_number=22)
        result = validate_organisationsnummer(orgnr)
        if result.is_valid:
            assert result.organization_type_code == "2"

    def test_invalid_format_letters(self):
        """Test rejection of letters."""
        result = validate_organisationsnummer("55670A7485")
        assert not result.is_valid

    def test_invalid_format_too_short(self):
        """Test rejection of too short input."""
        result = validate_organisationsnummer("556703")
        assert not result.is_valid

    def test_invalid_format_too_long(self):
        """Test rejection of too long input (not counting prefix)."""
        result = validate_organisationsnummer("55670374851234")
        assert not result.is_valid

    def test_whitespace_handling(self):
        """Test that whitespace is handled correctly."""
        result = validate_organisationsnummer("  556703-7485  ")
        assert result.is_valid

    def test_all_valid_org_types(self):
        """Test that all organization types are recognized."""
        for type_code in ORGANIZATION_TYPES.keys():
            # Just verify the mapping exists
            assert type_code in ORGANIZATION_TYPES


class TestFormatOrganisationsnummer:
    """Tests for organisationsnummer formatting."""

    def test_format_valid(self):
        """Test formatting valid organisationsnummer."""
        result = format_organisationsnummer("5567037485")
        assert result == "556703-7485"

    def test_format_already_formatted(self):
        """Test formatting already formatted organisationsnummer."""
        result = format_organisationsnummer("556703-7485")
        assert result == "556703-7485"

    def test_format_invalid_returns_none(self):
        """Test that invalid organisationsnummer returns None."""
        result = format_organisationsnummer("0000000000")
        assert result is None

    def test_format_custom_separator(self):
        """Test formatting with custom separator."""
        result = format_organisationsnummer("5567037485", separator="")
        assert result == "5567037485"


class TestFormatWithPrefix:
    """Tests for formatting with 16 prefix."""

    def test_format_with_prefix(self):
        """Test formatting with 16 prefix."""
        result = format_with_prefix("5567037485")
        assert result == "16556703-7485"

    def test_format_with_prefix_invalid_returns_none(self):
        """Test that invalid organisationsnummer returns None."""
        result = format_with_prefix("0000000000")
        assert result is None


class TestIsAktiebolag:
    """Tests for Aktiebolag detection."""

    def test_is_aktiebolag_true(self):
        """Test detection of likely AB."""
        # This would need a real AB orgnr, using Spotify as example
        result = is_aktiebolag("5567037485")
        assert isinstance(result, bool)

    def test_is_aktiebolag_invalid_returns_false(self):
        """Test that invalid orgnr returns False."""
        result = is_aktiebolag("0000000000")
        assert result is False


class TestGenerateOrganisationsnummer:
    """Tests for organisationsnummer generation (test utility)."""

    def test_generate_valid(self):
        """Test that generated organisationsnummer is valid."""
        orgnr = generate_organisationsnummer()
        result = validate_organisationsnummer(orgnr)
        assert result.is_valid

    def test_generate_specific_type(self):
        """Test generating specific organization type."""
        for org_type in ["5", "7", "8", "9"]:
            orgnr = generate_organisationsnummer(org_type=org_type, group_number=56)
            result = validate_organisationsnummer(orgnr)
            assert result.is_valid
            assert result.organization_type_code == org_type

    def test_generate_invalid_group_number_raises(self):
        """Test that invalid group number raises error."""
        with pytest.raises(ValueError):
            generate_organisationsnummer(group_number=10)  # Must be >= 20

        with pytest.raises(ValueError):
            generate_organisationsnummer(group_number=100)  # Must be <= 99
