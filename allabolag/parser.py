"""
Parser for allabolag.se company pages.

Allabolag.se is a Next.js app that embeds all company data in a JSON blob
within a <script id="__NEXT_DATA__"> tag. This is much more reliable than
scraping HTML elements.

Extracts:
- Company details (name, orgnr, status, legal form)
- Address and contact info
- SNI codes and descriptions
- Financial data (revenue, profit, employees)
- Board members, directors, and auditors
- Signatories and ownership structure
"""
import re
import json
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class Company:
    """Parsed company data from allabolag.se."""
    orgnr: str
    name: str
    legal_form: Optional[str] = None
    status: Optional[str] = None
    registration_date: Optional[str] = None

    # Address
    street_address: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    municipality: Optional[str] = None
    county: Optional[str] = None

    # Contact
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None

    # Business
    sni_code: Optional[str] = None
    sni_description: Optional[str] = None
    purpose: Optional[str] = None

    # Financials (latest year)
    revenue: Optional[int] = None
    profit: Optional[int] = None
    employees: Optional[int] = None
    share_capital: Optional[int] = None

    # Board/Management
    directors: List[Dict[str, Any]] = field(default_factory=list)
    signatories: List[str] = field(default_factory=list)

    # Corporate structure
    parent_company: Optional[str] = None
    num_subsidiaries: Optional[int] = None

    # Meta
    scraped_at: Optional[str] = None
    source_url: Optional[str] = None

    # Raw data for debugging
    raw_json: Optional[dict] = None


class AllabolagParser:
    """Parser for allabolag.se company pages using Next.js JSON data."""

    def parse_company_page(self, html: str, url: str = None) -> Optional[Company]:
        """
        Parse a company detail page.

        Args:
            html: Raw HTML content
            url: Source URL (for reference)

        Returns:
            Company object or None if parsing fails
        """
        try:
            # Extract the __NEXT_DATA__ JSON blob
            data = self._extract_next_data(html)
            if not data:
                logger.warning("Could not find __NEXT_DATA__ in page")
                return None

            # Get company data from pageProps
            props = data.get('props', {}).get('pageProps', {})
            company_data = props.get('company')

            if not company_data:
                logger.warning("No company data found in pageProps")
                return None

            # Parse into Company object
            return self._parse_company_data(company_data, url)

        except Exception as e:
            logger.error(f"Parse error: {e}")
            return None

    def _extract_next_data(self, html: str) -> Optional[dict]:
        """Extract and parse the __NEXT_DATA__ script tag."""
        pattern = r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>'
        match = re.search(pattern, html, re.DOTALL)

        if not match:
            return None

        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse __NEXT_DATA__ JSON: {e}")
            return None

    def _parse_company_data(self, data: dict, url: str = None) -> Company:
        """Parse company data from the JSON structure."""
        company = Company(
            orgnr=data.get('orgnr', ''),
            name=data.get('name') or data.get('legalName', ''),
            source_url=url
        )

        # Legal form
        company_type = data.get('companyType', {})
        company.legal_form = company_type.get('name') or company_type.get('code')

        # Status
        status = data.get('status', {})
        company.status = status.get('status') or status.get('statusCode')

        # Registration date
        company.registration_date = data.get('registrationDate')

        # Address - prefer postal address
        postal = data.get('postalAddress') or data.get('legalPostalAddress') or {}
        visitor = data.get('visitorAddress') or data.get('legalVisitorAddress') or {}

        company.street_address = postal.get('addressLine') or visitor.get('addressLine')
        company.postal_code = postal.get('zipCode')
        company.city = postal.get('postPlace') or visitor.get('postPlace')

        # Location
        location = data.get('location', {})
        domicile = data.get('domicile', {})
        company.municipality = location.get('municipality') or domicile.get('municipality')
        company.county = location.get('county') or domicile.get('county')

        # Contact
        company.phone = data.get('phone') or data.get('legalPhone')
        company.email = data.get('email')
        company.website = data.get('homePage')

        # Industry/SNI
        nace = data.get('naceIndustries', [])
        if nace:
            # Format: "66190 Description here"
            first_nace = nace[0]
            parts = first_nace.split(' ', 1)
            if len(parts) >= 1:
                company.sni_code = parts[0]
            if len(parts) >= 2:
                company.sni_description = parts[1]

        # Also check industries array
        if not company.sni_code:
            industries = data.get('industries', [])
            if industries:
                company.sni_code = industries[0].get('code')
                company.sni_description = industries[0].get('name')

        # Purpose/description
        company.purpose = data.get('purpose')

        # Financials
        company.revenue = self._parse_amount(data.get('revenue'))
        company.profit = self._parse_amount(data.get('profit'))
        company.employees = self._parse_int(data.get('employees') or data.get('numberOfEmployees'))
        company.share_capital = self._parse_int(data.get('shareCapital'))

        # Directors and roles
        company.directors = self._parse_roles(data.get('roles', {}))

        # Signatories
        company.signatories = data.get('signatories', [])

        # Corporate structure (may be None, not just missing)
        corp_struct = data.get('corporateStructure') or {}
        company.parent_company = corp_struct.get('parentCompanyName')
        company.num_subsidiaries = corp_struct.get('numberOfSubsidiaries')

        # Store raw JSON for debugging/reprocessing
        company.raw_json = data

        return company

    def _parse_roles(self, roles_data: dict) -> List[Dict[str, Any]]:
        """Parse directors, board members, and auditors from roles data."""
        directors = []

        role_groups = roles_data.get('roleGroups', [])
        for group in role_groups:
            group_name = group.get('name', '')
            for role in group.get('roles', []):
                director = {
                    'name': role.get('name'),
                    'role': role.get('role'),
                    'group': group_name,
                    'type': role.get('type'),  # Person or Company
                    'id': role.get('id'),
                }

                # Parse birth date if available
                birth_date = role.get('birthDate')
                if birth_date:
                    director['birth_date'] = birth_date
                    # Extract birth year
                    parts = birth_date.split('.')
                    if len(parts) == 3:
                        try:
                            director['birth_year'] = int(parts[2])
                        except ValueError:
                            pass

                directors.append(director)

        return directors

    def _parse_amount(self, value) -> Optional[int]:
        """Parse a monetary amount (may be string like '326' or '0')."""
        if value is None:
            return None
        try:
            if isinstance(value, str):
                # Remove spaces, handle negative
                value = value.replace(' ', '').replace(',', '.')
                return int(float(value))
            return int(value)
        except (ValueError, TypeError):
            return None

    def _parse_int(self, value) -> Optional[int]:
        """Parse an integer value."""
        if value is None:
            return None
        try:
            if isinstance(value, str):
                return int(value.replace(' ', ''))
            return int(value)
        except (ValueError, TypeError):
            return None

    def extract_financial_history(self, html: str) -> List[Dict[str, Any]]:
        """
        Extract full financial history from page.

        Returns list of yearly account data with all available metrics.
        """
        data = self._extract_next_data(html)
        if not data:
            return []

        props = data.get('props', {}).get('pageProps', {})
        company_data = props.get('company', {})
        accounts = company_data.get('companyAccounts', [])

        history = []
        for year_data in accounts:
            year_record = {
                'year': year_data.get('year'),
                'period_start': year_data.get('periodStart'),
                'period_end': year_data.get('periodEnd'),
                'currency': year_data.get('currency'),
                'accounts': {}
            }

            for account in year_data.get('accounts', []):
                code = account.get('code')
                amount = account.get('amount')
                if code and amount is not None:
                    year_record['accounts'][code] = self._parse_amount(amount)

            history.append(year_record)

        return history
