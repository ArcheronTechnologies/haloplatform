#!/usr/bin/env python3
"""
Run temporal sequence detection on the company graph.

Detects fraud playbooks by analyzing the sequence of events in company lifecycles.
Works with NetworkX graph data.
"""

import json
import pickle
import sys
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

GRAPH_PATH = Path("data/company_graph.pickle")
OUTPUT_PATH = Path("data/sequence_detection.json")
ALERTS_PATH = Path("data/alerts.json")


@dataclass
class Event:
    """A company lifecycle event."""
    event_type: str
    timestamp: datetime
    entity_id: str
    details: dict = field(default_factory=dict)


@dataclass
class PlaybookMatch:
    """Result of playbook detection."""
    playbook_id: str
    playbook_name: str
    severity: str
    confidence: float
    current_stage: int
    total_stages: int
    matched_events: list
    entity_id: str
    company_name: str
    alert: str


# Simplified playbooks that work with available data
PLAYBOOKS = {
    "shell_company_indicators": {
        "name": "Shell Company Indicators",
        "description": "Multiple shell company indicators present",
        "severity": "high",
        "indicators": [
            "single_director",
            "generic_sni",
            "young_company",
            "no_employees",
        ],
        "min_indicators": 3,
    },
    "rapid_formation": {
        "name": "Rapid Formation Pattern",
        "description": "Company formed and registered for taxes quickly",
        "severity": "medium",
        "sequence": ["formed", "f_skatt_registered"],
        "max_days": 30,
    },
    "dormant_then_active": {
        "name": "Dormant Company Activation",
        "description": "Old company with recent director changes",
        "severity": "medium",
        "conditions": {
            "min_age_years": 5,
            "recent_director_change": True,
        },
    },
}


def load_graph():
    """Load the company graph."""
    with open(GRAPH_PATH, "rb") as f:
        return pickle.load(f)


def extract_events(g, company_id: str) -> list[Event]:
    """Extract timeline events from a company node."""
    if company_id not in g.nodes:
        return []

    data = dict(g.nodes[company_id])
    events = []

    # Formation event
    formation = data.get("formation", {})
    formation_date = formation.get("date") or data.get("registration_date")
    if formation_date:
        try:
            if isinstance(formation_date, str):
                formation_date = date.fromisoformat(formation_date)
            events.append(Event(
                event_type="formed",
                timestamp=datetime.combine(formation_date, datetime.min.time()),
                entity_id=company_id,
                details={"date": str(formation_date)}
            ))
        except (ValueError, TypeError):
            pass

    # F-skatt registration
    f_skatt = data.get("f_skatt") or {}
    if f_skatt.get("registered"):
        f_skatt_from = f_skatt.get("from")
        if f_skatt_from:
            try:
                if isinstance(f_skatt_from, str):
                    f_skatt_from = date.fromisoformat(f_skatt_from)
                events.append(Event(
                    event_type="f_skatt_registered",
                    timestamp=datetime.combine(f_skatt_from, datetime.min.time()),
                    entity_id=company_id,
                    details=f_skatt
                ))
            except (ValueError, TypeError):
                pass

    # Moms/VAT registration
    moms = data.get("moms") or {}
    if moms.get("registered"):
        moms_from = moms.get("from")
        if moms_from:
            try:
                if isinstance(moms_from, str):
                    moms_from = date.fromisoformat(moms_from)
                events.append(Event(
                    event_type="vat_registered",
                    timestamp=datetime.combine(moms_from, datetime.min.time()),
                    entity_id=company_id,
                    details=moms
                ))
            except (ValueError, TypeError):
                pass

    # Employer registration
    employer = data.get("employer") or {}
    if employer.get("registered"):
        employer_from = employer.get("from")
        if employer_from:
            try:
                if isinstance(employer_from, str):
                    employer_from = date.fromisoformat(employer_from)
                events.append(Event(
                    event_type="employer_registered",
                    timestamp=datetime.combine(employer_from, datetime.min.time()),
                    entity_id=company_id,
                    details=employer
                ))
            except (ValueError, TypeError):
                pass

    return sorted(events, key=lambda e: e.timestamp)


