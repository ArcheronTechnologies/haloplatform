"""Swedish-specific utilities for personnummer, organisationsnummer, addresses, company names, and data handling."""

from halo.swedish.personnummer import (
    validate_personnummer,
    PersonnummerInfo,
    format_personnummer,
    generate_personnummer,
    luhn_checksum,
)
from halo.swedish.organisationsnummer import (
    validate_organisationsnummer,
    OrganisationsnummerInfo,
    format_organisationsnummer,
    format_with_prefix,
    generate_organisationsnummer,
    is_aktiebolag,
    luhn_checksum as orgnr_luhn_checksum,
    ORGANIZATION_TYPES,
)
from halo.swedish.address import (
    SwedishAddress,
    parse_address,
    validate_postal_code,
    normalize_postal_code,
    normalize_street_name,
    normalize_city_name,
    get_region_from_postal_code,
    extract_addresses_from_text,
    is_swedish_address,
    addresses_match,
    format_address_for_display,
    format_address_for_search,
    POSTAL_REGIONS,
)
from halo.swedish.company_name import (
    NormalizedCompanyName,
    normalize_company_name,
    company_names_match,
    extract_legal_form,
    format_company_name,
    is_holding_company,
    is_consulting_company,
    LEGAL_FORMS,
    LEGAL_FORM_FULL_NAMES,
)

__all__ = [
    # Personnummer
    "validate_personnummer",
    "PersonnummerInfo",
    "format_personnummer",
    "generate_personnummer",
    "luhn_checksum",
    # Organisationsnummer
    "validate_organisationsnummer",
    "OrganisationsnummerInfo",
    "format_organisationsnummer",
    "format_with_prefix",
    "generate_organisationsnummer",
    "is_aktiebolag",
    "orgnr_luhn_checksum",
    "ORGANIZATION_TYPES",
    # Address
    "SwedishAddress",
    "parse_address",
    "validate_postal_code",
    "normalize_postal_code",
    "normalize_street_name",
    "normalize_city_name",
    "get_region_from_postal_code",
    "extract_addresses_from_text",
    "is_swedish_address",
    "addresses_match",
    "format_address_for_display",
    "format_address_for_search",
    "POSTAL_REGIONS",
    # Company Name
    "NormalizedCompanyName",
    "normalize_company_name",
    "company_names_match",
    "extract_legal_form",
    "format_company_name",
    "is_holding_company",
    "is_consulting_company",
    "LEGAL_FORMS",
    "LEGAL_FORM_FULL_NAMES",
]
