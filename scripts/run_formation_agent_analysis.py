#!/usr/bin/env python3
"""
Run formation agent (auditor) analysis on the company graph.

Formation agents are entities that repeatedly appear across company formations.
In our data, this includes:
- Auditing companies (revisorer)
- Serial directors
- Shared addresses

This script analyzes these patterns and generates alerts.
"""

import json
import pickle
import sys
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

GRAPH_PATH = Path("data/company_graph.pickle")
OUTPUT_PATH = Path("data/formation_agent_analysis.json")
ALERTS_PATH = Path("data/alerts.json")


@dataclass
class FormationAgentScore:
    """Score for a formation agent (auditor, serial director, etc.)."""
    agent_id: str
    agent_name: str
    agent_type: str  # auditor, serial_director, address_cluster
    companies_count: int
    avg_shell_score: float
    high_shell_count: int  # companies with shell_score > 0.6
    suspicion_level: str  # low, medium, high
    alert: Optional[str] = None


def load_graph():
    """Load the company graph."""
    with open(GRAPH_PATH, "rb") as f:
        return pickle.load(f)


def analyze_auditors(g) -> list[FormationAgentScore]:
    """Analyze auditing companies as potential formation agents."""
    print("\n[1] Analyzing auditing companies...")

    # Find auditor relationships
    auditor_companies = defaultdict(list)

    for u, v, data in g.edges(data=True):
        if 'auditor' in u.lower():
            auditor_companies[u].append(v)

    scores = []
    for auditor_id, companies in auditor_companies.items():
        if len(companies) < 2:
            continue

        # Get auditor name
        auditor_data = dict(g.nodes.get(auditor_id, {}))
        name = auditor_data.get('name', auditor_id)

        # Calculate shell scores
        shell_scores = []
        for c in companies:
            if c in g.nodes:
                company_data = dict(g.nodes[c])
                shell_scores.append(company_data.get('shell_score', 0))

        avg_shell = sum(shell_scores) / len(shell_scores) if shell_scores else 0
        high_shell = len([s for s in shell_scores if s > 0.6])

        # Determine suspicion level
        if high_shell > 3 or (len(companies) > 10 and avg_shell > 0.4):
            suspicion_level = "high"
            alert = f"Auditor with {high_shell} high-risk companies"
        elif high_shell > 1 or avg_shell > 0.3:
            suspicion_level = "medium"
            alert = None
        else:
            suspicion_level = "low"
            alert = None

        scores.append(FormationAgentScore(
            agent_id=auditor_id,
            agent_name=name,
            agent_type="auditor",
            companies_count=len(companies),
            avg_shell_score=avg_shell,
            high_shell_count=high_shell,
            suspicion_level=suspicion_level,
            alert=alert
        ))

    print(f"   Found {len(scores)} auditors with 2+ companies")
    return scores


def analyze_serial_directors(g) -> list[FormationAgentScore]:
    """Analyze serial directors as potential formation agents."""
    print("\n[2] Analyzing serial directors...")

    from halo.intelligence.exclusion_lists import should_exclude_from_serial_director

    # Find director relationships
    director_companies = defaultdict(list)

    for u, v, data in g.edges(data=True):
        if data.get('_type') == 'DirectsEdge':
            director_companies[u].append(v)

    # Filter to serial directors (3+ companies)
    serial_directors = {k: v for k, v in director_companies.items() if len(v) >= 3}

    scores = []
    excluded_count = 0
    for director_id, companies in serial_directors.items():
        # Get director info
        director_data = dict(g.nodes.get(director_id, {}))
        names = director_data.get('names', [{}])
        name = names[0].get('name', director_id) if names else director_id

        # Skip excluded entities (audit firms, PE, law firms, banks, government)
        if should_exclude_from_serial_director(name):
            excluded_count += 1
            continue

        # Calculate shell scores of directed companies
        shell_scores = []
        for c in companies:
            if c in g.nodes:
                company_data = dict(g.nodes[c])
                shell_scores.append(company_data.get('shell_score', 0))

        avg_shell = sum(shell_scores) / len(shell_scores) if shell_scores else 0
        high_shell = len([s for s in shell_scores if s > 0.6])

        # Determine suspicion level
        if len(companies) >= 5 and (high_shell > 2 or avg_shell > 0.5):
            suspicion_level = "high"
            alert = f"Serial director with {len(companies)} companies, {high_shell} high-risk"
        elif len(companies) >= 4 or high_shell > 1:
            suspicion_level = "medium"
            alert = None
        else:
            suspicion_level = "low"
            alert = None

        scores.append(FormationAgentScore(
            agent_id=director_id,
            agent_name=name,
            agent_type="serial_director",
            companies_count=len(companies),
            avg_shell_score=avg_shell,
            high_shell_count=high_shell,
            suspicion_level=suspicion_level,
            alert=alert
        ))

    print(f"   Found {len(scores)} serial directors (3+ companies)")
    print(f"   Excluded {excluded_count} (audit firms, PE, law firms, banks, government)")
    return scores


