"""
Read-only ingestion adapter for Allabolag scraped data.

Converts Allabolag's SQLite database format into ontology-aligned
Entity, Fact, and Mention objects for processing by the resolution
and derivation pipelines.

IMPORTANT: This adapter is READ-ONLY. The scraper may be running
concurrently, so we never write to the Allabolag database.
"""

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterator, Optional
from uuid import UUID, uuid4

from halo.schemas.entity import (
    EntityType,
    EntityIdentifierCreate,
    IdentifierType,
    PersonAttributes,
    CompanyAttributes,
)
from halo.schemas.mention import MentionCreate
from halo.schemas.provenance import ProvenanceCreate, SourceType


@dataclass
class AllabolagCompany:
    """Raw company data from Allabolag."""

    org_nr: str
    name: str
    legal_name: Optional[str]
    status: Optional[str]
    status_date: Optional[str]
    registration_date: Optional[str]
    company_type: Optional[str]
    sni_code: Optional[str]
    sni_name: Optional[str]
    municipality: Optional[str]
    county: Optional[str]
    parent_org_nr: Optional[str]
    parent_name: Optional[str]
    revenue: Optional[int]
    profit: Optional[int]
    employees: Optional[int]
    allabolag_company_id: Optional[str]
    scraped_at: str


@dataclass
class AllabolagPerson:
    """Raw person data from Allabolag."""

    id: int
    allabolag_person_id: str
    name: str
    first_name: Optional[str]
    last_name: Optional[str]
    birth_date: Optional[str]
    year_of_birth: Optional[int]
    age: Optional[int]
    gender: Optional[str]
    scraped_at: Optional[str]


@dataclass
class AllabolagRole:
    """Raw role data from Allabolag."""

    id: int
    company_org_nr: str
    person_id: int
    role_type: str
    role_group: Optional[str]
    discovered_from: Optional[str]
    scraped_at: str


