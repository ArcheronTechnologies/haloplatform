#!/usr/bin/env python3
"""
Load Swedish companies from SCB Företagsregistret into the intelligence graph.

SCB provides a comprehensive database of 1.8M Swedish companies with:
- Org number, name, legal form
- Address (postal)
- SNI industry codes
- Registration status
- Employee size class
- Ownership category
"""

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from halo.ingestion.scb_foretag import SCBForetagAdapter
from halo.graph.client import GraphClient
from halo.graph.schema import Company, Address
from halo.graph.edges import RegisteredAtEdge

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SCBGraphLoader:
    """Load SCB company data into the intelligence graph."""

    def __init__(
        self,
        adapter: Optional[SCBForetagAdapter] = None,
        graph: Optional[GraphClient] = None,
    ):
        self.adapter = adapter or SCBForetagAdapter(
            cert_path=Path('./halo/secrets/scb_cert.p12'),
            cert_password='[REDACTED_PASSWORD]',
        )
        self.graph = graph or GraphClient()
        self._address_cache: dict[str, str] = {}

    async def __aenter__(self):
        await self.graph.connect()
        return self

    async def __aexit__(self, *args):
        await self.adapter.close()
        await self.graph.close()

    def _transform_scb_company(self, raw_data: dict) -> Company:
        """Transform SCB raw data to Company node."""
        orgnr = raw_data.get("OrgNr", "")

        # Build names list
        names = [{
            "name": raw_data.get("Företagsnamn", ""),
            "type": "main",
            "from": raw_data.get("Registreringsdatum"),
            "to": None,
        }]

        # Legal form code -> description
        legal_form = raw_data.get("Juridisk form, kod", "")

        # Status
        status_code = raw_data.get("Företagsstatus, kod", "0")
        is_active = status_code == "1"
        status = {
            "code": "active" if is_active else "inactive",
            "text": raw_data.get("Företagsstatus", "Unknown"),
        }

        # Formation dates
        formation = {
            "date": raw_data.get("Startdatum"),
            "registered": raw_data.get("Registreringsdatum"),
        }

        # SNI codes (up to 5 branches)
        sni_codes = []
        for i in range(1, 6):
            sni_code = raw_data.get(f"Bransch_{i}, kod", "").strip()
            sni_desc = raw_data.get(f"Bransch_{i}", "").strip()
            if sni_code:
                sni_codes.append({
                    "code": sni_code,
                    "description": sni_desc,
                })

        # Employee size class
        employees = {
            "size_class": raw_data.get("Stkl, kod", "").strip(),
            "size_class_text": raw_data.get("Storleksklass", ""),
        }

        # Tax registrations
        f_skatt = {
            "status": raw_data.get("Fskattstatus", ""),
            "registered": raw_data.get("Fskattstatus, kod", "") != "0",
        }
        vat = {
            "status": raw_data.get("Momsstatus", ""),
            "registered": raw_data.get("Momsstatus, kod", "") != "0",
        }

        return Company(
            id=f"company-{orgnr}",
            orgnr=orgnr,
            names=names,
            legal_form=legal_form,
            status=status,
            formation=formation,
            sni_codes=sni_codes,
            employees=employees,
            f_skatt=f_skatt,
            vat=vat,
            sources=["scb_foretagsregistret"],
        )

    async def _load_address(self, raw_data: dict, company_id: str) -> Optional[str]:
        """Load address from SCB data and create relationship."""
        street = raw_data.get("PostAdress", "").strip()
        postal_code = raw_data.get("PostNr", "").strip()
        city = raw_data.get("PostOrt", "").strip()
        co_address = raw_data.get("COAdress", "").strip()

        if not (street or postal_code or city):
            return None

        # Build address key for deduplication
        address_key = f"{street}|{postal_code}|{city}".lower()

        if address_key in self._address_cache:
            address_id = self._address_cache[address_key]
        else:
            from uuid import uuid4

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
                type="postal",
                sources=["scb_foretagsregistret"],
            )
            address_id = await self.graph.add_address(address)
            self._address_cache[address_key] = address_id

        # Create registration edge
        edge = RegisteredAtEdge(
            from_id=company_id,
            to_id=address_id,
            type="postal",
        )
        await self.graph.add_registration(edge)

        return address_id

    async def load_companies(
        self,
        limit: int = 1000,
        legal_form: Optional[str] = None,
        only_active: bool = True,
        include_addresses: bool = True,
    ) -> dict:
        """
        Load companies from SCB into the graph.

        Args:
            limit: Maximum number of companies to load
            legal_form: Filter by legal form (e.g., "49" for Aktiebolag)
            only_active: Only load active companies
            include_addresses: Create address nodes and relationships

        Returns:
            Summary statistics
        """
        logger.info(f"Loading up to {limit} companies from SCB...")

        companies_loaded = 0
        addresses_loaded = 0
        offset = 0
        batch_size = min(2000, limit)  # SCB max is 2000 per request

        while companies_loaded < limit:
            remaining = limit - companies_loaded
            fetch_count = min(batch_size, remaining)

            logger.info(f"Fetching batch: offset={offset}, limit={fetch_count}")

            records = await self.adapter.fetch_companies_batch(
                offset=offset,
                limit=fetch_count,
                only_active=only_active,
                legal_form=legal_form,
            )

            if not records:
                logger.info("No more records available")
                break

            for record in records:
                if companies_loaded >= limit:
                    break

                # Transform to Company node
                company = self._transform_scb_company(record.raw_data)
                await self.graph.add_company(company)
                companies_loaded += 1

                # Load address
                if include_addresses:
                    addr_id = await self._load_address(record.raw_data, company.id)
                    if addr_id:
                        addresses_loaded += 1

                if companies_loaded % 100 == 0:
                    logger.info(f"Progress: {companies_loaded}/{limit} companies")

            offset += len(records)

            # If we got fewer than requested, we've reached the end
            if len(records) < fetch_count:
                break

        logger.info(f"Loaded {companies_loaded} companies and {addresses_loaded} addresses")

        return {
            "companies_loaded": companies_loaded,
            "addresses_loaded": addresses_loaded,
            "address_cache_size": len(self._address_cache),
        }


