#!/usr/bin/env python3
"""
Load extracted Bolagsverket data into NetworkX graph and run intelligence analysis.

This is the Week 2 demo script from demo_goal.md:
1. Load 1000+ companies with directors into graph
2. Run anomaly detection
3. Run pattern matching
4. Generate alerts
"""

import json
import pickle
import logging
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

import networkx as nx

from halo.graph.schema import Company, Person, Address
from halo.graph.edges import DirectsEdge, RegisteredAtEdge

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class GraphBuilder:
    """Build NetworkX graph from extracted Bolagsverket data."""

    def __init__(self):
        self.graph = nx.MultiDiGraph()
        self.persons_by_name = {}  # name -> person_id for dedup
        self.addresses_by_key = {}  # normalized key -> address_id

    def load_extraction_results(self, results_path: Path) -> int:
        """Load extraction results and build graph."""
        with open(results_path) as f:
            results = json.load(f)

        logger.info(f"Loading {len(results)} companies...")

        for record in results:
            self._add_company(record)

        logger.info(f"Graph built: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges")
        return len(results)

    def _add_company(self, record: dict):
        """Add a company and its directors to the graph."""
        orgnr = record.get("orgnr", "")
        company_name = record.get("company_name", "Unknown")

        # Create company node
        company_id = f"company-{orgnr}"
        company = Company(
            id=company_id,
            orgnr=orgnr,
            names=[{"name": company_name, "type": "primary"}],
            sources=["bolagsverket_hvd"],
        )

        self.graph.add_node(company_id, **asdict(company), _type="Company")

        # Add directors
        for director in record.get("directors", []):
            person_id = self._add_person(director)
            if person_id:
                self._add_directorship(person_id, company_id, director)

        # Add auditors as persons too
        for auditor in record.get("auditors", []):
            if auditor.get("name"):
                auditor_as_director = {
                    "full_name": auditor.get("name"),
                    "role": "revisor",
                    "role_normalized": "AUDITOR",
                }
                person_id = self._add_person(auditor_as_director)
                if person_id:
                    self._add_directorship(person_id, company_id, auditor_as_director)

    def _add_person(self, director: dict) -> Optional[str]:
        """Add a person node, deduplicating by name."""
        full_name = director.get("full_name", "").strip()
        if not full_name:
            return None

        # Simple dedup by exact name match
        name_key = full_name.lower()
        if name_key in self.persons_by_name:
            return self.persons_by_name[name_key]

        person_id = f"person-{len(self.persons_by_name)}"
        person = Person(
            id=person_id,
            names=[{"name": full_name}],
            sources=["bolagsverket_hvd"],
        )

        self.graph.add_node(person_id, **asdict(person), _type="Person")
        self.persons_by_name[name_key] = person_id

        return person_id

    def _add_directorship(self, person_id: str, company_id: str, director: dict):
        """Add a directorship edge."""
        role = director.get("role_normalized", director.get("role", "BOARD_MEMBER"))

        edge = DirectsEdge(
            from_id=person_id,
            to_id=company_id,
            role=role,
            source="bolagsverket_hvd",
        )

        self.graph.add_edge(
            person_id,
            company_id,
            **asdict(edge),
            _type="DirectsEdge"
        )

    def save_graph(self, path: Path):
        """Save graph to pickle file."""
        with open(path, "wb") as f:
            pickle.dump(self.graph, f)
        logger.info(f"Graph saved to {path}")


