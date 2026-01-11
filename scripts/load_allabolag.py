#!/usr/bin/env python3
"""
Load scraped Allabolag.se data into the intelligence graph.

This integrates the allabolag scraper output into the Halo demo platform:
1. Load companies and directors from allabolag SQLite database
2. Enrich existing graph or create new nodes
3. Add allabolag-specific data (signatories, purpose, financials)
4. Re-run pattern detection with enriched data

Data flow:
  SCB orgnrs -> allabolag scraper -> SQLite -> this script -> NetworkX graph -> demo API
"""

import json
import pickle
import logging
import sqlite3
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

import networkx as nx

from halo.graph.schema import Company, Person, Address
from halo.graph.edges import DirectsEdge, RegisteredAtEdge

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
ALLABOLAG_DB = PROJECT_ROOT / "allabolag_scrape.db"
GRAPH_PICKLE = PROJECT_ROOT / "data" / "company_graph.pickle"
ALERTS_JSON = PROJECT_ROOT / "data" / "alerts.json"
INTEL_RESULTS = PROJECT_ROOT / "data" / "intelligence_results.json"


@dataclass
class AllabolagCompany:
    """Company data from allabolag scraper."""
    orgnr: str
    name: str
    legal_form: Optional[str] = None
    status: Optional[str] = None
    registration_date: Optional[str] = None
    street_address: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    municipality: Optional[str] = None
    county: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    sni_code: Optional[str] = None
    sni_description: Optional[str] = None
    purpose: Optional[str] = None
    revenue: Optional[int] = None
    profit: Optional[int] = None
    employees: Optional[int] = None
    share_capital: Optional[int] = None
    parent_company: Optional[str] = None
    num_subsidiaries: Optional[int] = None
    signatories: list = field(default_factory=list)
    directors: list = field(default_factory=list)
    scraped_at: Optional[str] = None


