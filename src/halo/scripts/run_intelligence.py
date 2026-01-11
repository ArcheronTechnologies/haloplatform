#!/usr/bin/env python3
"""
Run intelligence analysis on loaded Swedish company data.

Week 2: Analyze 1000 real companies from SCB for shell company indicators,
anomalous patterns, and risk scoring.
"""

import asyncio
import json
import pickle
import logging
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import networkx as nx

from halo.intelligence.anomaly import AnomalyDetector, AnomalyScore, ANOMALY_THRESHOLDS

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SCBGraphAnalyzer:
    """Analyze SCB company graph for shell company indicators."""

    # Generic SNI codes commonly used by shell companies
    GENERIC_SNI_CODES = {
        "70": "Head offices; management consultancy",
        "82": "Office administrative, office support",
        "64": "Financial services, except insurance",
        "66": "Other financial activities",
        "68": "Real estate activities",
        "69": "Legal and accounting activities",
    }

    # Virtual office indicators in address
    VIRTUAL_OFFICE_KEYWORDS = [
        "box", "postbox", "c/o", "att:", "kontorshotell",
    ]

    def __init__(self, graph_path: str):
        """Load the graph from pickle file."""
        with open(graph_path, "rb") as f:
            self.graph: nx.MultiDiGraph = pickle.load(f)
        logger.info(f"Loaded graph: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges")

    def get_companies(self) -> list[dict]:
        """Get all company nodes with their data."""
        companies = []
        for node_id in self.graph.nodes():
            if node_id.startswith("company-"):
                data = dict(self.graph.nodes[node_id])
                data["node_id"] = node_id
                companies.append(data)
        return companies

    def get_addresses(self) -> list[dict]:
        """Get all address nodes with their data."""
        addresses = []
        for node_id in self.graph.nodes():
            if node_id.startswith("address-"):
                data = dict(self.graph.nodes[node_id])
                data["node_id"] = node_id
                addresses.append(data)
        return addresses

    def get_companies_at_address(self, address_id: str) -> list[str]:
        """Get company IDs registered at an address."""
        company_ids = []
        # Find incoming edges to this address (companies -> address)
        for u, v, data in self.graph.in_edges(address_id, data=True):
            if data.get("_type") == "RegisteredAtEdge" and u.startswith("company-"):
                company_ids.append(u)
        return company_ids

    # SCB employee size classes
    # 1 = 0 employees, 2 = 1-4, 3 = 5-9, 4 = 10-19, 5 = 20-49, etc.
    SIZE_CLASS_ZERO_EMPLOYEES = {"1", "0", ""}

    def analyze_company(self, company: dict) -> dict:
        """
        Analyze a single company for shell indicators using SCB data.

        Shell detection logic based on Swedish tax registration patterns:
        - No F-skatt + No VAT = major red flag (no economic activity)
        - F-skatt without VAT = unusual for Swedish companies
        - VAT without F-skatt = can't invoice as contractor
        - AB (Aktiebolag) with no registrations = classic shell structure

        Returns dict with indicators and risk score.
        """
        indicators = {}
        flags = []
        shell_score = 0.0

        # === TAX REGISTRATION ANALYSIS (most important) ===
        f_skatt = company.get("f_skatt", {})
        vat = company.get("vat", {})
        f_skatt_registered = f_skatt.get("registered", False)
        vat_registered = vat.get("registered", False)

        # No tax registrations at all = major red flag
        no_tax_registrations = not f_skatt_registered and not vat_registered
        indicators["no_tax_registrations"] = no_tax_registrations
        if no_tax_registrations:
            shell_score += 0.5  # Major indicator
            flags.append({
                "type": "no_tax_registrations",
                "severity": "high",
                "detail": "No F-skatt, no VAT - no economic activity registrations"
            })

        # F-skatt without VAT (unusual for Swedish companies)
        f_skatt_no_vat = f_skatt_registered and not vat_registered
        indicators["f_skatt_no_vat"] = f_skatt_no_vat
        if f_skatt_no_vat:
            shell_score += 0.2
            flags.append({
                "type": "f_skatt_no_vat",
                "severity": "medium",
                "detail": "Has F-skatt but not VAT registered"
            })

        # VAT without F-skatt (can receive VAT but can't invoice as contractor)
        vat_no_f_skatt = vat_registered and not f_skatt_registered
        indicators["vat_no_f_skatt"] = vat_no_f_skatt
        if vat_no_f_skatt:
            shell_score += 0.1
            flags.append({
                "type": "vat_no_f_skatt",
                "severity": "low",
                "detail": "Has VAT but not F-skatt"
            })

        # === EMPLOYEE COUNT ===
        employees = company.get("employees", {})
        size_class = str(employees.get("size_class", "")).strip()
        size_text = employees.get("size_class_text", "")

        no_employees = size_class in self.SIZE_CLASS_ZERO_EMPLOYEES
        indicators["no_employees"] = no_employees
        if no_employees:
            shell_score += 0.15
            flags.append({
                "type": "no_employees",
                "severity": "medium",
                "detail": f"Size class: {size_text or '0 employees'}"
            })

        # === LEGAL FORM + TAX STATUS COMBO ===
        legal_form = company.get("legal_form", "")
        # AB (Aktiebolag, code 49) with no activity = classic shell
        is_ab = legal_form == "49"
        ab_no_activity = is_ab and no_tax_registrations
        indicators["ab_no_activity"] = ab_no_activity
        if ab_no_activity:
            shell_score += 0.15  # Additional penalty for AB shells
            flags.append({
                "type": "ab_no_activity",
                "severity": "high",
                "detail": "Aktiebolag with no tax registrations - classic shell structure"
            })

        # === SNI CODES (generic/holding indicators) ===
        sni_codes = company.get("sni_codes", [])
        generic_sni = False
        sni_details = []
        for sni in sni_codes:
            code = sni.get("code", "")
            desc = sni.get("description", "")
            code_2digit = code[:2] if code else ""
            if code_2digit in self.GENERIC_SNI_CODES:
                generic_sni = True
                sni_details.append(f"{code}: {desc}")

        indicators["generic_sni"] = generic_sni
        if generic_sni:
            shell_score += 0.1
            flags.append({
                "type": "generic_sni_code",
                "severity": "low",
                "detail": f"SNI: {', '.join(sni_details[:2])}"  # Limit to 2
            })

        # === FORMATION DATE ===
        formation = company.get("formation", {})
        start_date = formation.get("date")
        recently_formed = False
        if start_date:
            try:
                start = datetime.strptime(start_date, "%Y-%m-%d").date()
                days_old = (datetime.now().date() - start).days
                recently_formed = days_old < 365 * 2  # Less than 2 years old
                indicators["recently_formed"] = recently_formed
                if recently_formed:
                    shell_score += 0.05
                    flags.append({
                        "type": "recently_formed",
                        "severity": "low",
                        "detail": f"Formed {start_date} ({days_old} days ago)"
                    })
            except (ValueError, TypeError):
                indicators["recently_formed"] = False

        # === FINAL SCORE CALCULATION ===
        shell_score = min(1.0, shell_score)  # Cap at 100%

        # Determine risk level based on score
        indicator_count = sum(1 for v in indicators.values() if v)
        if shell_score >= 0.5:
            risk_level = "high"
            flags.append({
                "type": "high_shell_probability",
                "severity": "high",
                "detail": f"Shell score: {shell_score:.0%} ({indicator_count} indicators)"
            })
        elif shell_score >= 0.25:
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "company_id": company.get("node_id"),
            "orgnr": company.get("orgnr"),
            "name": company.get("names", [{}])[0].get("name", "Unknown"),
            "legal_form": company.get("legal_form"),
            "indicators": indicators,
            "shell_score": shell_score,
            "risk_level": risk_level,
            "flags": flags,
        }

    def analyze_address_density(self) -> list[dict]:
        """Find addresses with high company density."""
        address_companies = defaultdict(list)

        # Build address -> companies mapping
        for edge in self.graph.edges(data=True):
            u, v, data = edge
            if data.get("_type") == "RegisteredAtEdge":
                if u.startswith("company-") and v.startswith("address-"):
                    address_companies[v].append(u)

        # Find high-density addresses
        high_density = []
        for addr_id, company_ids in address_companies.items():
            if len(company_ids) > 1:  # More than 1 company
                addr_data = self.graph.nodes.get(addr_id, {})
                normalized = addr_data.get("normalized", {})

                high_density.append({
                    "address_id": addr_id,
                    "company_count": len(company_ids),
                    "city": normalized.get("city", ""),
                    "postal_code": normalized.get("postal_code", ""),
                    "street": normalized.get("street", ""),
                    "company_ids": company_ids[:10],  # First 10
                    "is_suspicious": len(company_ids) >= ANOMALY_THRESHOLDS["companies_at_address"],
                })

        # Sort by company count descending
        high_density.sort(key=lambda x: x["company_count"], reverse=True)
        return high_density

    def analyze_sni_distribution(self) -> dict:
        """Analyze SNI code distribution."""
        sni_counter = Counter()
        sni_names = {}

        for company in self.get_companies():
            sni_codes = company.get("sni_codes", [])
            for sni in sni_codes:
                code = sni.get("code", "")
                desc = sni.get("description", "")
                if code:
                    code_2digit = code[:2]
                    sni_counter[code_2digit] += 1
                    if code_2digit not in sni_names:
                        sni_names[code_2digit] = desc.split(",")[0] if desc else code_2digit

        return {
            "distribution": dict(sni_counter.most_common(20)),
            "names": sni_names,
            "generic_code_count": sum(
                sni_counter[code] for code in self.GENERIC_SNI_CODES if code in sni_counter
            ),
        }

    def run_full_analysis(self) -> dict:
        """Run full intelligence analysis on the graph."""
        logger.info("Starting full intelligence analysis...")

        companies = self.get_companies()
        logger.info(f"Analyzing {len(companies)} companies...")

        # Analyze each company
        company_results = []
        risk_counts = Counter()

        for company in companies:
            result = self.analyze_company(company)
            company_results.append(result)
            risk_counts[result["risk_level"]] += 1

        # Sort by shell score descending
        company_results.sort(key=lambda x: x["shell_score"], reverse=True)

        # Analyze addresses
        logger.info("Analyzing address density...")
        address_density = self.analyze_address_density()
        suspicious_addresses = [a for a in address_density if a["is_suspicious"]]

        # Analyze SNI distribution
        logger.info("Analyzing SNI distribution...")
        sni_analysis = self.analyze_sni_distribution()

        # Summary statistics
        high_risk = [r for r in company_results if r["risk_level"] == "high"]
        medium_risk = [r for r in company_results if r["risk_level"] == "medium"]

        return {
            "summary": {
                "total_companies": len(companies),
                "total_addresses": len(self.get_addresses()),
                "risk_distribution": dict(risk_counts),
                "high_risk_count": len(high_risk),
                "medium_risk_count": len(medium_risk),
                "suspicious_address_count": len(suspicious_addresses),
                "generic_sni_count": sni_analysis["generic_code_count"],
            },
            "high_risk_companies": high_risk[:20],  # Top 20
            "suspicious_addresses": suspicious_addresses[:10],  # Top 10
            "sni_distribution": sni_analysis,
            "all_results": company_results,
        }