async def main():
    print("=" * 60)
    print("Loading Swedish Companies from SCB Företagsregistret")
    print("=" * 60)

    # Configuration
    target_count = 1000
    legal_form = "49"  # Aktiebolag (AB)

    loader = SCBGraphLoader()

    async with loader:
        # First, get some stats
        print("\n1. Checking SCB API...")
        healthy = await loader.adapter.healthcheck()
        print(f"   API Status: {'OK' if healthy else 'FAILED'}")

        total = await loader.adapter.count_companies(only_active=True)
        ab_count = await loader.adapter.count_companies(only_active=True, legal_form=legal_form)
        print(f"   Total active companies: {total:,}")
        print(f"   Total active Aktiebolag: {ab_count:,}")

        # Load companies
        print(f"\n2. Loading {target_count} Aktiebolag companies...")
        result = await loader.load_companies(
            limit=target_count,
            legal_form=legal_form,
            only_active=True,
            include_addresses=True,
        )

        print(f"\n3. Results:")
        print(f"   Companies loaded: {result['companies_loaded']}")
        print(f"   Addresses loaded: {result['addresses_loaded']}")
        print(f"   Address cache size: {result['address_cache_size']}")

        # Get graph stats
        stats = await loader.graph.get_statistics()
        print(f"\n4. Graph Statistics:")
        print(f"   Total nodes: {stats.get('total_nodes', stats.get('nodes', 0))}")
        print(f"   Total edges: {stats.get('total_edges', stats.get('edges', 0))}")
        print(f"   Companies: {stats.get('company_count', stats.get('companies', 0))}")
        print(f"   Addresses: {stats.get('address_count', stats.get('addresses', 0))}")

        # Save graph
        data_dir = Path("./halo/data")
        data_dir.mkdir(parents=True, exist_ok=True)

        graph_file = data_dir / "scb_graph.pickle"
        # NetworkX graph can be saved with pickle
        import pickle
        with open(graph_file, "wb") as f:
            pickle.dump(loader.graph.backend.graph, f)
        print(f"\n5. Graph saved to {graph_file}")

        # Also save company list for reference
        orgnrs_file = data_dir / "scb_orgnrs.txt"
        companies = []
        for node_id in loader.graph.backend.graph.nodes():
            if node_id.startswith("company-"):
                node_data = loader.graph.backend.graph.nodes[node_id]
                orgnr = node_data.get("orgnr", "")
                name = ""
                names = node_data.get("names", [])
                if names:
                    name = names[0].get("name", "")
                companies.append(f"{orgnr}\t{name}")

        with open(orgnrs_file, "w") as f:
            f.write("\n".join(companies))
        print(f"   Company list saved to {orgnrs_file}")

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