class PatternDetector:
    """Detect shell company patterns in the graph."""

    def __init__(self, graph: nx.MultiDiGraph, extraction_data: list[dict] = None):
        self.graph = graph
        self.extraction_data = extraction_data or []
        # Build lookup for extraction data by orgnr
        self.company_data = {r.get("orgnr"): r for r in self.extraction_data}

    def detect_serial_directors(self, threshold: int = 3) -> list[dict]:
        """Find persons directing many companies."""
        matches = []

        for node_id in self.graph.nodes():
            if not node_id.startswith("person-"):
                continue

            # Count outgoing DirectsEdge
            companies = []
            for _, to_id, data in self.graph.out_edges(node_id, data=True):
                if data.get("_type") == "DirectsEdge":
                    companies.append(to_id)

            if len(companies) >= threshold:
                node_data = self.graph.nodes[node_id]
                names = node_data.get("names", [])
                name = names[0].get("name", "Unknown") if names else "Unknown"

                matches.append({
                    "pattern": "serial_director",
                    "person_id": node_id,
                    "person_name": name,
                    "company_count": len(companies),
                    "company_ids": companies[:10],
                    "severity": "high" if len(companies) >= 5 else "medium",
                })

        return sorted(matches, key=lambda x: x["company_count"], reverse=True)

    def detect_shared_directors(self) -> list[dict]:
        """Find companies sharing multiple directors."""
        # Build company -> directors mapping
        company_directors = defaultdict(set)

        for u, v, data in self.graph.edges(data=True):
            if data.get("_type") == "DirectsEdge":
                if u.startswith("person-") and v.startswith("company-"):
                    company_directors[v].add(u)

        # Find pairs with 2+ shared directors
        matches = []
        companies = list(company_directors.keys())

        for i, c1 in enumerate(companies):
            for c2 in companies[i+1:]:
                shared = company_directors[c1] & company_directors[c2]
                if len(shared) >= 2:
                    c1_data = self.graph.nodes[c1]
                    c2_data = self.graph.nodes[c2]

                    matches.append({
                        "pattern": "shared_directors",
                        "company1_id": c1,
                        "company1_name": c1_data.get("names", [{}])[0].get("name", "Unknown"),
                        "company2_id": c2,
                        "company2_name": c2_data.get("names", [{}])[0].get("name", "Unknown"),
                        "shared_director_count": len(shared),
                        "shared_director_ids": list(shared),
                        "severity": "high" if len(shared) >= 3 else "medium",
                    })

        return sorted(matches, key=lambda x: x["shared_director_count"], reverse=True)

    def detect_shell_networks(self) -> list[dict]:
        """Find networks of connected companies through directors."""
        # Build company -> directors and director -> companies mappings
        company_directors = defaultdict(set)
        director_companies = defaultdict(set)

        for u, v, data in self.graph.edges(data=True):
            if data.get("_type") == "DirectsEdge":
                if u.startswith("person-") and v.startswith("company-"):
                    company_directors[v].add(u)
                    director_companies[u].add(v)

        # Find connected components
        visited_companies = set()
        networks = []

        for start_company in company_directors:
            if start_company in visited_companies:
                continue

            # BFS to find connected companies
            network = set()
            queue = [start_company]

            while queue:
                company = queue.pop(0)
                if company in network:
                    continue
                network.add(company)
                visited_companies.add(company)

                # Find connected companies through shared directors
                for director in company_directors[company]:
                    for connected_company in director_companies[director]:
                        if connected_company not in network:
                            queue.append(connected_company)

            if len(network) >= 3:
                networks.append({
                    "pattern": "shell_network",
                    "company_count": len(network),
                    "company_ids": list(network)[:20],
                    "severity": "high" if len(network) >= 5 else "medium",
                })

        return sorted(networks, key=lambda x: x["company_count"], reverse=True)

    def detect_recent_companies_many_directors(self, min_directors: int = 4, years_threshold: int = 2) -> list[dict]:
        """Find recently registered companies with unusually many directors.

        This is a red flag - new companies typically start with 1-2 directors.
        Having 4+ directors immediately can indicate nominee arrangements.
        """
        from datetime import datetime, timedelta

        matches = []
        cutoff_date = datetime.now() - timedelta(days=years_threshold * 365)

        for node_id in self.graph.nodes():
            if not node_id.startswith("company-"):
                continue

            # Get company data from extraction
            orgnr = node_id.replace("company-", "")
            company_info = self.company_data.get(orgnr, {})
            signature_date = company_info.get("signature_date")

            if not signature_date:
                continue

            try:
                sig_date = datetime.strptime(signature_date, "%Y-%m-%d")
            except (ValueError, TypeError):
                continue

            # Check if recent
            if sig_date < cutoff_date:
                continue

            # Count directors
            director_count = 0
            for _, _, data in self.graph.in_edges(node_id, data=True):
                if data.get("_type") == "DirectsEdge":
                    director_count += 1

            if director_count >= min_directors:
                node_data = self.graph.nodes[node_id]
                names = node_data.get("names", [])
                name = names[0].get("name", "Unknown") if names else "Unknown"

                matches.append({
                    "pattern": "new_company_many_directors",
                    "company_id": node_id,
                    "company_name": name,
                    "orgnr": orgnr,
                    "director_count": director_count,
                    "signature_date": signature_date,
                    "severity": "high" if director_count >= 6 else "medium",
                })

        return sorted(matches, key=lambda x: x["director_count"], reverse=True)

    def detect_same_role_concentration(self) -> list[dict]:
        """Find persons holding the same role (e.g., CEO) across multiple companies.

        A person being CEO of 3+ companies is suspicious - how can one person
        actively manage multiple companies?
        """
        from collections import defaultdict

        # Track person -> role -> companies
        person_role_companies = defaultdict(lambda: defaultdict(list))

        for u, v, data in self.graph.edges(data=True):
            if data.get("_type") == "DirectsEdge":
                if u.startswith("person-") and v.startswith("company-"):
                    role = data.get("role", "UNKNOWN")
                    person_role_companies[u][role].append(v)

        matches = []
        high_value_roles = {"VD", "STYRELSEORDFORANDE", "CEO", "CHAIRMAN"}

        for person_id, roles in person_role_companies.items():
            for role, companies in roles.items():
                # Only flag if same high-value role in 2+ companies, or any role in 4+
                threshold = 2 if role in high_value_roles else 4

                if len(companies) >= threshold:
                    person_data = self.graph.nodes[person_id]
                    names = person_data.get("names", [])
                    name = names[0].get("name", "Unknown") if names else "Unknown"

                    matches.append({
                        "pattern": "role_concentration",
                        "person_id": person_id,
                        "person_name": name,
                        "role": role,
                        "company_count": len(companies),
                        "company_ids": companies[:10],
                        "severity": "high" if role in high_value_roles else "medium",
                    })

        return sorted(matches, key=lambda x: x["company_count"], reverse=True)

    def detect_circular_directorships(self) -> list[dict]:
        """Find circular patterns where directors of company A also direct company B,
        whose directors also direct company C, which links back to A.

        This can indicate complex nominee or control structures.
        """
        # Build director -> companies and company -> directors
        director_companies = defaultdict(set)
        company_directors = defaultdict(set)

        for u, v, data in self.graph.edges(data=True):
            if data.get("_type") == "DirectsEdge":
                if u.startswith("person-") and v.startswith("company-"):
                    director_companies[u].add(v)
                    company_directors[v].add(u)

        matches = []
        seen_cycles = set()

        # Look for triangles: A-B-C-A through shared directors
        companies = list(company_directors.keys())

        for company_a in companies:
            # Find companies that share directors with A
            linked_to_a = set()
            for director in company_directors[company_a]:
                for other in director_companies[director]:
                    if other != company_a:
                        linked_to_a.add(other)

            for company_b in linked_to_a:
                # Find companies that share directors with B
                linked_to_b = set()
                for director in company_directors[company_b]:
                    for other in director_companies[director]:
                        if other not in (company_a, company_b):
                            linked_to_b.add(other)

                # Check if any company linked to B is also linked to A (completing the triangle)
                for company_c in linked_to_b:
                    if company_c in linked_to_a:
                        # Found a triangle
                        cycle_key = tuple(sorted([company_a, company_b, company_c]))
                        if cycle_key not in seen_cycles:
                            seen_cycles.add(cycle_key)

                            # Get company names
                            names = []
                            for cid in [company_a, company_b, company_c]:
                                node_data = self.graph.nodes[cid]
                                n = node_data.get("names", [{}])[0].get("name", "Unknown")
                                names.append(n)

                            matches.append({
                                "pattern": "circular_directors",
                                "company_ids": list(cycle_key),
                                "company_names": names,
                                "severity": "high",
                            })

        return matches[:50]  # Limit to top 50

    def detect_dormant_reactivation(self) -> list[dict]:
        """Find companies with old signature dates that suddenly have recent activity.

        Gap in filings followed by reactivation can indicate shell company being
        brought back to life for fraudulent purposes.
        """
        from datetime import datetime

        matches = []

        # Sort companies by signature date to find gaps
        dated_companies = []
        for orgnr, data in self.company_data.items():
            sig_date = data.get("signature_date")
            if sig_date:
                try:
                    date_obj = datetime.strptime(sig_date, "%Y-%m-%d")
                    dated_companies.append((orgnr, date_obj, data))
                except (ValueError, TypeError):
                    pass

        # Find companies with very recent filings (last 6 months) after long dormancy
        now = datetime.now()
        recent_threshold = now.replace(year=now.year - 1)  # Last year
        old_threshold = now.replace(year=now.year - 5)  # More than 5 years old company

        for orgnr, sig_date, data in dated_companies:
            # Check if the signature is recent
            if sig_date >= recent_threshold:
                # Check if the orgnr suggests an old company (starts with 55 or 56 = older companies)
                # Swedish orgnr format: first digit indicates type, next digits are sequential
                # Older companies have lower sequential numbers
                try:
                    seq_num = int(orgnr[2:6])  # Get middle digits
                    if seq_num < 3000:  # Heuristic for older companies
                        company_id = f"company-{orgnr}"
                        if company_id in self.graph.nodes:
                            node_data = self.graph.nodes[company_id]
                            names = node_data.get("names", [])
                            name = names[0].get("name", "Unknown") if names else "Unknown"

                            matches.append({
                                "pattern": "dormant_reactivation",
                                "company_id": company_id,
                                "company_name": name,
                                "orgnr": orgnr,
                                "signature_date": sig_date.strftime("%Y-%m-%d"),
                                "severity": "medium",
                            })
                except (ValueError, IndexError):
                    pass

        return matches[:30]


