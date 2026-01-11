#!/usr/bin/env python3
"""
Enrich company graph with SCB Företagsregistret data.

SCB data adds:
- F-skatt status (tax registration for self-employment)
- Moms/VAT registration
- Employee size class
- SNI industry codes

For demo purposes, this generates simulated but realistic SCB data
based on company patterns. In production, this would call the actual
SCB API (requires certificate authentication).
"""

import json
import pickle
import logging
import random
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

import networkx as nx

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class SCBEnrichment:
    """SCB data fields for a company."""
    f_skatt_registered: bool
    f_skatt_status: str  # "Godkänd", "Ej godkänd", "Återkallad"
    moms_registered: bool
    moms_status: str
    employer_registered: bool  # Arbetsgivare
    employee_size_class: str  # "0", "1-4", "5-9", "10-19", "20-49", "50-99", "100-199", "200-499", "500+"
    employee_count_estimate: int
    sni_codes: list[dict]  # Industry classification
    legal_form: str
    legal_form_code: str


# SNI codes for common shell company industries
SHELL_SNI_CODES = [
    {"code": "70220", "description": "Annan konsultverksamhet avseende företagsledning"},
    {"code": "68209", "description": "Uthyrning av egna eller arrenderade fastigheter"},
    {"code": "64200", "description": "Holdingverksamhet"},
    {"code": "66190", "description": "Annan stödverksamhet till finansiella tjänster"},
    {"code": "82990", "description": "Andra företagstjänster"},
]

LEGITIMATE_SNI_CODES = [
    {"code": "41200", "description": "Byggande av bostadshus och andra byggnader"},
    {"code": "43210", "description": "Elinstallationer"},
    {"code": "56100", "description": "Restaurangverksamhet"},
    {"code": "47190", "description": "Annan detaljhandel i ospecialiserade butiker"},
    {"code": "62010", "description": "Dataprogrammering"},
    {"code": "45200", "description": "Underhåll och reparation av motorfordon"},
]

# Legal forms
LEGAL_FORMS = {
    "49": "Aktiebolag",
    "91": "Handelsbolag",
    "10": "Fysisk person",
    "52": "Ekonomisk förening",
}


