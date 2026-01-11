"""
Parser for allabolag.se company pages.

The site uses Next.js and embeds all data in a <script id="__NEXT_DATA__"> tag
as JSON. We extract this and parse the relevant fields.
"""

from bs4 import BeautifulSoup
from dataclasses import dataclass
from datetime import date
from typing import Optional, List
import json
import re


@dataclass
class Person:
    name: str
    birth_date: Optional[date]  # Parsed from "DD.MM.YYYY"
    allabolag_id: str
    role: str
    role_group: str  # 'Management', 'Board', 'Revision', 'Other'


@dataclass
class Company:
    org_nr: str
    name: str
    legal_name: Optional[str]
    status: Optional[str]
    status_date: Optional[date]
    registration_date: Optional[date]
    company_type: Optional[str]
    sni_code: Optional[str]
    sni_name: Optional[str]
    municipality: Optional[str]
    county: Optional[str]
    parent_org_nr: Optional[str]
    parent_name: Optional[str]
    revenue: Optional[int]  # KSEK
    profit: Optional[int]
    employees: Optional[int]
    allabolag_company_id: Optional[str]
    persons: List[Person]
    raw_json: dict


def parse_birth_date(date_str: str) -> Optional[date]:
    """Parse 'DD.MM.YYYY' to date object."""
    if not date_str:
        return None
    try:
        parts = date_str.split('.')
        if len(parts) == 3:
            return date(int(parts[2]), int(parts[1]), int(parts[0]))
    except (ValueError, IndexError):
        pass
    return None


def parse_swedish_date(date_str: str) -> Optional[date]:
    """Parse 'YYYY-MM-DD' or 'DD.MM.YYYY' to date object."""
    if not date_str:
        return None
    try:
        if '-' in date_str:
            parts = date_str.split('-')
            return date(int(parts[0]), int(parts[1]), int(parts[2]))
        elif '.' in date_str:
            return parse_birth_date(date_str)
    except (ValueError, IndexError):
        pass
    return None


def normalize_org_nr(org_nr: str) -> str:
    """Normalize org number to 10 digits without dash."""
    if not org_nr:
        return ""
    return org_nr.replace('-', '').replace(' ', '')


def parse_int(value) -> Optional[int]:
    """Parse string/int to int, handling Swedish formatting."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        # Remove spaces, handle KSEK notation
        cleaned = value.replace(' ', '').replace(',', '.').replace('\xa0', '')
        try:
            return int(float(cleaned))
        except ValueError:
            return None
    return None


def parse_company(html: str) -> Optional[Company]:
    """
    Parse company data from allabolag.se HTML.

    Returns Company object or None if parsing fails.
    """
    soup = BeautifulSoup(html, 'html.parser')

    # Find the __NEXT_DATA__ script tag
    script_tag = soup.select_one('script#__NEXT_DATA__')
    if not script_tag or not script_tag.string:
        return None

    try:
        data = json.loads(script_tag.string)
    except json.JSONDecodeError:
        return None

    # Navigate to company data
    try:
        page_props = data['props']['pageProps']
        company_data = page_props.get('company')
        if not company_data:
            return None
    except KeyError:
        return None

    # Extract persons from roles
    persons = []
    roles_data = company_data.get('roles', {})
    role_groups = roles_data.get('roleGroups', [])

    for group in role_groups:
        group_name = group.get('name', 'Other')
        for role_entry in group.get('roles', []):
            if role_entry.get('type') == 'Person':
                persons.append(Person(
                    name=role_entry.get('name', ''),
                    birth_date=parse_birth_date(role_entry.get('birthDate')),
                    allabolag_id=str(role_entry.get('id', '')),
                    role=role_entry.get('role', ''),
                    role_group=group_name
                ))

    # Also check chairman and manager separately
    for key in ['chairman', 'manager']:
        person_data = roles_data.get(key)
        if person_data and person_data.get('type') == 'Person':
            # Check if already added (avoid duplicates)
            existing_ids = {p.allabolag_id for p in persons}
            if str(person_data.get('id', '')) not in existing_ids:
                persons.append(Person(
                    name=person_data.get('name', ''),
                    birth_date=parse_birth_date(person_data.get('birthDate')),
                    allabolag_id=str(person_data.get('id', '')),
                    role=person_data.get('role', ''),
                    role_group='Management' if key == 'manager' else 'Board'
                ))

    # Extract corporate structure (parent company)
    corp_structure = company_data.get('corporateStructure') or {}
    parent_org_nr = corp_structure.get('parentCompanyOrganisationNumber')
    if parent_org_nr:
        parent_org_nr = normalize_org_nr(parent_org_nr)

    # Extract industry
    current_industry = company_data.get('currentIndustry') or {}

    # Extract location
    location = company_data.get('location') or {}
    domicile = company_data.get('domicile') or {}

    # Extract status
    status_data = company_data.get('status') or {}

    return Company(
        org_nr=normalize_org_nr(company_data.get('orgnr', '')),
        name=company_data.get('name', ''),
        legal_name=company_data.get('legalName'),
        status=status_data.get('status'),
        status_date=parse_swedish_date(status_data.get('statusDate')),
        registration_date=parse_swedish_date(company_data.get('registrationDate')),
        company_type=company_data.get('companyType', {}).get('name') if company_data.get('companyType') else None,
        sni_code=current_industry.get('code'),
        sni_name=current_industry.get('name'),
        municipality=domicile.get('municipality') or location.get('municipality'),
        county=domicile.get('county') or location.get('county'),
        parent_org_nr=parent_org_nr,
        parent_name=corp_structure.get('parentCompanyName'),
        revenue=parse_int(company_data.get('revenue')),
        profit=parse_int(company_data.get('profit')),
        employees=parse_int(company_data.get('employees')),
        allabolag_company_id=company_data.get('companyId'),
        persons=persons,
        raw_json=company_data
    )