def analyze_address_clusters(g) -> list[FormationAgentScore]:
    """Analyze addresses with multiple companies (registration mills)."""
    print("\n[3] Analyzing address clusters...")

    # Find address relationships
    address_companies = defaultdict(list)

    for u, v, data in g.edges(data=True):
        if data.get('_type') == 'RegisteredAtEdge':
            address_companies[v].append(u)

    # Filter to addresses with multiple companies
    multi_company_addresses = {k: v for k, v in address_companies.items() if len(v) >= 2}

    scores = []
    for addr_id, companies in multi_company_addresses.items():
        # Get address info
        addr_data = dict(g.nodes.get(addr_id, {}))
        normalized = addr_data.get('normalized', {})
        name = f"{normalized.get('street', '')} {normalized.get('postal_code', '')} {normalized.get('city', '')}".strip()
        if not name:
            name = addr_id

        # Calculate shell scores
        shell_scores = []
        for c in companies:
            if c in g.nodes:
                company_data = dict(g.nodes[c])
                shell_scores.append(company_data.get('shell_score', 0))

        avg_shell = sum(shell_scores) / len(shell_scores) if shell_scores else 0
        high_shell = len([s for s in shell_scores if s > 0.6])

        # Determine suspicion level
        if len(companies) >= 5 or (len(companies) >= 3 and avg_shell > 0.5):
            suspicion_level = "high"
            alert = f"Address cluster with {len(companies)} companies"
        elif len(companies) >= 3 or high_shell > 0:
            suspicion_level = "medium"
            alert = None
        else:
            suspicion_level = "low"
            alert = None

        scores.append(FormationAgentScore(
            agent_id=addr_id,
            agent_name=name,
            agent_type="address_cluster",
            companies_count=len(companies),
            avg_shell_score=avg_shell,
            high_shell_count=high_shell,
            suspicion_level=suspicion_level,
            alert=alert
        ))

    print(f"   Found {len(scores)} addresses with 2+ companies")
    return scores


def generate_alerts(all_scores: list[FormationAgentScore]) -> list[dict]:
    """Generate alerts from formation agent analysis."""
    alerts = []

    for score in all_scores:
        if score.alert:
            alerts.append({
                "id": f"formation-{score.agent_id}",
                "alert_type": f"formation_agent_{score.agent_type}",
                "severity": score.suspicion_level,
                "entity_id": score.agent_id,
                "entity_type": score.agent_type,
                "description": score.alert,
                "evidence": {
                    "agent_name": score.agent_name,
                    "companies_count": score.companies_count,
                    "avg_shell_score": score.avg_shell_score,
                    "high_shell_count": score.high_shell_count,
                },
                "created_at": datetime.utcnow().isoformat(),
            })

    return alerts


def main():
    print("=" * 60)
    print("FORMATION AGENT ANALYSIS")
    print("=" * 60)

    if not GRAPH_PATH.exists():
        print(f"Error: Graph not found at {GRAPH_PATH}")
        return 1

    g = load_graph()
    print(f"Loaded graph: {g.number_of_nodes()} nodes, {g.number_of_edges()} edges")

    # Run analyses
    auditor_scores = analyze_auditors(g)
    director_scores = analyze_serial_directors(g)
    address_scores = analyze_address_clusters(g)

    all_scores = auditor_scores + director_scores + address_scores

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    by_type = defaultdict(lambda: {"total": 0, "high": 0, "medium": 0})
    for score in all_scores:
        by_type[score.agent_type]["total"] += 1
        if score.suspicion_level == "high":
            by_type[score.agent_type]["high"] += 1
        elif score.suspicion_level == "medium":
            by_type[score.agent_type]["medium"] += 1

    for agent_type, counts in by_type.items():
        print(f"\n{agent_type}:")
        print(f"  Total: {counts['total']}")
        print(f"  High suspicion: {counts['high']}")
        print(f"  Medium suspicion: {counts['medium']}")

    # Generate and merge alerts
    new_alerts = generate_alerts(all_scores)
    print(f"\nGenerated {len(new_alerts)} new alerts")

    # Load existing alerts and merge
    existing_alerts = []
    if ALERTS_PATH.exists():
        with open(ALERTS_PATH) as f:
            existing_alerts = json.load(f)
        # Remove old formation agent alerts
        existing_alerts = [a for a in existing_alerts if not a.get("alert_type", "").startswith("formation_agent")]

    all_alerts = existing_alerts + new_alerts

    # Save alerts
    with open(ALERTS_PATH, "w") as f:
        json.dump(all_alerts, f, indent=2, default=str)
    print(f"Saved {len(all_alerts)} total alerts to {ALERTS_PATH}")

    # Save detailed analysis
    output = {
        "analysis_date": datetime.utcnow().isoformat(),
        "scores": [asdict(s) for s in all_scores],
        "summary": dict(by_type),
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Saved detailed analysis to {OUTPUT_PATH}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
