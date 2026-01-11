#!/usr/bin/env python3
"""
Cross-reference ICIJ Offshore Leaks data with our company graph.

This script:
1. Loads Swedish entities and officers from ICIJ
2. Extracts Swedish addresses and names
3. Matches against companies and persons in our graph
4. Generates ground truth labels for validation
"""

import csv
import json
import pickle
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

ICIJ_DIR = Path("data/icij")
GRAPH_PATH = Path("data/company_graph.pickle")
OUTPUT_PATH = Path("data/icij_ground_truth.json")


@dataclass
class ICIJEntity:
    """An entity from ICIJ offshore leaks."""
    node_id: str
    name: str
    address: str
    jurisdiction: str
    source: str  # Panama Papers, Paradise Papers, etc.
    country_codes: str
    status: str


@dataclass
class ICIJOfficer:
    """An officer (person) from ICIJ offshore leaks."""
    node_id: str
    name: str
    countries: str
    country_codes: str
    source: str


@dataclass
class GroundTruthMatch:
    """A match between ICIJ and our graph."""
    icij_id: str
    icij_name: str
    icij_type: str  # entity or officer
    icij_source: str
    graph_id: Optional[str]
    graph_name: Optional[str]
    match_type: str  # exact, fuzzy, address
    confidence: float


def load_sweden_entities() -> list[ICIJEntity]:
    """Load Swedish entities from ICIJ CSV."""
    entities = []
    csv_path = ICIJ_DIR / "sweden_entities.csv"

    if not csv_path.exists():
        print(f"Warning: {csv_path} not found")
        return entities

    with open(csv_path, "r", encoding="utf-8") as f:
        for line in f:
            # Parse CSV manually (header-less extract)
            parts = line.strip().split(",")
            if len(parts) >= 8:
                entities.append(ICIJEntity(
                    node_id=parts[0],
                    name=parts[1].strip('"'),
                    address=parts[7] if len(parts) > 7 else "",
                    jurisdiction=parts[4] if len(parts) > 4 else "",
                    source=parts[-4] if len(parts) > 4 else "Unknown",
                    country_codes=parts[-5] if len(parts) > 5 else "",
                    status=parts[-8] if len(parts) > 8 else "",
                ))

    return entities


def load_sweden_officers() -> list[ICIJOfficer]:
    """Load Swedish officers from ICIJ CSV."""
    officers = []
    csv_path = ICIJ_DIR / "sweden_officers.csv"

    if not csv_path.exists():
        print(f"Warning: {csv_path} not found")
        return officers

    with open(csv_path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) >= 5:
                officers.append(ICIJOfficer(
                    node_id=parts[0],
                    name=parts[1].strip('"'),
                    countries=parts[2] if len(parts) > 2 else "",
                    country_codes=parts[3] if len(parts) > 3 else "",
                    source=parts[4] if len(parts) > 4 else "Unknown",
                ))

    return officers


def normalize_name(name: str) -> str:
    """Normalize a name for matching."""
    if not name:
        return ""
    # Remove common suffixes
    name = re.sub(r"\b(AB|AKTIEBOLAG|HB|KB|INC|LTD|LIMITED|S\.?A\.?|CORP|LLC)\b", "", name, flags=re.IGNORECASE)
    # Remove punctuation
    name = re.sub(r"[^\w\s]", " ", name)
    # Normalize whitespace
    name = " ".join(name.split())
    return name.upper().strip()


def extract_orgnr_from_address(address: str) -> Optional[str]:
    """Try to extract Swedish org number from address."""
    # Swedish org numbers: 10 digits, often formatted as NNNNNN-NNNN
    patterns = [
        r"\b(\d{6}[-\s]?\d{4})\b",  # 556001-2345 or 5560012345
    ]
    for pattern in patterns:
        match = re.search(pattern, address)
        if match:
            orgnr = re.sub(r"[-\s]", "", match.group(1))
            # Validate it looks like a Swedish org number
            if orgnr.startswith(("55", "56", "57", "58", "59")):
                return orgnr
    return None


