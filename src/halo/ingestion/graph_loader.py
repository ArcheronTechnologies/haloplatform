"""
Graph Loader - Loads data from ingestion adapters into the intelligence graph.

This module connects data sources (Bolagsverket, SCB, etc.) to the graph database,
transforming raw API data into graph nodes and edges.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from halo.graph.client import GraphClient, create_graph_client
from halo.graph.schema import Company, Person, Address
from halo.graph.edges import DirectsEdge, RegisteredAtEdge, OwnsEdge
from halo.ingestion.bolagsverket_hvd import BolagsverketHVDAdapter
from halo.ingestion.base_adapter import IngestionRecord

logger = logging.getLogger(__name__)


@dataclass
class LoadResult:
    """Result of loading an entity into the graph."""
    entity_id: str
    entity_type: str
    created: bool  # True if new, False if updated
    edges_created: int
    source: str
    timestamp: datetime


class GraphLoader:
    """
    Loads data from ingestion adapters into the intelligence graph.

    Transforms raw API data into graph nodes and edges,
    handling deduplication and relationship creation.
    """

    def __init__(
        self,
        graph_client: Optional[GraphClient] = None,
        bolagsverket_adapter: Optional[BolagsverketHVDAdapter] = None,
    ):
        """
        Initialize the graph loader.

        Args:
            graph_client: Graph client (defaults to NetworkX for development)
            bolagsverket_adapter: Bolagsverket HVD adapter (created if not provided)
        """
        self.graph = graph_client or GraphClient()
        self.bolagsverket = bolagsverket_adapter or BolagsverketHVDAdapter()
        self._address_cache: dict[str, str] = {}  # Cache address -> ID mapping

    async def __aenter__(self):
        await self.graph.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.graph.close()
        await self.bolagsverket.close()

    # =========================================================================
    # Bolagsverket HVD Loading
    # =========================================================================

    async def load_company_from_bolagsverket(
        self,
        orgnr: str,
        include_directors: bool = True,
        include_address: bool = True,
    ) -> Optional[LoadResult]:
        """
        Load a company from Bolagsverket HVD API into the graph.

        Args:
            orgnr: Swedish organisation number (10 digits)
            include_directors: Load director relationships
            include_address: Load registered address

        Returns:
            LoadResult with details of what was loaded
        """
        # Normalize orgnr
        orgnr = orgnr.replace("-", "").replace(" ", "")

        # Fetch from Bolagsverket
        record = await self.bolagsverket.fetch_company(orgnr)
        if not record:
            logger.info(f"Company not found in Bolagsverket: {orgnr}")
            return None

        # Transform and load
        return await self._load_bolagsverket_company(
            record,
            include_directors=include_directors,
            include_address=include_address,
        )

    async def load_companies_batch(
        self,
        orgnrs: list[str],
        include_directors: bool = True,
        include_address: bool = True,
    ) -> list[LoadResult]:
        """
        Load multiple companies from Bolagsverket.

        Args:
            orgnrs: List of organisation numbers
            include_directors: Load director relationships
            include_address: Load registered addresses

        Returns:
            List of LoadResults for each company
        """
        results = []
        for orgnr in orgnrs:
            try:
                result = await self.load_company_from_bolagsverket(
                    orgnr,
                    include_directors=include_directors,
                    include_address=include_address,
                )
                if result:
                    results.append(result)
            except Exception as e:
                logger.error(f"Failed to load company {orgnr}: {e}")
        return results

    async def _load_bolagsverket_company(
        self,
        record: IngestionRecord,
        include_directors: bool = True,
        include_address: bool = True,
    ) -> LoadResult:
        """Transform and load a Bolagsverket company record."""
        data = record.raw_data
        edges_created = 0

        # Extract company data
        company = self._transform_bolagsverket_company(data)

        # Check if company already exists
        existing = await self.graph.find_company_by_orgnr(company.orgnr)
        created = existing is None

        # Add/update company
        company_id = await self.graph.add_company(company)
        logger.info(f"{'Created' if created else 'Updated'} company: {company.orgnr}")

        # Load address if present
        if include_address:
            address_id = await self._load_bolagsverket_address(data, company_id)
            if address_id:
                edges_created += 1

        # Load directors/board members if present
        if include_directors:
            director_count = await self._load_bolagsverket_directors(data, company_id)
            edges_created += director_count

        return LoadResult(
            entity_id=company_id,
            entity_type="Company",
            created=created,
            edges_created=edges_created,
            source="bolagsverket_hvd",
            timestamp=datetime.utcnow(),
        )

    def _transform_bolagsverket_company(self, data: dict[str, Any]) -> Company:
        """Transform Bolagsverket HVD raw data to Company node."""
        # Extract organisationsidentitet
        org_id = data.get("organisationsidentitet", {})
        orgnr = org_id.get("identitetsbeteckning", "")

        # Extract names from HVD format
        names = []
        namn_data = data.get("organisationsnamn", {})
        namn_lista = namn_data.get("organisationsnamnLista", [])
        for name_entry in namn_lista:
            names.append({
                "name": name_entry.get("namn", ""),
                "type": name_entry.get("organisationsnamntyp", {}).get("kod", ""),
                "from": name_entry.get("registreringsdatum"),
                "to": None,
            })

        # Extract SNI codes from HVD format
        sni_codes = []
        naringsgren = data.get("naringsgrenOrganisation", {})
        for sni in naringsgren.get("sni", []):
            sni_codes.append({
                "code": sni.get("kod", ""),
                "description": sni.get("klartext", ""),
            })

        # Extract legal form from HVD format
        org_form = data.get("organisationsform", {})
        legal_form = org_form.get("kod", "")

        # Extract status - verksamOrganisation.kod == "JA" means active
        verksamhet = data.get("verksamOrganisation", {})
        is_active = verksamhet.get("kod") == "JA"
        is_deregistered = data.get("avregistreradOrganisation") is not None

        status = {
            "code": "deregistered" if is_deregistered else ("active" if is_active else "inactive"),
            "text": "Avregistrerad" if is_deregistered else ("Aktiv" if is_active else "Inaktiv"),
        }

        # Extract formation/registration date
        org_datum = data.get("organisationsdatum", {})
        formation = {
            "date": org_datum.get("registreringsdatum"),
            "registered": org_datum.get("registreringsdatum"),
        }

        # Create Company node
        return Company(
            id=f"company-{orgnr}",
            orgnr=orgnr,
            names=names,
            legal_form=legal_form,
            status=status,
            formation=formation,
            sni_codes=sni_codes,
            employees={"count": None},  # Not available in HVD
            f_skatt={"registered": None},  # Not available in HVD
            vat={"registered": None},  # Not available in HVD
            sources=["bolagsverket_hvd"],
        )

    async def _load_bolagsverket_address(
        self,
        data: dict[str, Any],
        company_id: str,
    ) -> Optional[str]:
        """Load address from Bolagsverket HVD data and create relationship."""
        # Extract postal address from HVD format
        post_org = data.get("postadressOrganisation", {})
        postadress = post_org.get("postadress", {})

        if not postadress:
            return None

        # Build address key for deduplication (HVD format uses utdelningsadress)
        street = postadress.get("utdelningsadress") or ""
        postal_code = postadress.get("postnummer") or ""
        city = postadress.get("postort") or ""
        co_address = postadress.get("coAdress") or ""

        address_key = f"{street}|{postal_code}|{city}".lower()

        # Check cache
        if address_key in self._address_cache:
            address_id = self._address_cache[address_key]
        else:
            # Create new address using schema-compliant format
            raw_parts = [co_address, street, postal_code, city]
            raw_addr = ", ".join(p for p in raw_parts if p)
            address = Address(
                id=f"address-{uuid4().hex[:8]}",
                raw_strings=[raw_addr] if raw_addr else [],
                normalized={
                    "street": street,
                    "co_address": co_address,
                    "postal_code": postal_code,
                    "city": city,
                    "country": "SE",
                },
                type="registered",
                sources=["bolagsverket_hvd"],
            )
            address_id = await self.graph.add_address(address)
            self._address_cache[address_key] = address_id
            logger.debug(f"Created address: {postal_code} {city}")

        # Create registration edge
        edge = RegisteredAtEdge(
            from_id=company_id,
            to_id=address_id,
            type="registered",
        )
        await self.graph.add_registration(edge)

        return address_id

    async def _load_bolagsverket_directors(
        self,
        data: dict[str, Any],
        company_id: str,
    ) -> int:
        """Load directors/board members from Bolagsverket data.

        Note: HVD (free) API does not include director data.
        This is available in the paid Företagsinformation API.
        This method handles it gracefully by returning 0 if no data available.
        """
        # Try HVD format (usually empty) and Företagsinformation format
        funktionarer = data.get("funktionarer", {})
        styrelse = funktionarer.get("styrelse", [])

        edges_created = 0

        for member in styrelse:
            # Get person data
            person_data = member.get("person", {})
            name = person_data.get("namn", "")
            role = member.get("funktion", "styrelseledamot")

            if not name:
                continue

            # Create person node
            person_id = f"person-{uuid4().hex[:8]}"
            person = Person(
                id=person_id,
                names=[{"name": name}],
            )
            await self.graph.add_person(person)

            # Create directorship edge
            edge = DirectsEdge(
                from_id=person_id,
                to_id=company_id,
                role=role,
            )
            await self.graph.add_directorship(edge)
            edges_created += 1

            logger.debug(f"Created director: {name} -> {company_id}")

        return edges_created

    # =========================================================================
    # Data enrichment
    # =========================================================================

    async def enrich_company(
        self,
        company_id: str,
        refresh: bool = False,
    ) -> Optional[LoadResult]:
        """
        Enrich an existing company with fresh data from Bolagsverket.

        Args:
            company_id: Graph company ID
            refresh: Force refresh even if recently updated

        Returns:
            LoadResult with enrichment details
        """
        # Get existing company
        company = await self.graph.get_company(company_id)
        if not company:
            logger.warning(f"Company not found for enrichment: {company_id}")
            return None

        orgnr = company.get("orgnr")
        if not orgnr:
            logger.warning(f"Company has no orgnr: {company_id}")
            return None

        # Load fresh data
        return await self.load_company_from_bolagsverket(orgnr)

    async def build_ownership_network(
        self,
        seed_company_id: str,
        max_depth: int = 3,
    ) -> dict[str, Any]:
        """
        Build ownership network from a seed company.

        Traverses ownership relationships to find connected entities.
        Note: Full ownership data requires Bolagsverket Ägandeinformation API.

        Args:
            seed_company_id: Starting company ID
            max_depth: Maximum ownership depth to traverse

        Returns:
            Network summary with companies and ownership links
        """
        chain = await self.graph.get_ownership_chain(seed_company_id, max_depth)

        return {
            "seed_company": seed_company_id,
            "ownership_depth": max_depth,
            "ownership_links": len(chain),
            "chain": chain,
        }

    # =========================================================================
    # Statistics
    # =========================================================================

    async def get_load_statistics(self) -> dict[str, Any]:
        """Get statistics about loaded data."""
        stats = await self.graph.get_statistics()

        return {
            "graph_statistics": stats,
            "address_cache_size": len(self._address_cache),
        }


# Factory function for easy creation
def create_graph_loader(
    backend_type: str = "networkx",
    **kwargs,
) -> GraphLoader:
    """
    Create a graph loader with specified backend.

    Args:
        backend_type: "networkx" or "neo4j"
        **kwargs: Backend-specific configuration

    Returns:
        Configured GraphLoader
    """
    graph = create_graph_client(backend_type, **kwargs)
    return GraphLoader(graph_client=graph)


# Convenience function for CLI usage
async def load_companies_from_list(
    orgnrs: list[str],
    backend_type: str = "networkx",
    **kwargs,
) -> list[LoadResult]:
    """
    Load a list of companies into the graph.

    Convenience function for scripts and CLI.

    Args:
        orgnrs: List of organisation numbers
        backend_type: Graph backend type
        **kwargs: Backend configuration

    Returns:
        List of LoadResults
    """
    loader = create_graph_loader(backend_type, **kwargs)

    async with loader:
        return await loader.load_companies_batch(orgnrs)