class AllabolagAdapter:
    """
    Read-only adapter for Allabolag scraped data.

    Converts scraped data into ontology-aligned mentions and
    generates provenance records for tracking.

    Usage:
        adapter = AllabolagAdapter("/path/to/allabolag.db")
        for company in adapter.iter_companies(since="2025-01-01"):
            mention = adapter.company_to_mention(company, provenance_id)
            # Process mention...
    """

    def __init__(self, db_path: str | Path):
        """
        Initialize adapter with database path.

        Args:
            db_path: Path to allabolag.db SQLite database
        """
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {db_path}")

    def _connect(self) -> sqlite3.Connection:
        """Create read-only connection to database."""
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    # ========== Statistics ==========

    def get_stats(self) -> dict:
        """Get database statistics."""
        conn = self._connect()
        try:
            stats = {}
            stats["companies"] = conn.execute(
                "SELECT COUNT(*) FROM companies"
            ).fetchone()[0]
            stats["persons"] = conn.execute(
                "SELECT COUNT(*) FROM persons"
            ).fetchone()[0]
            stats["roles"] = conn.execute(
                "SELECT COUNT(*) FROM roles"
            ).fetchone()[0]

            # Latest scrape times
            stats["latest_company_scrape"] = conn.execute(
                "SELECT MAX(scraped_at) FROM companies"
            ).fetchone()[0]
            stats["latest_person_scrape"] = conn.execute(
                "SELECT MAX(person_page_scraped_at) FROM persons WHERE person_page_scraped_at IS NOT NULL"
            ).fetchone()[0]

            return stats
        finally:
            conn.close()

    # ========== Company Iteration ==========

    def iter_companies(
        self, since: Optional[str] = None, batch_size: int = 1000
    ) -> Iterator[AllabolagCompany]:
        """
        Iterate over companies.

        Args:
            since: Only return companies scraped after this timestamp (ISO format)
            batch_size: Number of records to fetch per query

        Yields:
            AllabolagCompany objects
        """
        conn = self._connect()
        try:
            if since:
                query = """
                    SELECT org_nr, name, legal_name, status, status_date,
                           registration_date, company_type, sni_code, sni_name,
                           municipality, county, parent_org_nr, parent_name,
                           revenue, profit, employees, allabolag_company_id, scraped_at
                    FROM companies
                    WHERE scraped_at > ?
                    ORDER BY scraped_at
                """
                cursor = conn.execute(query, (since,))
            else:
                query = """
                    SELECT org_nr, name, legal_name, status, status_date,
                           registration_date, company_type, sni_code, sni_name,
                           municipality, county, parent_org_nr, parent_name,
                           revenue, profit, employees, allabolag_company_id, scraped_at
                    FROM companies
                    ORDER BY scraped_at
                """
                cursor = conn.execute(query)

            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break
                for row in rows:
                    yield AllabolagCompany(
                        org_nr=row["org_nr"],
                        name=row["name"],
                        legal_name=row["legal_name"],
                        status=row["status"],
                        status_date=row["status_date"],
                        registration_date=row["registration_date"],
                        company_type=row["company_type"],
                        sni_code=row["sni_code"],
                        sni_name=row["sni_name"],
                        municipality=row["municipality"],
                        county=row["county"],
                        parent_org_nr=row["parent_org_nr"],
                        parent_name=row["parent_name"],
                        revenue=row["revenue"],
                        profit=row["profit"],
                        employees=row["employees"],
                        allabolag_company_id=row["allabolag_company_id"],
                        scraped_at=row["scraped_at"],
                    )
        finally:
            conn.close()

    def get_company(self, org_nr: str) -> Optional[AllabolagCompany]:
        """Get a single company by orgnummer."""
        conn = self._connect()
        try:
            row = conn.execute(
                """SELECT org_nr, name, legal_name, status, status_date,
                          registration_date, company_type, sni_code, sni_name,
                          municipality, county, parent_org_nr, parent_name,
                          revenue, profit, employees, allabolag_company_id, scraped_at
                   FROM companies WHERE org_nr = ?""",
                (org_nr,),
            ).fetchone()
            if row:
                return AllabolagCompany(**dict(row))
            return None
        finally:
            conn.close()

    # ========== Person Iteration ==========

    def iter_persons(
        self, since: Optional[str] = None, batch_size: int = 1000
    ) -> Iterator[AllabolagPerson]:
        """
        Iterate over persons.

        Args:
            since: Only return persons updated after this timestamp
            batch_size: Number of records to fetch per query

        Yields:
            AllabolagPerson objects
        """
        conn = self._connect()
        try:
            if since:
                query = """
                    SELECT id, allabolag_person_id, name, first_name, last_name,
                           birth_date, year_of_birth, age, gender, person_page_scraped_at
                    FROM persons
                    WHERE updated_at > ?
                    ORDER BY updated_at
                """
                cursor = conn.execute(query, (since,))
            else:
                query = """
                    SELECT id, allabolag_person_id, name, first_name, last_name,
                           birth_date, year_of_birth, age, gender, person_page_scraped_at
                    FROM persons
                    ORDER BY id
                """
                cursor = conn.execute(query)

            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break
                for row in rows:
                    yield AllabolagPerson(
                        id=row["id"],
                        allabolag_person_id=row["allabolag_person_id"],
                        name=row["name"],
                        first_name=row["first_name"],
                        last_name=row["last_name"],
                        birth_date=row["birth_date"],
                        year_of_birth=row["year_of_birth"],
                        age=row["age"],
                        gender=row["gender"],
                        scraped_at=row["person_page_scraped_at"],
                    )
        finally:
            conn.close()

    def get_person(self, person_id: int) -> Optional[AllabolagPerson]:
        """Get a single person by internal ID."""
        conn = self._connect()
        try:
            row = conn.execute(
                """SELECT id, allabolag_person_id, name, first_name, last_name,
                          birth_date, year_of_birth, age, gender, person_page_scraped_at
                   FROM persons WHERE id = ?""",
                (person_id,),
            ).fetchone()
            if row:
                return AllabolagPerson(
                    id=row["id"],
                    allabolag_person_id=row["allabolag_person_id"],
                    name=row["name"],
                    first_name=row["first_name"],
                    last_name=row["last_name"],
                    birth_date=row["birth_date"],
                    year_of_birth=row["year_of_birth"],
                    age=row["age"],
                    gender=row["gender"],
                    scraped_at=row["person_page_scraped_at"],
                )
            return None
        finally:
            conn.close()

    # ========== Role Iteration ==========

    def iter_roles(
        self, since: Optional[str] = None, batch_size: int = 1000
    ) -> Iterator[AllabolagRole]:
        """
        Iterate over roles (person-company relationships).

        Args:
            since: Only return roles discovered after this timestamp
            batch_size: Number of records to fetch per query

        Yields:
            AllabolagRole objects
        """
        conn = self._connect()
        try:
            if since:
                query = """
                    SELECT id, company_org_nr, person_id, role_type, role_group,
                           discovered_from, scraped_at
                    FROM roles
                    WHERE scraped_at > ?
                    ORDER BY scraped_at
                """
                cursor = conn.execute(query, (since,))
            else:
                query = """
                    SELECT id, company_org_nr, person_id, role_type, role_group,
                           discovered_from, scraped_at
                    FROM roles
                    ORDER BY id
                """
                cursor = conn.execute(query)

            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break
                for row in rows:
                    yield AllabolagRole(
                        id=row["id"],
                        company_org_nr=row["company_org_nr"],
                        person_id=row["person_id"],
                        role_type=row["role_type"],
                        role_group=row["role_group"],
                        discovered_from=row["discovered_from"],
                        scraped_at=row["scraped_at"],
                    )
        finally:
            conn.close()

    def get_roles_for_person(self, person_id: int) -> list[AllabolagRole]:
        """Get all roles for a person."""
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT id, company_org_nr, person_id, role_type, role_group,
                          discovered_from, scraped_at
                   FROM roles WHERE person_id = ?""",
                (person_id,),
            ).fetchall()
            return [
                AllabolagRole(
                    id=row["id"],
                    company_org_nr=row["company_org_nr"],
                    person_id=row["person_id"],
                    role_type=row["role_type"],
                    role_group=row["role_group"],
                    discovered_from=row["discovered_from"],
                    scraped_at=row["scraped_at"],
                )
                for row in rows
            ]
        finally:
            conn.close()

    def get_roles_for_company(self, org_nr: str) -> list[AllabolagRole]:
        """Get all roles for a company."""
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT id, company_org_nr, person_id, role_type, role_group,
                          discovered_from, scraped_at
                   FROM roles WHERE company_org_nr = ?""",
                (org_nr,),
            ).fetchall()
            return [
                AllabolagRole(
                    id=row["id"],
                    company_org_nr=row["company_org_nr"],
                    person_id=row["person_id"],
                    role_type=row["role_type"],
                    role_group=row["role_group"],
                    discovered_from=row["discovered_from"],
                    scraped_at=row["scraped_at"],
                )
                for row in rows
            ]
        finally:
            conn.close()

    # ========== Mention Conversion ==========

    def company_to_mention(
        self, company: AllabolagCompany, provenance_id: UUID
    ) -> MentionCreate:
        """
        Convert an Allabolag company to a mention.

        Args:
            company: AllabolagCompany from database
            provenance_id: UUID of provenance record

        Returns:
            MentionCreate for resolution pipeline
        """
        return MentionCreate(
            mention_type=EntityType.COMPANY,
            surface_form=company.name,
            normalized_form=self._normalize_company_name(company.name),
            extracted_orgnummer=company.org_nr,
            extracted_attributes={
                "legal_name": company.legal_name,
                "status": company.status,
                "company_type": company.company_type,
                "sni_code": company.sni_code,
                "sni_name": company.sni_name,
                "municipality": company.municipality,
                "county": company.county,
                "revenue_ksek": company.revenue,
                "employees": company.employees,
                "registration_date": company.registration_date,
                "parent_org_nr": company.parent_org_nr,
            },
            provenance_id=provenance_id,
            document_location=f"allabolag:company:{company.org_nr}",
        )

    def person_to_mention(
        self, person: AllabolagPerson, provenance_id: UUID
    ) -> MentionCreate:
        """
        Convert an Allabolag person to a mention.

        Args:
            person: AllabolagPerson from database
            provenance_id: UUID of provenance record

        Returns:
            MentionCreate for resolution pipeline
        """
        return MentionCreate(
            mention_type=EntityType.PERSON,
            surface_form=person.name,
            normalized_form=self._normalize_person_name(person.name),
            extracted_attributes={
                "first_name": person.first_name,
                "last_name": person.last_name,
                "birth_date": person.birth_date,
                "year_of_birth": person.year_of_birth,
                "gender": person.gender,
                "allabolag_person_id": person.allabolag_person_id,
            },
            provenance_id=provenance_id,
            document_location=f"allabolag:person:{person.allabolag_person_id}",
        )

    def create_provenance(self, scraped_at: str) -> ProvenanceCreate:
        """
        Create a provenance record for Allabolag data.

        Args:
            scraped_at: Timestamp when data was scraped

        Returns:
            ProvenanceCreate for the data source
        """
        return ProvenanceCreate(
            source_type=SourceType.ALLABOLAG_SCRAPE,
            source_id=f"allabolag:{scraped_at}",
            source_url="[REDACTED_COMMERCIAL_API]",
            extraction_method="web_scraper",
            extraction_timestamp=datetime.fromisoformat(scraped_at),
            extraction_system_version="allabolag_scraper_v1",
        )

    # ========== Network Queries ==========

    def get_person_network(self, person_id: int, depth: int = 2) -> dict:
        """
        Get a person's corporate network.

        Args:
            person_id: Person ID to start from
            depth: How many hops to traverse

        Returns:
            Dict with persons, companies, and roles in network
        """
        conn = self._connect()
        try:
            visited_persons = {person_id}
            visited_companies = set()
            all_roles = []

            current_persons = {person_id}

            for _ in range(depth):
                if not current_persons:
                    break

                # Find companies for current persons
                placeholders = ",".join("?" * len(current_persons))
                rows = conn.execute(
                    f"""SELECT DISTINCT company_org_nr FROM roles
                        WHERE person_id IN ({placeholders})""",
                    tuple(current_persons),
                ).fetchall()

                new_companies = {r[0] for r in rows} - visited_companies
                visited_companies.update(new_companies)

                if not new_companies:
                    break

                # Find persons for new companies
                placeholders = ",".join("?" * len(new_companies))
                rows = conn.execute(
                    f"""SELECT DISTINCT person_id FROM roles
                        WHERE company_org_nr IN ({placeholders})""",
                    tuple(new_companies),
                ).fetchall()

                current_persons = {r[0] for r in rows} - visited_persons
                visited_persons.update(current_persons)

            # Fetch all roles for the network
            if visited_persons:
                placeholders = ",".join("?" * len(visited_persons))
                rows = conn.execute(
                    f"""SELECT id, company_org_nr, person_id, role_type, role_group,
                               discovered_from, scraped_at
                        FROM roles WHERE person_id IN ({placeholders})""",
                    tuple(visited_persons),
                ).fetchall()
                all_roles = [dict(r) for r in rows]

            return {
                "person_ids": list(visited_persons),
                "company_org_nrs": list(visited_companies),
                "roles": all_roles,
                "depth_reached": depth,
            }
        finally:
            conn.close()

    def get_company_network(self, org_nr: str, depth: int = 2) -> dict:
        """
        Get a company's ownership and director network.

        Args:
            org_nr: Company orgnummer to start from
            depth: How many hops to traverse

        Returns:
            Dict with persons, companies, and roles in network
        """
        conn = self._connect()
        try:
            visited_persons = set()
            visited_companies = {org_nr}
            all_roles = []

            current_companies = {org_nr}

            for _ in range(depth):
                if not current_companies:
                    break

                # Find persons for current companies
                placeholders = ",".join("?" * len(current_companies))
                rows = conn.execute(
                    f"""SELECT DISTINCT person_id FROM roles
                        WHERE company_org_nr IN ({placeholders})""",
                    tuple(current_companies),
                ).fetchall()

                new_persons = {r[0] for r in rows} - visited_persons
                visited_persons.update(new_persons)

                if not new_persons:
                    break

                # Find companies for new persons
                placeholders = ",".join("?" * len(new_persons))
                rows = conn.execute(
                    f"""SELECT DISTINCT company_org_nr FROM roles
                        WHERE person_id IN ({placeholders})""",
                    tuple(new_persons),
                ).fetchall()

                current_companies = {r[0] for r in rows} - visited_companies
                visited_companies.update(current_companies)

            # Fetch all roles for the network
            if visited_companies:
                placeholders = ",".join("?" * len(visited_companies))
                rows = conn.execute(
                    f"""SELECT id, company_org_nr, person_id, role_type, role_group,
                               discovered_from, scraped_at
                        FROM roles WHERE company_org_nr IN ({placeholders})""",
                    tuple(visited_companies),
                ).fetchall()
                all_roles = [dict(r) for r in rows]

            return {
                "person_ids": list(visited_persons),
                "company_org_nrs": list(visited_companies),
                "roles": all_roles,
                "depth_reached": depth,
            }
        finally:
            conn.close()

    # ========== Helper Methods ==========

    def _normalize_company_name(self, name: str) -> str:
        """Normalize a company name for matching."""
        if not name:
            return ""
        # Remove common suffixes, lowercase, strip whitespace
        normalized = name.upper().strip()
        for suffix in [" AB", " HB", " KB", " EF", " I LIKVIDATION"]:
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)].strip()
        return normalized

    def _normalize_person_name(self, name: str) -> str:
        """Normalize a person name for matching."""
        if not name:
            return ""
        # Uppercase, strip, normalize whitespace
        return " ".join(name.upper().split())