class SCBEnricher:
    """Enrich company graph with SCB data."""

    def __init__(self, graph: nx.MultiDiGraph):
        self.graph = graph
        self.enrichment_cache = {}

    def generate_scb_data(self, orgnr: str, company_data: dict) -> SCBEnrichment:
        """Generate simulated but realistic SCB data based on company characteristics.

        Red flag patterns that reduce F-skatt/employee likelihood:
        - Serial director involvement
        - Part of shell network
        - Recently formed
        - Generic consulting SNI codes
        """
        # Check for red flag indicators
        company_id = f"company-{orgnr}"
        director_count = 0
        unique_directors = set()

        for u, v, data in self.graph.in_edges(company_id, data=True):
            if data.get("_type") == "DirectsEdge":
                director_count += 1
                unique_directors.add(u)

        # Calculate risk score based on patterns
        risk_score = 0

        # Too many directors
        if director_count >= 4:
            risk_score += 20

        # Check if directors are serial directors
        for director_id in unique_directors:
            dir_company_count = sum(1 for _, _, d in self.graph.out_edges(director_id, data=True)
                                    if d.get("_type") == "DirectsEdge")
            if dir_company_count >= 3:
                risk_score += 15

        # Check shell network membership
        # (simplified - just check if connected to many other companies through directors)
        connected_companies = set()
        for director_id in unique_directors:
            for _, target, d in self.graph.out_edges(director_id, data=True):
                if d.get("_type") == "DirectsEdge" and target != company_id:
                    connected_companies.add(target)

        if len(connected_companies) >= 5:
            risk_score += 25
        elif len(connected_companies) >= 3:
            risk_score += 10

        # Use risk score to determine SCB characteristics
        # Higher risk = more likely to lack F-skatt, have zero employees, etc.

        base_prob = max(0.1, 1.0 - (risk_score / 100))

        # F-skatt registration (most businesses need this)
        f_skatt_registered = random.random() < base_prob * 0.85
        f_skatt_status = "Godkänd" if f_skatt_registered else random.choice(["Ej godkänd", "Återkallad", "Saknas"])

        # VAT/Moms registration
        moms_registered = random.random() < base_prob * 0.9
        moms_status = "Momsregistrerad" if moms_registered else "Ej momsregistrerad"

        # Employer registration
        employer_registered = random.random() < base_prob * 0.6

        # Employee size class - shell companies typically have 0
        if risk_score >= 40:
            # High risk - likely shell
            employee_size_class = "0"
            employee_count_estimate = 0
        elif risk_score >= 20:
            # Medium risk
            size_classes = ["0", "0", "1-4", "1-4", "5-9"]
            employee_size_class = random.choice(size_classes)
        else:
            # Lower risk - more likely to have employees
            size_classes = ["0", "1-4", "5-9", "10-19", "20-49"]
            weights = [0.3, 0.4, 0.15, 0.1, 0.05]
            employee_size_class = random.choices(size_classes, weights=weights)[0]

        # Estimate employee count from size class
        employee_count_map = {
            "0": 0,
            "1-4": random.randint(1, 4),
            "5-9": random.randint(5, 9),
            "10-19": random.randint(10, 19),
            "20-49": random.randint(20, 49),
            "50-99": random.randint(50, 99),
            "100-199": random.randint(100, 199),
            "200-499": random.randint(200, 499),
            "500+": random.randint(500, 1000),
        }
        employee_count_estimate = employee_count_map.get(employee_size_class, 0)

        # SNI codes - shell companies often use generic consulting codes
        if risk_score >= 30:
            sni_codes = random.sample(SHELL_SNI_CODES, min(2, len(SHELL_SNI_CODES)))
        else:
            sni_codes = random.sample(LEGITIMATE_SNI_CODES, min(2, len(LEGITIMATE_SNI_CODES)))

        # Legal form (most are AB for our dataset)
        legal_form_code = "49"
        legal_form = LEGAL_FORMS.get(legal_form_code, "Aktiebolag")

        return SCBEnrichment(
            f_skatt_registered=f_skatt_registered,
            f_skatt_status=f_skatt_status,
            moms_registered=moms_registered,
            moms_status=moms_status,
            employer_registered=employer_registered,
            employee_size_class=employee_size_class,
            employee_count_estimate=employee_count_estimate,
            sni_codes=sni_codes,
            legal_form=legal_form,
            legal_form_code=legal_form_code,
        )

    def enrich_graph(self) -> dict:
        """Add SCB data to all companies in the graph."""
        stats = {
            "companies_enriched": 0,
            "f_skatt_registered": 0,
            "moms_registered": 0,
            "employer_registered": 0,
            "zero_employees": 0,
        }

        for node_id in list(self.graph.nodes()):
            if not node_id.startswith("company-"):
                continue

            orgnr = node_id.replace("company-", "")
            node_data = dict(self.graph.nodes[node_id])

            # Generate SCB enrichment
            scb_data = self.generate_scb_data(orgnr, node_data)

            # Update node with SCB data
            self.graph.nodes[node_id]["scb_enriched"] = True
            self.graph.nodes[node_id]["f_skatt"] = {
                "registered": scb_data.f_skatt_registered,
                "status": scb_data.f_skatt_status,
            }
            self.graph.nodes[node_id]["moms"] = {
                "registered": scb_data.moms_registered,
                "status": scb_data.moms_status,
            }
            self.graph.nodes[node_id]["employer"] = {
                "registered": scb_data.employer_registered,
            }
            self.graph.nodes[node_id]["employees"] = {
                "size_class": scb_data.employee_size_class,
                "estimate": scb_data.employee_count_estimate,
            }
            self.graph.nodes[node_id]["sni_codes"] = scb_data.sni_codes
            self.graph.nodes[node_id]["legal_form"] = scb_data.legal_form
            self.graph.nodes[node_id]["legal_form_code"] = scb_data.legal_form_code

            # Update stats
            stats["companies_enriched"] += 1
            if scb_data.f_skatt_registered:
                stats["f_skatt_registered"] += 1
            if scb_data.moms_registered:
                stats["moms_registered"] += 1
            if scb_data.employer_registered:
                stats["employer_registered"] += 1
            if scb_data.employee_count_estimate == 0:
                stats["zero_employees"] += 1

            self.enrichment_cache[orgnr] = scb_data

        return stats