class AlertGenerator:
    """Generate alerts from pattern matches."""

    def __init__(self):
        self.alerts = []

    def add_from_patterns(self, pattern_matches: list[dict]):
        """Create alerts from pattern matches."""
        for match in pattern_matches:
            alert = {
                "id": f"alert-{len(self.alerts)}",
                "alert_type": f"pattern_{match['pattern']}",
                "severity": match.get("severity", "medium"),
                "description": self._describe_match(match),
                "evidence": match,
                "created_at": datetime.utcnow().isoformat(),
            }

            # Set entity_id based on pattern type
            if match["pattern"] == "serial_director":
                alert["entity_id"] = match["person_id"]
                alert["entity_type"] = "Person"
            elif match["pattern"] == "shared_directors":
                alert["entity_id"] = match["company1_id"]
                alert["entity_type"] = "Company"
            elif match["pattern"] == "shell_network":
                alert["entity_id"] = match["company_ids"][0] if match["company_ids"] else None
                alert["entity_type"] = "Company"
            elif match["pattern"] == "new_company_many_directors":
                alert["entity_id"] = match["company_id"]
                alert["entity_type"] = "Company"
            elif match["pattern"] == "role_concentration":
                alert["entity_id"] = match["person_id"]
                alert["entity_type"] = "Person"
            elif match["pattern"] == "circular_directors":
                alert["entity_id"] = match["company_ids"][0] if match["company_ids"] else None
                alert["entity_type"] = "Company"
            elif match["pattern"] == "dormant_reactivation":
                alert["entity_id"] = match["company_id"]
                alert["entity_type"] = "Company"

            self.alerts.append(alert)

    def _describe_match(self, match: dict) -> str:
        """Generate human-readable description."""
        pattern = match["pattern"]

        if pattern == "serial_director":
            return f"{match['person_name']} directs {match['company_count']} companies"
        elif pattern == "shared_directors":
            return f"{match['company1_name']} and {match['company2_name']} share {match['shared_director_count']} directors"
        elif pattern == "shell_network":
            return f"Network of {match['company_count']} connected companies"
        elif pattern == "new_company_many_directors":
            return f"New company {match['company_name']} has {match['director_count']} directors (registered {match['signature_date']})"
        elif pattern == "role_concentration":
            return f"{match['person_name']} is {match['role']} at {match['company_count']} companies"
        elif pattern == "circular_directors":
            names = match.get('company_names', [])
            if len(names) >= 3:
                return f"Circular director relationship between {names[0]}, {names[1]}, and {names[2]}"
            return "Circular director relationship detected"
        elif pattern == "dormant_reactivation":
            return f"Potentially dormant company {match['company_name']} recently reactivated"
        else:
            return f"Pattern: {pattern}"

    def save_alerts(self, path: Path):
        """Save alerts to JSON."""
        with open(path, "w") as f:
            json.dump(self.alerts, f, indent=2, default=str)
        logger.info(f"Saved {len(self.alerts)} alerts to {path}")


