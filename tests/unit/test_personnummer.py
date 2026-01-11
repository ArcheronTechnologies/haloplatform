"""
Unit tests for Swedish personnummer validation.
"""

from datetime import date

import pytest

from halo.swedish.personnummer import (
    PersonnummerInfo,
    format_personnummer,
    generate_personnummer,
    luhn_checksum,
    validate_personnummer,
)


class TestLuhnChecksum:
    """Tests for Luhn checksum calculation."""

    def test_known_checksums(self):
        """Test with known valid checksums."""
        # Test case from Skatteverket documentation
        assert luhn_checksum("811218987") == 6

    def test_all_zeros(self):
        """Test checksum of all zeros."""
        assert luhn_checksum("000000000") == 0

    def test_sequential_digits(self):
        """Test with sequential digits."""
        # The checksum should be deterministic
        result = luhn_checksum("123456789")
        assert isinstance(result, int)
        assert 0 <= result <= 9


class TestValidatePersonnummer:
    """Tests for personnummer validation."""

    def test_valid_personnummer_12_digits(self):
        """Test valid 12-digit personnummer."""
        # Valid test personnummer (generated)
        result = validate_personnummer("198112189876")
        assert result.is_valid
        assert result.normalized == "198112189876"
        assert result.birth_date == date(1981, 12, 18)
        assert result.gender == "M"  # 7 is odd
        assert not result.is_coordination

    def test_valid_personnummer_10_digits(self):
        """Test valid 10-digit personnummer."""
        result = validate_personnummer("8112189876")
        assert result.is_valid
        assert result.normalized == "198112189876"

    def test_valid_personnummer_with_dash(self):
        """Test valid personnummer with separator."""
        result = validate_personnummer("811218-9876")
        assert result.is_valid
        assert result.normalized == "198112189876"

    def test_valid_personnummer_with_plus(self):
        """Test personnummer with + for people over 100."""
        # Person born 1912 using + separator (would be over 100)
        # Valid personnummer: 191212189870 (checksum 0)
        result = validate_personnummer("121218+9870")
        assert result.is_valid
        # With +, century should be 19xx for recent years
        assert result.normalized[:2] == "19"

    def test_invalid_checksum(self):
        """Test personnummer with wrong checksum."""
        result = validate_personnummer("198112189870")  # Wrong checksum
        assert not result.is_valid

    def test_invalid_date(self):
        """Test personnummer with invalid date."""
        result = validate_personnummer("199902301234")  # Feb 30 doesn't exist
        assert not result.is_valid

    def test_coordination_number(self):
        """Test valid coordination number (samordningsnummer)."""
        # Coordination numbers have day + 60
        # Day 18 becomes 78
        # Valid coordination number: 198112789873 (checksum 3)
        result = validate_personnummer("198112789873")
        assert result.is_valid
        assert result.is_coordination
        assert result.birth_date == date(1981, 12, 18)

    def test_gender_female(self):
        """Test gender detection for female."""
        # 9th digit even = female
        pnr = generate_personnummer(date(1990, 5, 15), gender="F")
        result = validate_personnummer(pnr)
        assert result.is_valid
        assert result.gender == "F"

    def test_gender_male(self):
        """Test gender detection for male."""
        # 9th digit odd = male
        pnr = generate_personnummer(date(1990, 5, 15), gender="M")
        result = validate_personnummer(pnr)
        assert result.is_valid
        assert result.gender == "M"

    def test_invalid_format_letters(self):
        """Test rejection of letters."""
        result = validate_personnummer("19811218ABCD")
        assert not result.is_valid

    def test_invalid_format_too_short(self):
        """Test rejection of too short input."""
        result = validate_personnummer("811218")
        assert not result.is_valid

    def test_invalid_format_too_long(self):
        """Test rejection of too long input."""
        result = validate_personnummer("19811218987612")
        assert not result.is_valid

    def test_whitespace_handling(self):
        """Test that whitespace is handled correctly."""
        result = validate_personnummer("  811218-9876  ")
        assert result.is_valid

    def test_future_date_rejected(self):
        """Test that future birth dates are rejected."""
        future_pnr = generate_personnummer(date(2030, 1, 1))
        result = validate_personnummer(future_pnr)
        assert not result.is_valid


class TestFormatPersonnummer:
    """Tests for personnummer formatting."""

    def test_format_valid(self):
        """Test formatting valid personnummer."""
        result = format_personnummer("8112189876")
        assert result == "19811218-9876"

    def test_format_already_formatted(self):
        """Test formatting already formatted personnummer."""
        result = format_personnummer("19811218-9876")
        assert result == "19811218-9876"

    def test_format_invalid_returns_none(self):
        """Test that invalid personnummer returns None."""
        result = format_personnummer("0000000000")
        assert result is None

    def test_format_custom_separator(self):
        """Test formatting with custom separator."""
        result = format_personnummer("8112189876", separator="")
        assert result == "198112189876"


class TestGeneratePersonnummer:
    """Tests for personnummer generation (test utility)."""

    def test_generate_valid(self):
        """Test that generated personnummer is valid."""
        pnr = generate_personnummer(date(1985, 6, 15))
        result = validate_personnummer(pnr)
        assert result.is_valid

    def test_generate_correct_date(self):
        """Test that generated personnummer has correct date."""
        birth = date(1990, 3, 25)
        pnr = generate_personnummer(birth)
        result = validate_personnummer(pnr)
        assert result.birth_date == birth

    def test_generate_correct_gender(self):
        """Test that generated personnummer has correct gender."""
        for gender in ["M", "F"]:
            pnr = generate_personnummer(date(1995, 1, 1), gender=gender)
            result = validate_personnummer(pnr)
            assert result.gender == gender