class AllabolagGraphLoader:
    """Load allabolag data into NetworkX graph."""

    def __init__(self, db_path: Path = ALLABOLAG_DB):
        self.db_path = db_path
        self.graph: Optional[nx.MultiDiGraph] = None
        self.persons_by_name: dict[str, str] = {}
        self.persons_by_id: dict[str, str] = {}  # allabolag person_id -> graph node id
        self.addresses_by_key: dict[str, str] = {}
        self.stats = {
            "companies_loaded": 0,
            "companies_updated": 0,
            "persons_created": 0,
            "persons_merged": 0,
            "edges_created": 0,
            "addresses_created": 0,
        }

    def load_existing_graph(self, graph_path: Path = GRAPH_PICKLE) -> bool:
        """Load existing graph if available."""
        if graph_path.exists():
            logger.info(f"Loading existing graph from {graph_path}")
            with open(graph_path, "rb") as f:
                self.graph = pickle.load(f)

            # Build person lookup from existing graph
            for node_id in self.graph.nodes():
                if node_id.startswith("person-"):
                    node_data = self.graph.nodes[node_id]
                    for name_entry in node_data.get("names", []):
                        name_key = name_entry.get("name", "").lower().strip()
                        if name_key:
                            self.persons_by_name[name_key] = node_id

            logger.info(f"Loaded graph with {self.graph.number_of_nodes()} nodes, "
                       f"{self.graph.number_of_edges()} edges")
            return True
        else:
            logger.info("No existing graph found, creating new one")
            self.graph = nx.MultiDiGraph()
            return False

    def load_companies_from_db(self) -> list[AllabolagCompany]:
        """Load all scraped companies from SQLite database."""
        if not self.db_path.exists():
            logger.error(f"Database not found: {self.db_path}")
            return []

        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        # Load companies
        companies = []
        rows = conn.execute("SELECT * FROM companies").fetchall()

        for row in rows:
            company = AllabolagCompany(
                orgnr=row["orgnr"],
                name=row["name"],
                legal_form=row["legal_form"],
                status=row["status"],
                registration_date=row["registration_date"],
                street_address=row["street_address"],
                postal_code=row["postal_code"],
                city=row["city"],
                municipality=row["municipality"],
                county=row["county"],
                phone=row["phone"],
                email=row["email"],
                website=row["website"],
                sni_code=row["sni_code"],
                sni_description=row["sni_description"],
                purpose=row["purpose"],
                revenue=row["revenue"],
                profit=row["profit"],
                employees=row["employees"],
                share_capital=row["share_capital"],
                parent_company=row["parent_company"],
                num_subsidiaries=row["num_subsidiaries"],
                scraped_at=row["scraped_at"],
            )

            # Parse signatories JSON
            signatories_json = row["signatories"]
            if signatories_json:
                try:
                    company.signatories = json.loads(signatories_json)
                except json.JSONDecodeError:
                    pass

            # Load directors for this company
            directors = conn.execute(
                "SELECT * FROM directors WHERE orgnr = ?",
                (company.orgnr,)
            ).fetchall()

            for d in directors:
                company.directors.append({
                    "name": d["name"],
                    "role": d["role"],
                    "role_group": d["role_group"],
                    "person_type": d["person_type"],
                    "person_id": d["person_id"],
                    "birth_date": d["birth_date"],
                    "birth_year": d["birth_year"],
                })

            companies.append(company)

        conn.close()
        logger.info(f"Loaded {len(companies)} companies from allabolag database")
        return companies

    def add_company_to_graph(self, company: AllabolagCompany):
        """Add or update a company in the graph."""
        company_id = f"company-{company.orgnr}"

        # Check if company exists
        if company_id in self.graph.nodes:
            # Update existing company with allabolag data
            existing = self.graph.nodes[company_id]
            self._merge_company_data(existing, company)
            self.stats["companies_updated"] += 1
        else:
            # Create new company node
            graph_company = Company(
                id=company_id,
                orgnr=company.orgnr,
                names=[{"name": company.name, "type": "primary", "source": "allabolag"}],
                legal_form=company.legal_form or "",
                status={"code": company.status or "UNKNOWN"},
                sni_codes=[{"code": company.sni_code, "description": company.sni_description}] if company.sni_code else [],
                employees={"count": company.employees or 0, "source": "allabolag"} if company.employees else None,
                revenue={"amount": company.revenue, "source": "allabolag"} if company.revenue else None,
                sources=["allabolag"],
            )

            # Add allabolag-specific fields as extra attributes
            node_data = asdict(graph_company)
            node_data["_type"] = "Company"
            node_data["purpose"] = company.purpose
            node_data["profit"] = company.profit
            node_data["share_capital"] = company.share_capital
            node_data["signatories"] = company.signatories
            node_data["parent_company"] = company.parent_company
            node_data["num_subsidiaries"] = company.num_subsidiaries
            node_data["contact"] = {
                "phone": company.phone,
                "email": company.email,
                "website": company.website,
            }

            self.graph.add_node(company_id, **node_data)
            self.stats["companies_loaded"] += 1

        # Add directors
        for director in company.directors:
            person_id = self._add_person(director)
            if person_id:
                self._add_directorship(person_id, company_id, director)

        # Add address
        if company.city or company.street_address:
            address_id = self._add_address(company)
            if address_id:
                self._add_registered_at(company_id, address_id)

    def _merge_company_data(self, existing: dict, company: AllabolagCompany):
        """Merge allabolag data into existing company node."""
        # Add allabolag to sources
        sources = existing.get("sources", [])
        if "allabolag" not in sources:
            sources.append("allabolag")
            existing["sources"] = sources

        # Update financials if we have them
        if company.employees and (not existing.get("employees") or existing["employees"].get("source") != "scb"):
            existing["employees"] = {"count": company.employees, "source": "allabolag"}

        if company.revenue and not existing.get("revenue"):
            existing["revenue"] = {"amount": company.revenue, "source": "allabolag"}

        # Add allabolag-specific data
        existing["purpose"] = company.purpose
        existing["profit"] = company.profit
        existing["share_capital"] = company.share_capital
        existing["signatories"] = company.signatories
        existing["parent_company"] = company.parent_company
        existing["num_subsidiaries"] = company.num_subsidiaries
        existing["contact"] = {
            "phone": company.phone,
            "email": company.email,
            "website": company.website,
        }

    def _add_person(self, director: dict) -> Optional[str]:
        """Add a person node, deduplicating by name and allabolag person_id."""
        name = (director.get("name") or "").strip()
        if not name:
            return None

        allabolag_id = director.get("person_id")
        person_type = director.get("person_type", "Person")

        # Skip company auditors (they're companies, not people)
        if person_type == "Company":
            return self._add_company_auditor(director)

        # Check if we've seen this allabolag person ID before
        if allabolag_id and allabolag_id in self.persons_by_id:
            return self.persons_by_id[allabolag_id]

        # Check by name
        name_key = name.lower()
        if name_key in self.persons_by_name:
            existing_id = self.persons_by_name[name_key]
            # Store the allabolag ID mapping
            if allabolag_id:
                self.persons_by_id[allabolag_id] = existing_id
            self.stats["persons_merged"] += 1
            return existing_id

        # Create new person
        person_id = f"person-{len(self.persons_by_name)}"
        person = Person(
            id=person_id,
            names=[{"name": name, "source": "allabolag"}],
            sources=["allabolag"],
        )

        # Add birth info if available
        node_data = asdict(person)
        node_data["_type"] = "Person"
        if director.get("birth_date"):
            node_data["birth_date"] = director["birth_date"]
        if director.get("birth_year"):
            node_data["birth_year"] = director["birth_year"]
        node_data["allabolag_id"] = allabolag_id

        self.graph.add_node(person_id, **node_data)
        self.persons_by_name[name_key] = person_id
        if allabolag_id:
            self.persons_by_id[allabolag_id] = person_id
        self.stats["persons_created"] += 1

        return person_id

    def _add_company_auditor(self, director: dict) -> Optional[str]:
        """Add a company (like BDO Sweden AB) as an auditor node."""
        name = (director.get("name") or "").strip()
        if not name:
            return None

        # Use a special prefix for auditing companies
        auditor_id = f"auditor-company-{name.lower().replace(' ', '-')}"

        if auditor_id not in self.graph.nodes:
            self.graph.add_node(auditor_id, **{
                "_type": "AuditingCompany",
                "name": name,
                "allabolag_id": director.get("person_id"),
                "sources": ["allabolag"],
            })

        return auditor_id

    def _add_directorship(self, person_id: str, company_id: str, director: dict):
        """Add a directorship edge."""
        role = director.get("role", "Ledamot")
        role_group = director.get("role_group", "Board")

        # Map role to normalized type
        role_normalized = self._normalize_role(role, role_group)

        edge = DirectsEdge(
            from_id=person_id,
            to_id=company_id,
            role=role_normalized,
            source="allabolag",
        )

        edge_data = asdict(edge)
        edge_data["_type"] = "DirectsEdge"
        edge_data["role_original"] = role
        edge_data["role_group"] = role_group

        # Check if this edge already exists
        existing_edges = list(self.graph.edges(person_id, data=True))
        for _, to_node, data in existing_edges:
            if to_node == company_id and data.get("role") == role_normalized:
                # Edge exists, maybe update source
                if "allabolag" not in data.get("sources", [data.get("source", "")]):
                    # Could update but for now just skip
                    pass
                return

        self.graph.add_edge(person_id, company_id, **edge_data)
        self.stats["edges_created"] += 1

    def _normalize_role(self, role: str, role_group: str) -> str:
        """Normalize Swedish roles to standard types."""
        role_lower = role.lower() if role else ""
        group_lower = role_group.lower() if role_group else ""

        if "vd" in role_lower or "verkställande" in role_lower:
            return "CEO"
        if "ordförande" in role_lower:
            return "BOARD_CHAIR"
        if "suppleant" in role_lower:
            return "BOARD_DEPUTY"
        if "revisor" in role_lower or group_lower == "revision":
            return "AUDITOR"
        if "ledamot" in role_lower or group_lower == "board":
            return "BOARD_MEMBER"
        if group_lower == "management":
            return "MANAGEMENT"

        return "BOARD_MEMBER"

    def _add_address(self, company: AllabolagCompany) -> Optional[str]:
        """Add an address node."""
        # Create normalized key
        parts = [
            company.street_address or "",
            company.postal_code or "",
            company.city or "",
        ]
        key = "-".join(p.lower().strip() for p in parts if p)

        if not key:
            return None

        if key in self.addresses_by_key:
            return self.addresses_by_key[key]

        address_id = f"address-{len(self.addresses_by_key)}"
        address = Address(
            id=address_id,
            raw_strings=[f"{company.street_address}, {company.postal_code} {company.city}"],
            normalized={
                "street": company.street_address,
                "postal_code": company.postal_code,
                "city": company.city,
                "municipality": company.municipality,
                "county": company.county,
            },
            sources=["allabolag"],
        )

        node_data = asdict(address)
        node_data["_type"] = "Address"

        self.graph.add_node(address_id, **node_data)
        self.addresses_by_key[key] = address_id
        self.stats["addresses_created"] += 1

        return address_id

    def _add_registered_at(self, company_id: str, address_id: str):
        """Add a RegisteredAt edge."""
        # Check if edge exists
        for _, to_node, data in self.graph.edges(company_id, data=True):
            if to_node == address_id and data.get("_type") == "RegisteredAtEdge":
                return

        edge = RegisteredAtEdge(
            from_id=company_id,
            to_id=address_id,
            source="allabolag",
        )

        edge_data = asdict(edge)
        edge_data["_type"] = "RegisteredAtEdge"

        self.graph.add_edge(company_id, address_id, **edge_data)

    def save_graph(self, path: Path = GRAPH_PICKLE):
        """Save the graph to pickle file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self.graph, f)
        logger.info(f"Graph saved to {path}")

    def print_stats(self):
        """Print loading statistics."""
        print("\n=== Allabolag Graph Loading Stats ===")
        for key, value in self.stats.items():
            print(f"  {key}: {value}")
        print(f"\nGraph totals:")
        print(f"  Nodes: {self.graph.number_of_nodes()}")
        print(f"  Edges: {self.graph.number_of_edges()}")

        # Count by type
        type_counts = defaultdict(int)
        for node_id in self.graph.nodes():
            node_type = self.graph.nodes[node_id].get("_type", "Unknown")
            type_counts[node_type] += 1

        print(f"\nNode types:")
        for node_type, count in sorted(type_counts.items()):
            print(f"  {node_type}: {count}")


def run_pattern_detection(graph: nx.MultiDiGraph) -> dict:
    """Run pattern detection on the graph."""
    from scripts.load_and_analyze import PatternDetector

    detector = PatternDetector(graph)

    results = {
        "serial_directors": detector.detect_serial_directors(threshold=3),
        "shared_directors": detector.detect_shared_directors(),
        "shell_networks": detector.detect_shell_networks(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Count alerts by severity
    alert_counts = {"high": 0, "medium": 0, "low": 0}
    for pattern_type, matches in results.items():
        if isinstance(matches, list):
            for match in matches:
                severity = match.get("severity", "medium")
                alert_counts[severity] += 1

    results["alert_counts"] = alert_counts

    return results


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Load allabolag data into graph")
    parser.add_argument("--db", type=Path, default=ALLABOLAG_DB,
                       help="Path to allabolag SQLite database")
    parser.add_argument("--graph", type=Path, default=GRAPH_PICKLE,
                       help="Path to graph pickle file")
    parser.add_argument("--merge", action="store_true", default=True,
                       help="Merge with existing graph (default: True)")
    parser.add_argument("--detect-patterns", action="store_true", default=True,
                       help="Run pattern detection after loading")
    parser.add_argument("--save-alerts", action="store_true", default=True,
                       help="Save alerts to JSON file")

    args = parser.parse_args()

    loader = AllabolagGraphLoader(args.db)

    # Load or create graph
    if args.merge:
        loader.load_existing_graph(args.graph)
    else:
        loader.graph = nx.MultiDiGraph()

    # Load companies from allabolag
    companies = loader.load_companies_from_db()

    if not companies:
        logger.warning("No companies found in allabolag database")
        return

    logger.info(f"Adding {len(companies)} companies to graph...")

    for company in companies:
        loader.add_company_to_graph(company)

    loader.print_stats()

    # Save graph
    loader.save_graph(args.graph)

    # Run pattern detection
    if args.detect_patterns:
        logger.info("Running pattern detection...")
        results = run_pattern_detection(loader.graph)

        print(f"\n=== Pattern Detection Results ===")
        print(f"Serial directors (3+ companies): {len(results.get('serial_directors', []))}")
        print(f"Shared directors: {len(results.get('shared_directors', []))}")
        print(f"Shell networks: {len(results.get('shell_networks', []))}")
        print(f"Alert counts: {results.get('alert_counts', {})}")

        if args.save_alerts:
            # Save intelligence results
            INTEL_RESULTS.parent.mkdir(parents=True, exist_ok=True)
            with open(INTEL_RESULTS, "w") as f:
                json.dump(results, f, indent=2, default=str)
            logger.info(f"Intelligence results saved to {INTEL_RESULTS}")

            # Generate alerts
            alerts = []
            for pattern_type, matches in results.items():
                if not isinstance(matches, list):
                    continue
                for match in matches:
                    alerts.append({
                        "id": f"alert-{len(alerts)}",
                        "type": match.get("pattern", pattern_type),
                        "severity": match.get("severity", "medium"),
                        "entities": match.get("company_ids", []) or [match.get("person_id")],
                        "details": match,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "status": "open",
                    })

            with open(ALERTS_JSON, "w") as f:
                json.dump(alerts, f, indent=2, default=str)
            logger.info(f"Alerts saved to {ALERTS_JSON} ({len(alerts)} alerts)")


if __name__ == "__main__":
    main()