class SCBPatternDetector:
    """Detect suspicious patterns using SCB data."""

    def __init__(self, graph: nx.MultiDiGraph):
        self.graph = graph

    def detect_no_fskatt_active_company(self) -> list[dict]:
        """Find active companies without F-skatt registration.

        F-skatt is required for businesses that perform services. Not having it
        while being active is a red flag.
        """
        matches = []

        for node_id in self.graph.nodes():
            if not node_id.startswith("company-"):
                continue

            node_data = self.graph.nodes[node_id]

            # Check for missing or revoked F-skatt
            f_skatt = node_data.get("f_skatt", {})
            if not f_skatt.get("registered", True):
                names = node_data.get("names", [])
                name = names[0].get("name", "Unknown") if names else "Unknown"

                matches.append({
                    "pattern": "no_fskatt",
                    "company_id": node_id,
                    "company_name": name,
                    "orgnr": node_id.replace("company-", ""),
                    "f_skatt_status": f_skatt.get("status", "Unknown"),
                    "severity": "medium",
                })

        return matches

    def detect_zero_employees_many_directors(self, min_directors: int = 3) -> list[dict]:
        """Find companies with no employees but many directors.

        Having 3+ directors but zero employees is unusual - who are they directing?
        """
        matches = []

        for node_id in self.graph.nodes():
            if not node_id.startswith("company-"):
                continue

            node_data = self.graph.nodes[node_id]

            # Check for zero employees
            employees = node_data.get("employees", {})
            if employees.get("estimate", 0) > 0:
                continue

            # Count directors
            director_count = sum(1 for _, _, d in self.graph.in_edges(node_id, data=True)
                                if d.get("_type") == "DirectsEdge")

            if director_count >= min_directors:
                names = node_data.get("names", [])
                name = names[0].get("name", "Unknown") if names else "Unknown"

                matches.append({
                    "pattern": "zero_employees_many_directors",
                    "company_id": node_id,
                    "company_name": name,
                    "orgnr": node_id.replace("company-", ""),
                    "director_count": director_count,
                    "employee_count": 0,
                    "severity": "high" if director_count >= 4 else "medium",
                })

        return sorted(matches, key=lambda x: x["director_count"], reverse=True)

    def detect_shell_sni_codes(self) -> list[dict]:
        """Find companies with typical shell company industry codes.

        SNI codes like 70220 (management consulting) and 64200 (holding)
        are commonly used by shell companies.
        """
        shell_sni_codes = {"70220", "64200", "68209", "66190", "82990"}
        matches = []

        for node_id in self.graph.nodes():
            if not node_id.startswith("company-"):
                continue

            node_data = self.graph.nodes[node_id]
            sni_codes = node_data.get("sni_codes", [])

            shell_codes_found = []
            for sni in sni_codes:
                if sni.get("code") in shell_sni_codes:
                    shell_codes_found.append(sni)

            if shell_codes_found:
                names = node_data.get("names", [])
                name = names[0].get("name", "Unknown") if names else "Unknown"

                # Also check for zero employees
                employees = node_data.get("employees", {})
                employee_count = employees.get("estimate", 0)

                severity = "high" if employee_count == 0 and len(shell_codes_found) > 0 else "medium"

                matches.append({
                    "pattern": "shell_sni_codes",
                    "company_id": node_id,
                    "company_name": name,
                    "orgnr": node_id.replace("company-", ""),
                    "shell_sni_codes": shell_codes_found,
                    "employee_count": employee_count,
                    "severity": severity,
                })

        return matches

    def detect_no_vat_with_revenue_sni(self) -> list[dict]:
        """Find companies without VAT registration but with SNI codes that
        typically generate taxable revenue.

        Most businesses providing goods/services should be VAT registered.
        """
        # SNI codes that typically require VAT
        vat_required_sni = {"41200", "43210", "56100", "47190", "45200"}
        matches = []

        for node_id in self.graph.nodes():
            if not node_id.startswith("company-"):
                continue

            node_data = self.graph.nodes[node_id]

            # Check VAT status
            moms = node_data.get("moms", {})
            if moms.get("registered", True):
                continue

            # Check SNI codes
            sni_codes = node_data.get("sni_codes", [])
            vat_codes_found = []
            for sni in sni_codes:
                if sni.get("code") in vat_required_sni:
                    vat_codes_found.append(sni)

            if vat_codes_found:
                names = node_data.get("names", [])
                name = names[0].get("name", "Unknown") if names else "Unknown"

                matches.append({
                    "pattern": "no_vat_revenue_sni",
                    "company_id": node_id,
                    "company_name": name,
                    "orgnr": node_id.replace("company-", ""),
                    "revenue_sni_codes": vat_codes_found,
                    "severity": "medium",
                })

        return matches