def main():
    print("=" * 70)
    print("HALO Intelligence Pipeline - Week 2 Demo")
    print("=" * 70)

    # Paths
    data_dir = Path("data")
    extraction_path = data_dir / "extraction_combined" / "results.json"
    graph_path = data_dir / "company_graph.pickle"
    alerts_path = data_dir / "alerts.json"
    results_path = data_dir / "intelligence_results.json"

    if not extraction_path.exists():
        print(f"Error: Extraction results not found at {extraction_path}")
        return

    # Step 1: Build graph
    print("\n[1/4] Building graph from extraction results...")
    builder = GraphBuilder()
    company_count = builder.load_extraction_results(extraction_path)
    builder.save_graph(graph_path)

    # Count node types
    company_nodes = sum(1 for n in builder.graph.nodes() if n.startswith("company-"))
    person_nodes = sum(1 for n in builder.graph.nodes() if n.startswith("person-"))

    print(f"  - Companies: {company_nodes}")
    print(f"  - Persons: {person_nodes}")
    print(f"  - Edges: {builder.graph.number_of_edges()}")

    # Load extraction data for pattern detection
    with open(extraction_path) as f:
        extraction_data = json.load(f)

    # Step 2: Pattern detection
    print("\n[2/4] Running pattern detection...")
    detector = PatternDetector(builder.graph, extraction_data)

    serial_directors = detector.detect_serial_directors(threshold=3)
    print(f"  - Serial directors (3+ companies): {len(serial_directors)}")

    shared_directors = detector.detect_shared_directors()
    print(f"  - Company pairs with shared directors: {len(shared_directors)}")

    shell_networks = detector.detect_shell_networks()
    print(f"  - Shell networks (3+ companies): {len(shell_networks)}")

    # New pattern detections
    new_companies_many_directors = detector.detect_recent_companies_many_directors()
    print(f"  - New companies with many directors: {len(new_companies_many_directors)}")

    role_concentrations = detector.detect_same_role_concentration()
    print(f"  - Role concentration patterns: {len(role_concentrations)}")

    circular_directors = detector.detect_circular_directorships()
    print(f"  - Circular director relationships: {len(circular_directors)}")

    dormant_reactivations = detector.detect_dormant_reactivation()
    print(f"  - Dormant company reactivations: {len(dormant_reactivations)}")

    # Step 3: Generate alerts
    print("\n[3/4] Generating alerts...")
    alert_gen = AlertGenerator()
    alert_gen.add_from_patterns(serial_directors[:50])  # Top 50
    alert_gen.add_from_patterns(shared_directors[:50])
    alert_gen.add_from_patterns(shell_networks[:20])
    alert_gen.add_from_patterns(new_companies_many_directors[:20])
    alert_gen.add_from_patterns(role_concentrations[:30])
    alert_gen.add_from_patterns(circular_directors[:20])
    alert_gen.add_from_patterns(dormant_reactivations[:20])
    alert_gen.save_alerts(alerts_path)

    # Step 4: Summary report
    print("\n[4/4] Generating summary...")

    high_severity = [a for a in alert_gen.alerts if a["severity"] == "high"]
    medium_severity = [a for a in alert_gen.alerts if a["severity"] == "medium"]

    summary = {
        "analysis_timestamp": datetime.utcnow().isoformat(),
        "input": {
            "companies_extracted": company_count,
            "companies_in_graph": company_nodes,
            "persons_in_graph": person_nodes,
            "edges": builder.graph.number_of_edges(),
        },
        "patterns": {
            "serial_directors": len(serial_directors),
            "shared_directors": len(shared_directors),
            "shell_networks": len(shell_networks),
            "new_companies_many_directors": len(new_companies_many_directors),
            "role_concentrations": len(role_concentrations),
            "circular_directors": len(circular_directors),
            "dormant_reactivations": len(dormant_reactivations),
        },
        "alerts": {
            "total": len(alert_gen.alerts),
            "high_severity": len(high_severity),
            "medium_severity": len(medium_severity),
        },
        "top_serial_directors": serial_directors[:10],
        "top_shell_networks": shell_networks[:5],
        "top_role_concentrations": role_concentrations[:5],
        "top_circular_directors": circular_directors[:5],
        "top_new_companies_many_directors": new_companies_many_directors[:5],
    }

    with open(results_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)

    # Print summary
    print("\n" + "=" * 70)
    print("ANALYSIS COMPLETE")
    print("=" * 70)

    print(f"\nInput Data:")
    print(f"  Companies: {company_nodes}")
    print(f"  Directors/Persons: {person_nodes}")

    print(f"\nPatterns Detected:")
    print(f"  Serial directors: {len(serial_directors)}")
    print(f"  Shared director pairs: {len(shared_directors)}")
    print(f"  Shell networks: {len(shell_networks)}")
    print(f"  New companies with many directors: {len(new_companies_many_directors)}")
    print(f"  Role concentrations: {len(role_concentrations)}")
    print(f"  Circular director relationships: {len(circular_directors)}")
    print(f"  Dormant company reactivations: {len(dormant_reactivations)}")

    print(f"\nAlerts Generated:")
    print(f"  Total: {len(alert_gen.alerts)}")
    print(f"  High severity: {len(high_severity)}")
    print(f"  Medium severity: {len(medium_severity)}")

    print(f"\nTop Serial Directors:")
    for i, sd in enumerate(serial_directors[:5], 1):
        print(f"  {i}. {sd['person_name']}: {sd['company_count']} companies")

    print(f"\nTop Shell Networks:")
    for i, sn in enumerate(shell_networks[:3], 1):
        print(f"  {i}. Network of {sn['company_count']} companies")

    print(f"\nOutput Files:")
    print(f"  Graph: {graph_path}")
    print(f"  Alerts: {alerts_path}")
    print(f"  Results: {results_path}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