def get_company_indicators(g, company_id: str) -> dict:
    """Get shell company indicators for a company."""
    if company_id not in g.nodes:
        return {}

    data = dict(g.nodes[company_id])
    indicators = {}

    # Single director
    director_count = 0
    for u, v, edge_data in g.edges(data=True):
        if v == company_id and edge_data.get("_type") == "DirectsEdge":
            director_count += 1
    indicators["single_director"] = director_count == 1
    indicators["director_count"] = director_count

    # Generic SNI (management consulting, financial services, real estate)
    sni_codes = data.get("sni_codes", [])
    generic_snis = {"64", "66", "68", "70", "82"}
    sni_2digit = ""
    if sni_codes:
        sni_2digit = str(sni_codes[0].get("kod", sni_codes[0].get("code", "")))[:2]
    indicators["generic_sni"] = sni_2digit in generic_snis
    indicators["sni_code"] = sni_2digit

    # Young company (< 2 years)
    formation_date = data.get("formation", {}).get("date") or data.get("registration_date")
    if formation_date:
        try:
            if isinstance(formation_date, str):
                formation_date = date.fromisoformat(formation_date)
            age_days = (date.today() - formation_date).days
            indicators["young_company"] = age_days < 730  # 2 years
            indicators["age_days"] = age_days
        except (ValueError, TypeError):
            indicators["young_company"] = False
            indicators["age_days"] = None
    else:
        indicators["young_company"] = False
        indicators["age_days"] = None

    # No employees
    employees = data.get("employees", {})
    emp_count = employees.get("count", 0) if isinstance(employees, dict) else 0
    indicators["no_employees"] = emp_count == 0
    indicators["employee_count"] = emp_count

    # No revenue (if available)
    revenue = data.get("revenue")
    indicators["no_revenue"] = revenue is None or revenue == 0
    indicators["revenue"] = revenue

    return indicators


def detect_shell_company_pattern(g, company_id: str) -> Optional[PlaybookMatch]:
    """Detect shell company indicators pattern."""
    indicators = get_company_indicators(g, company_id)

    if not indicators:
        return None

    # Count matching indicators
    matched = []
    for indicator in ["single_director", "generic_sni", "young_company", "no_employees"]:
        if indicators.get(indicator):
            matched.append(indicator)

    if len(matched) >= 3:
        data = dict(g.nodes[company_id])
        names = data.get("names", [{}])
        company_name = names[0].get("name", company_id) if names else company_id

        return PlaybookMatch(
            playbook_id="shell_company_indicators",
            playbook_name="Shell Company Indicators",
            severity="high" if len(matched) >= 4 else "medium",
            confidence=len(matched) / 4,
            current_stage=len(matched),
            total_stages=4,
            matched_events=[{"indicator": m, "value": indicators.get(m)} for m in matched],
            entity_id=company_id,
            company_name=company_name,
            alert=f"Company has {len(matched)} shell company indicators: {', '.join(matched)}"
        )

    return None


def detect_rapid_formation(g, company_id: str) -> Optional[PlaybookMatch]:
    """Detect rapid formation pattern (formed and registered quickly)."""
    events = extract_events(g, company_id)

    if len(events) < 2:
        return None

    # Find formation and f-skatt events
    formed_event = None
    fskatt_event = None

    for event in events:
        if event.event_type == "formed":
            formed_event = event
        elif event.event_type == "f_skatt_registered":
            fskatt_event = event

    if formed_event and fskatt_event:
        days_diff = (fskatt_event.timestamp - formed_event.timestamp).days

        if 0 <= days_diff <= 30:
            data = dict(g.nodes[company_id])
            names = data.get("names", [{}])
            company_name = names[0].get("name", company_id) if names else company_id

            return PlaybookMatch(
                playbook_id="rapid_formation",
                playbook_name="Rapid Formation Pattern",
                severity="medium",
                confidence=1.0 - (days_diff / 30),  # Higher confidence for faster registration
                current_stage=2,
                total_stages=2,
                matched_events=[
                    {"type": "formed", "date": formed_event.timestamp.isoformat()},
                    {"type": "f_skatt_registered", "date": fskatt_event.timestamp.isoformat()},
                ],
                entity_id=company_id,
                company_name=company_name,
                alert=f"Company registered for F-skatt within {days_diff} days of formation"
            )

    return None