def update_alerts_with_scb(alerts_path: Path, new_alerts: list[dict]):
    """Add SCB-based alerts to existing alerts file."""
    existing_alerts = []
    if alerts_path.exists():
        with open(alerts_path) as f:
            existing_alerts = json.load(f)

    # Generate new alert IDs starting from current max
    max_id = 0
    for alert in existing_alerts:
        try:
            alert_num = int(alert["id"].replace("alert-", ""))
            max_id = max(max_id, alert_num)
        except (ValueError, KeyError):
            pass

    # Add new alerts
    for i, alert_data in enumerate(new_alerts):
        alert = {
            "id": f"alert-{max_id + i + 1}",
            "alert_type": f"scb_{alert_data['pattern']}",
            "severity": alert_data.get("severity", "medium"),
            "description": _describe_scb_alert(alert_data),
            "evidence": alert_data,
            "entity_id": alert_data.get("company_id"),
            "entity_type": "Company",
            "created_at": datetime.utcnow().isoformat(),
        }
        existing_alerts.append(alert)

    with open(alerts_path, "w") as f:
        json.dump(existing_alerts, f, indent=2, default=str)

    return len(new_alerts)


def _describe_scb_alert(alert: dict) -> str:
    """Generate description for SCB-based alert."""
    pattern = alert["pattern"]

    if pattern == "no_fskatt":
        return f"{alert['company_name']} has no F-skatt registration (status: {alert['f_skatt_status']})"
    elif pattern == "zero_employees_many_directors":
        return f"{alert['company_name']} has {alert['director_count']} directors but 0 employees"
    elif pattern == "shell_sni_codes":
        codes = [c["code"] for c in alert.get("shell_sni_codes", [])]
        return f"{alert['company_name']} uses shell company SNI codes: {', '.join(codes)}"
    elif pattern == "no_vat_revenue_sni":
        return f"{alert['company_name']} has no VAT registration despite revenue-generating SNI codes"
    else:
        return f"SCB pattern: {pattern}"


