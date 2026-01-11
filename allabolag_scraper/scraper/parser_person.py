"""
Parser for allabolag.se person pages.

Person pages provide:
- Full birth date (YYYY-MM-DD)
- All company roles (including companies not in our initial list)
- Connections to other persons (via shared companies)
- Historical role information
"""

from bs4 import BeautifulSoup
from dataclasses import dataclass
from datetime import date
from typing import Optional, List
import json
from urllib.parse import quote


@dataclass
class PersonRole:
    """A role this person holds at a company."""
    company_org_nr: str
    company_name: str
    role: str  # 'Verkstallande direktor', 'Ledamot', etc.
    company_status: str  # 'ACTIVE', 'INACTIVE', etc.
    company_employees: Optional[int]
    company_revenue: Optional[int]  # KSEK from SDI field


@dataclass
class PersonConnection:
    """A connection to another person (via shared companies)."""
    person_id: str
    name: str
    gender: Optional[str]
    num_shared_companies: int


@dataclass
class PersonProfile:
    """Complete person profile from person page."""
    allabolag_person_id: str
    name: str
    birth_date: Optional[date]  # YYYY-MM-DD format
    year_of_birth: Optional[int]
    age: Optional[int]
    gender: Optional[str]  # 'M' or 'F'

    roles: List[PersonRole]
    connections: List[PersonConnection]

    raw_json: dict


def build_person_url(name: str, person_id: str) -> str:
    """
    Build the person page URL.

    Format: /befattning/{name-slug}/-/{person_id}
    Example: /befattning/jens-anders-finn%C3%A4s/-/11337210
    """
    # Create URL-safe slug from name
    name_slug = name.lower().replace(' ', '-')
    name_slug = quote(name_slug, safe='-')
    return f"https://www.allabolag.se/befattning/{name_slug}/-/{person_id}"


def parse_person_page(html: str) -> Optional[PersonProfile]:
    """
    Parse person data from allabolag.se person page HTML.

    Returns PersonProfile object or None if parsing fails.
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

    # Navigate to person data
    try:
        page_props = data['props']['pageProps']
        role_person = page_props.get('rolePerson')
        if not role_person:
            return None
    except KeyError:
        return None

    # Parse birth date (YYYY-MM-DD format on person pages)
    birth_date = None
    birth_date_str = role_person.get('birthDate')
    if birth_date_str:
        try:
            parts = birth_date_str.split('-')
            if len(parts) == 3:
                birth_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
        except (ValueError, IndexError):
            pass

    # Extract roles (all companies this person is involved with)
    roles = []
    for role_data in role_person.get('roles', []):
        if role_data.get('type') == 'Company':
            # Extract revenue from companyAccounts (most recent year)
            revenue = None
            accounts = role_data.get('companyAccounts', [])
            if accounts:
                latest = accounts[0]  # First is most recent
                for acc in latest.get('accounts', []):
                    if acc.get('code') == 'SDI':  # Revenue code
                        try:
                            revenue = int(float(acc.get('amount', 0)))
                        except (ValueError, TypeError):
                            pass
                        break

            # Parse employee count
            employees = None
            emp_str = role_data.get('companyNumberOfEmployees')
            if emp_str:
                try:
                    employees = int(emp_str)
                except ValueError:
                    pass

            # Get status
            status_data = role_data.get('status', {})

            # Normalize org_nr
            org_nr = str(role_data.get('id', '')).replace('-', '').replace(' ', '')

            roles.append(PersonRole(
                company_org_nr=org_nr,
                company_name=role_data.get('name', ''),
                role=role_data.get('role', ''),
                company_status=status_data.get('status', 'UNKNOWN') if status_data else 'UNKNOWN',
                company_employees=employees,
                company_revenue=revenue,
            ))

    # Extract connections (other people connected through shared companies)
    connections = []
    for conn_data in role_person.get('connections', []):
        connections.append(PersonConnection(
            person_id=str(conn_data.get('personId', '')),
            name=conn_data.get('name', ''),
            gender=conn_data.get('gender'),
            num_shared_companies=conn_data.get('numberOfConnections', 0),
        ))

    return PersonProfile(
        allabolag_person_id=str(role_person.get('personId', '')),
        name=role_person.get('name', ''),
        birth_date=birth_date,
        year_of_birth=role_person.get('yearOfBirth'),
        age=role_person.get('age'),
        gender=role_person.get('gender'),
        roles=roles,
        connections=connections,
        raw_json=role_person,
    )