def match_against_graph(g, entities: list[ICIJEntity], officers: list[ICIJOfficer]) -> list[GroundTruthMatch]:
    """Match ICIJ data against our company graph."""
    matches = []

    # Build lookup indexes
    company_names = {}
    person_names = {}
    orgnr_to_id = {}

    for node_id, data in g.nodes(data=True):
        node_type = data.get("_type")

        if node_type == "Company":
            names = data.get("names", [])
            for name_entry in names:
                name = name_entry.get("name", "")
                if name:
                    normalized = normalize_name(name)
                    company_names[normalized] = node_id

            # Also index by org number
            orgnr = node_id.replace("company-", "")
            if orgnr:
                orgnr_to_id[orgnr] = node_id

        elif node_type == "Person":
            names = data.get("names", [])
            for name_entry in names:
                name = name_entry.get("name", "")
                if name:
                    normalized = normalize_name(name)
                    person_names[normalized] = node_id

    print(f"Built indexes: {len(company_names)} company names, {len(person_names)} person names, {len(orgnr_to_id)} org numbers")

    # Match entities
    for entity in entities:
        # Try org number from address
        orgnr = extract_orgnr_from_address(entity.address)
        if orgnr and orgnr in orgnr_to_id:
            node_id = orgnr_to_id[orgnr]
            data = dict(g.nodes[node_id])
            matches.append(GroundTruthMatch(
                icij_id=entity.node_id,
                icij_name=entity.name,
                icij_type="entity",
                icij_source=entity.source,
                graph_id=node_id,
                graph_name=data.get("names", [{}])[0].get("name", ""),
                match_type="orgnr",
                confidence=1.0,
            ))
            continue

        # Try name matching
        normalized = normalize_name(entity.name)
        if normalized in company_names:
            node_id = company_names[normalized]
            data = dict(g.nodes[node_id])
            matches.append(GroundTruthMatch(
                icij_id=entity.node_id,
                icij_name=entity.name,
                icij_type="entity",
                icij_source=entity.source,
                graph_id=node_id,
                graph_name=data.get("names", [{}])[0].get("name", ""),
                match_type="exact_name",
                confidence=0.9,
            ))

    # Match officers (persons)
    for officer in officers:
        normalized = normalize_name(officer.name)
        if normalized in person_names:
            node_id = person_names[normalized]
            data = dict(g.nodes[node_id])
            matches.append(GroundTruthMatch(
                icij_id=officer.node_id,
                icij_name=officer.name,
                icij_type="officer",
                icij_source=officer.source,
                graph_id=node_id,
                graph_name=data.get("names", [{}])[0].get("name", ""),
                match_type="exact_name",
                confidence=0.8,
            ))

    return matches


def main():
    print("=" * 60)
    print("ICIJ OFFSHORE LEAKS CROSS-REFERENCE")
    print("=" * 60)

    # Load ICIJ data
    print("\n[1] Loading ICIJ data...")
    entities = load_sweden_entities()
    officers = load_sweden_officers()
    print(f"   Loaded {len(entities)} Swedish entities")
    print(f"   Loaded {len(officers)} Swedish officers")

    # Load graph
    print("\n[2] Loading company graph...")
    if not GRAPH_PATH.exists():
        print(f"Error: Graph not found at {GRAPH_PATH}")
        return 1

    g = pickle.load(open(GRAPH_PATH, "rb"))
    companies = [n for n, d in g.nodes(data=True) if d.get("_type") == "Company"]
    persons = [n for n, d in g.nodes(data=True) if d.get("_type") == "Person"]
    print(f"   Graph: {len(companies)} companies, {len(persons)} persons")

    # Cross-reference
    print("\n[3] Cross-referencing...")
    matches = match_against_graph(g, entities, officers)
    print(f"   Found {len(matches)} matches")

    # Summary by type
    by_type = defaultdict(list)
    for m in matches:
        by_type[m.match_type].append(m)

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    for match_type, type_matches in by_type.items():
        print(f"\n{match_type}: {len(type_matches)} matches")
        for m in type_matches[:5]:
            print(f"  - {m.icij_name} -> {m.graph_name or 'N/A'} (conf: {m.confidence})")

    # Save results
    output = {
        "generated_at": datetime.utcnow().isoformat(),
        "icij_entities_count": len(entities),
        "icij_officers_count": len(officers),
        "graph_companies_count": len(companies),
        "graph_persons_count": len(persons),
        "matches_count": len(matches),
        "matches_by_type": {k: len(v) for k, v in by_type.items()},
        "matches": [asdict(m) for m in matches],
        "icij_entities_unmatched": [
            {"node_id": e.node_id, "name": e.name, "address": e.address, "source": e.source}
            for e in entities
            if not any(m.icij_id == e.node_id for m in matches)
        ][:50],
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved results to {OUTPUT_PATH}")

    # Mark matched companies in graph as offshore-linked
    for m in matches:
        if m.graph_id and m.graph_id in g.nodes:
            g.nodes[m.graph_id]["icij_linked"] = True
            g.nodes[m.graph_id]["icij_source"] = m.icij_source
            g.nodes[m.graph_id]["icij_id"] = m.icij_id

    pickle.dump(g, open(GRAPH_PATH, "wb"))
    print(f"Updated graph with ICIJ links")

    return 0


if __name__ == "__main__":
    sys.exit(main())