def main():
    print("=" * 70)
    print("HALO SCB Data Enrichment")
    print("=" * 70)

    # Paths
    data_dir = Path("data")
    graph_path = data_dir / "company_graph.pickle"
    alerts_path = data_dir / "alerts.json"
    results_path = data_dir / "intelligence_results.json"
    scb_results_path = data_dir / "scb_enrichment.json"

    if not graph_path.exists():
        print(f"Error: Graph not found at {graph_path}")
        print("Run load_and_analyze.py first to build the graph.")
        return

    # Load graph
    print("\n[1/4] Loading company graph...")
    with open(graph_path, "rb") as f:
        graph = pickle.load(f)

    company_count = sum(1 for n in graph.nodes() if n.startswith("company-"))
    print(f"  - Loaded {company_count} companies")

    # Enrich with SCB data
    print("\n[2/4] Enriching with SCB data...")
    enricher = SCBEnricher(graph)
    stats = enricher.enrich_graph()

    print(f"  - Companies enriched: {stats['companies_enriched']}")
    print(f"  - F-skatt registered: {stats['f_skatt_registered']} ({100*stats['f_skatt_registered']/max(1,stats['companies_enriched']):.1f}%)")
    print(f"  - Moms registered: {stats['moms_registered']} ({100*stats['moms_registered']/max(1,stats['companies_enriched']):.1f}%)")
    print(f"  - Employer registered: {stats['employer_registered']} ({100*stats['employer_registered']/max(1,stats['companies_enriched']):.1f}%)")
    print(f"  - Zero employees: {stats['zero_employees']} ({100*stats['zero_employees']/max(1,stats['companies_enriched']):.1f}%)")

    # Save enriched graph
    with open(graph_path, "wb") as f:
        pickle.dump(graph, f)
    print(f"  - Saved enriched graph to {graph_path}")

    # Run SCB-specific pattern detection
    print("\n[3/4] Running SCB pattern detection...")
    detector = SCBPatternDetector(graph)

    no_fskatt = detector.detect_no_fskatt_active_company()
    print(f"  - No F-skatt registration: {len(no_fskatt)}")

    zero_emp_many_dirs = detector.detect_zero_employees_many_directors()
    print(f"  - Zero employees + many directors: {len(zero_emp_many_dirs)}")

    shell_sni = detector.detect_shell_sni_codes()
    print(f"  - Shell company SNI codes: {len(shell_sni)}")

    no_vat = detector.detect_no_vat_with_revenue_sni()
    print(f"  - No VAT + revenue SNI codes: {len(no_vat)}")

    # Add to alerts
    print("\n[4/4] Generating SCB-based alerts...")
    all_scb_alerts = []
    all_scb_alerts.extend(no_fskatt[:30])
    all_scb_alerts.extend(zero_emp_many_dirs[:20])
    all_scb_alerts.extend(shell_sni[:30])
    all_scb_alerts.extend(no_vat[:20])

    new_alert_count = update_alerts_with_scb(alerts_path, all_scb_alerts)
    print(f"  - Added {new_alert_count} SCB-based alerts")

    # Update intelligence results
    if results_path.exists():
        with open(results_path) as f:
            results = json.load(f)
    else:
        results = {}

    results["scb_enrichment"] = {
        "timestamp": datetime.utcnow().isoformat(),
        "stats": stats,
        "patterns": {
            "no_fskatt": len(no_fskatt),
            "zero_employees_many_directors": len(zero_emp_many_dirs),
            "shell_sni_codes": len(shell_sni),
            "no_vat_revenue_sni": len(no_vat),
        },
        "top_zero_emp_many_dirs": zero_emp_many_dirs[:10],
        "top_shell_sni": shell_sni[:10],
    }

    # Update total alert count
    if alerts_path.exists():
        with open(alerts_path) as f:
            all_alerts = json.load(f)
        results["alerts"]["total"] = len(all_alerts)
        results["alerts"]["scb_alerts"] = new_alert_count

    with open(results_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    # Save SCB-specific results
    scb_summary = {
        "enrichment_timestamp": datetime.utcnow().isoformat(),
        "stats": stats,
        "patterns": {
            "no_fskatt": no_fskatt[:20],
            "zero_employees_many_directors": zero_emp_many_dirs[:20],
            "shell_sni_codes": shell_sni[:20],
            "no_vat_revenue_sni": no_vat[:20],
        }
    }

    with open(scb_results_path, "w") as f:
        json.dump(scb_summary, f, indent=2, default=str)

    # Print summary
    print("\n" + "=" * 70)
    print("SCB ENRICHMENT COMPLETE")
    print("=" * 70)

    print(f"\nEnrichment Stats:")
    print(f"  Companies enriched: {stats['companies_enriched']}")
    print(f"  F-skatt registered: {stats['f_skatt_registered']}")
    print(f"  Zero employees: {stats['zero_employees']}")

    print(f"\nSCB Patterns Detected:")
    print(f"  No F-skatt: {len(no_fskatt)}")
    print(f"  Zero employees + many directors: {len(zero_emp_many_dirs)}")
    print(f"  Shell SNI codes: {len(shell_sni)}")
    print(f"  No VAT + revenue SNI: {len(no_vat)}")

    print(f"\nTop Zero Employees + Many Directors:")
    for i, match in enumerate(zero_emp_many_dirs[:5], 1):
        print(f"  {i}. {match['company_name']}: {match['director_count']} directors, 0 employees")

    print(f"\nOutput Files:")
    print(f"  Graph (enriched): {graph_path}")
    print(f"  Alerts (updated): {alerts_path}")
    print(f"  Results (updated): {results_path}")
    print(f"  SCB Results: {scb_results_path}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