def main():
    print("=" * 70)
    print("HALO Intelligence Analysis - Swedish Company Data")
    print("=" * 70)

    graph_path = Path("./halo/data/scb_graph.pickle")
    if not graph_path.exists():
        print(f"Error: Graph file not found at {graph_path}")
        print("Run load_scb_companies.py first to fetch data.")
        return

    analyzer = SCBGraphAnalyzer(str(graph_path))

    # Run analysis
    results = analyzer.run_full_analysis()

    # Print summary
    print("\n" + "=" * 70)
    print("ANALYSIS SUMMARY")
    print("=" * 70)

    summary = results["summary"]
    print(f"\nTotal Companies Analyzed: {summary['total_companies']}")
    print(f"Total Addresses: {summary['total_addresses']}")

    print(f"\nRisk Distribution:")
    for level, count in sorted(summary["risk_distribution"].items()):
        pct = count / summary["total_companies"] * 100
        bar = "#" * int(pct / 2)
        print(f"  {level.upper():8} {count:4} ({pct:5.1f}%) {bar}")

    print(f"\nKey Findings:")
    print(f"  - High-risk companies: {summary['high_risk_count']}")
    print(f"  - Suspicious addresses (>={ANOMALY_THRESHOLDS['companies_at_address']} companies): {summary['suspicious_address_count']}")
    print(f"  - Companies with generic SNI codes: {summary['generic_sni_count']}")

    # Top suspicious companies
    print("\n" + "=" * 70)
    print("TOP 10 HIGHEST RISK COMPANIES")
    print("=" * 70)

    for i, company in enumerate(results["high_risk_companies"][:10], 1):
        print(f"\n{i}. {company['name']}")
        print(f"   Org Nr: {company['orgnr']}")
        print(f"   Shell Score: {company['shell_score']:.0%}")
        print(f"   Flags:")
        for flag in company["flags"]:
            print(f"     - [{flag['severity'].upper()}] {flag['type']}: {flag['detail']}")

    # Suspicious addresses
    print("\n" + "=" * 70)
    print("TOP SUSPICIOUS ADDRESSES (Multi-Company Registrations)")
    print("=" * 70)

    for addr in results["suspicious_addresses"][:10]:
        print(f"\n  {addr['street']}, {addr['postal_code']} {addr['city']}")
        print(f"  Companies registered: {addr['company_count']}")

    # SNI distribution
    print("\n" + "=" * 70)
    print("SNI CODE DISTRIBUTION (Top 10)")
    print("=" * 70)

    sni = results["sni_distribution"]
    for code, count in list(sni["distribution"].items())[:10]:
        name = sni["names"].get(code, "")
        is_generic = " [GENERIC]" if code in analyzer.GENERIC_SNI_CODES else ""
        print(f"  {code}: {count:4} - {name[:50]}{is_generic}")

    # Save results
    output_dir = Path("./halo/data")
    output_file = output_dir / "intelligence_results.json"

    # Prepare JSON-safe output
    output_data = {
        "analysis_timestamp": datetime.now().isoformat(),
        "summary": results["summary"],
        "high_risk_companies": results["high_risk_companies"],
        "suspicious_addresses": results["suspicious_addresses"],
        "sni_distribution": results["sni_distribution"],
    }

    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2, default=str)
    print(f"\n\nDetailed results saved to: {output_file}")

    print("\n" + "=" * 70)
    print("Analysis Complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