def detect_dormant_activation(g, company_id: str) -> Optional[PlaybookMatch]:
    """Detect dormant company activation pattern."""
    if company_id not in g.nodes:
        return None

    data = dict(g.nodes[company_id])

    # Check company age
    formation_date = data.get("formation", {}).get("date") or data.get("registration_date")
    if not formation_date:
        return None

    try:
        if isinstance(formation_date, str):
            formation_date = date.fromisoformat(formation_date)
        age_years = (date.today() - formation_date).days / 365
    except (ValueError, TypeError):
        return None

    if age_years < 5:
        return None

    # Check for recent director activity (would need allabolag data with dates)
    # For now, flag old companies with single director as potentially dormant/activated
    director_count = 0
    for u, v, edge_data in g.edges(data=True):
        if v == company_id and edge_data.get("_type") == "DirectsEdge":
            director_count += 1

    if director_count == 1:
        names = data.get("names", [{}])
        company_name = names[0].get("name", company_id) if names else company_id

        return PlaybookMatch(
            playbook_id="dormant_then_active",
            playbook_name="Dormant Company Pattern",
            severity="low",
            confidence=0.5,
            current_stage=1,
            total_stages=2,
            matched_events=[
                {"indicator": "old_company", "age_years": age_years},
                {"indicator": "single_director", "value": True},
            ],
            entity_id=company_id,
            company_name=company_name,
            alert=f"Old company ({age_years:.1f} years) with single director - potential dormant activation"
        )

    return None


def main():
    print("=" * 60)
    print("TEMPORAL SEQUENCE DETECTION")
    print("=" * 60)

    if not GRAPH_PATH.exists():
        print(f"Error: Graph not found at {GRAPH_PATH}")
        return 1

    g = load_graph()
    companies = [n for n, d in g.nodes(data=True) if d.get("_type") == "Company"]
    print(f"Loaded graph: {len(companies)} companies")

    all_matches = []

    # Run shell company detection
    print("\n[1] Detecting shell company indicators...")
    shell_matches = []
    for company_id in companies:
        match = detect_shell_company_pattern(g, company_id)
        if match:
            shell_matches.append(match)
    print(f"   Found {len(shell_matches)} companies with shell indicators")
    all_matches.extend(shell_matches)

    # Run rapid formation detection
    print("\n[2] Detecting rapid formation patterns...")
    rapid_matches = []
    for company_id in companies:
        match = detect_rapid_formation(g, company_id)
        if match:
            rapid_matches.append(match)
    print(f"   Found {len(rapid_matches)} companies with rapid formation")
    all_matches.extend(rapid_matches)

    # Run dormant activation detection
    print("\n[3] Detecting dormant company patterns...")
    dormant_matches = []
    for company_id in companies:
        match = detect_dormant_activation(g, company_id)
        if match:
            dormant_matches.append(match)
    print(f"   Found {len(dormant_matches)} potential dormant activations")
    all_matches.extend(dormant_matches)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    by_playbook = defaultdict(lambda: {"total": 0, "high": 0, "medium": 0, "low": 0})
    for match in all_matches:
        by_playbook[match.playbook_id]["total"] += 1
        by_playbook[match.playbook_id][match.severity] += 1

    for playbook_id, counts in by_playbook.items():
        print(f"\n{playbook_id}:")
        print(f"  Total: {counts['total']}")
        print(f"  High: {counts['high']}, Medium: {counts['medium']}, Low: {counts['low']}")

    # Generate alerts
    new_alerts = []
    for match in all_matches:
        if match.severity in ("high", "medium"):
            new_alerts.append({
                "id": f"sequence-{match.entity_id}-{match.playbook_id}",
                "alert_type": f"sequence_{match.playbook_id}",
                "severity": match.severity,
                "entity_id": match.entity_id,
                "entity_type": "Company",
                "description": match.alert,
                "evidence": {
                    "playbook": match.playbook_name,
                    "company_name": match.company_name,
                    "confidence": match.confidence,
                    "matched_events": match.matched_events,
                },
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

    print(f"\nGenerated {len(new_alerts)} new alerts")

    # Load and merge alerts
    existing_alerts = []
    if ALERTS_PATH.exists():
        with open(ALERTS_PATH) as f:
            existing_alerts = json.load(f)
        # Remove old sequence alerts
        existing_alerts = [a for a in existing_alerts if not a.get("alert_type", "").startswith("sequence_")]

    all_alerts = existing_alerts + new_alerts

    with open(ALERTS_PATH, "w") as f:
        json.dump(all_alerts, f, indent=2, default=str)
    print(f"Saved {len(all_alerts)} total alerts to {ALERTS_PATH}")

    # Save detailed results
    output = {
        "analysis_date": datetime.now(timezone.utc).isoformat(),
        "matches": [asdict(m) for m in all_matches],
        "summary": dict(by_playbook),
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Saved detailed results to {OUTPUT_PATH}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
