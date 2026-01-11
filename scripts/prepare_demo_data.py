#!/usr/bin/env python3
"""
Prepare demo data by combining ALL data sources:

1. SCB Full Registry (644K companies) - data/scb_full_registry.json
   - Company names, addresses, SNI codes, F-skatt, VAT, employees, etc.

2. Bolagsverket Enrichment (directors) - data/bolagsverket_enriched.db
   - Directors extracted from annual reports via XBRL/PDF

Generates:
- company_graph.pickle - NetworkX graph with companies, directors, addresses
- intelligence_results.json - Detection results (shell scores, serial directors, etc.)
- alerts.json - Alerts for the demo UI
"""

import json
import pickle
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx

DATA_DIR = Path(__file__).parent.parent / "data"
SCB_REGISTRY_PATH = DATA_DIR / "scb_full_registry.json"
BOLAGSVERKET_DB_PATH = DATA_DIR / "bolagsverket_enriched.db"


def load_scb_companies(limit: int = None) -> dict:
    """Load companies from SCB full registry."""
    print(f"Loading SCB registry from {SCB_REGISTRY_PATH}...")

    with open(SCB_REGISTRY_PATH) as f:
        data = json.load(f)

    scb_companies = data.get("companies", [])
    if limit:
        scb_companies = scb_companies[:limit]

    companies = {}
    for c in scb_companies:
        orgnr = c.get("orgnr")
        if not orgnr:
            continue

        raw = c.get("raw", {})

        companies[orgnr] = {
            "orgnr": orgnr,
            "name": raw.get("Företagsnamn", ""),
            "legal_form": raw.get("Juridisk form", ""),
            "status": raw.get("Företagsstatus", ""),
            "registration_date": raw.get("Registreringsdatum", ""),
            "address_street": raw.get("PostAdress", ""),
            "address_postal_code": raw.get("PostNr", ""),
            "address_city": raw.get("PostOrt", ""),
            "municipality": raw.get("Säteskommun", ""),
            "sni_codes": [raw.get("Bransch_1, kod", "").strip()] if raw.get("Bransch_1, kod", "").strip() else [],
            "sni_description": raw.get("Bransch_1", ""),
            "f_skatt": raw.get("Fskattstatus", "") == "Är registrerad för F-skatt",
            "moms": raw.get("Momsstatus", "") == "Är registrerad för moms",
            "employer": raw.get("Arbetsgivarstatus", "") == "Är registrerad som vanlig arbetsgivare",
            "employee_class": raw.get("Storleksklass", ""),
            "sector": raw.get("Sektor", ""),
            "ownership": raw.get("Ägarkategori", ""),
            "start_date": raw.get("Startdatum", ""),
            "phone": raw.get("Telefon", ""),
            "email": raw.get("E-post", ""),
        }

    print(f"  Loaded {len(companies):,} companies from SCB")
    return companies


def load_bolagsverket_directors() -> tuple:
    """Load directors from Bolagsverket enrichment database."""
    if not BOLAGSVERKET_DB_PATH.exists():
        print(f"  Warning: Bolagsverket DB not found at {BOLAGSVERKET_DB_PATH}")
        return [], {}

    conn = sqlite3.connect(BOLAGSVERKET_DB_PATH)
    conn.row_factory = sqlite3.Row

    # Load directors
    directors = []
    for row in conn.execute("SELECT * FROM directors"):
        directors.append(dict(row))

    # Load Bolagsverket company data (for address/purpose enrichment)
    bv_companies = {}
    for row in conn.execute("SELECT * FROM companies"):
        bv_companies[row["orgnr"]] = dict(row)

    conn.close()

    print(f"  Loaded {len(directors):,} directors from Bolagsverket")
    print(f"  Loaded {len(bv_companies):,} enriched companies from Bolagsverket")
    return directors, bv_companies


def merge_company_data(scb_companies: dict, bv_companies: dict) -> dict:
    """Merge SCB and Bolagsverket company data."""
    merged = scb_companies.copy()

    enriched_count = 0
    for orgnr, bv_data in bv_companies.items():
        if orgnr in merged:
            # Enrich with Bolagsverket data
            if bv_data.get("purpose"):
                merged[orgnr]["purpose"] = bv_data["purpose"]
            if bv_data.get("address_street") and not merged[orgnr].get("address_street"):
                merged[orgnr]["address_street"] = bv_data["address_street"]
            merged[orgnr]["has_annual_reports"] = True
            enriched_count += 1
        else:
            # Add company from Bolagsverket that wasn't in SCB
            merged[orgnr] = {
                "orgnr": orgnr,
                "name": bv_data.get("name", ""),
                "legal_form": bv_data.get("legal_form", ""),
                "status": bv_data.get("status", ""),
                "registration_date": bv_data.get("registration_date", ""),
                "address_street": bv_data.get("address_street", ""),
                "address_postal_code": bv_data.get("address_postal_code", ""),
                "address_city": bv_data.get("address_city", ""),
                "sni_codes": json.loads(bv_data.get("sni_codes") or "[]"),
                "purpose": bv_data.get("purpose", ""),
                "has_annual_reports": True,
            }

    print(f"  Enriched {enriched_count:,} companies with Bolagsverket data")
    return merged


def build_graph(companies: dict, directors: list) -> nx.MultiDiGraph:
    """Build NetworkX graph from companies and directors."""
    G = nx.MultiDiGraph()

    # Add company nodes
    for orgnr, company in companies.items():
        company_id = f"company-{orgnr}"

        sni_codes = company.get("sni_codes", [])
        if isinstance(sni_codes, str):
            try:
                sni_codes = json.loads(sni_codes)
            except:
                sni_codes = [sni_codes] if sni_codes else []

        G.add_node(
            company_id,
            _type="Company",
            orgnr=orgnr,
            names=[{"name": company.get("name") or "Unknown", "type": "primary"}],
            legal_form=company.get("legal_form"),
            status=company.get("status"),
            registration_date=company.get("registration_date"),
            sni_codes=sni_codes,
            sni_description=company.get("sni_description", ""),
            address={
                "street": company.get("address_street"),
                "postal_code": company.get("address_postal_code"),
                "city": company.get("address_city"),
            },
            municipality=company.get("municipality", ""),
            f_skatt=company.get("f_skatt", False),
            moms=company.get("moms", False),
            employer=company.get("employer", False),
            employee_class=company.get("employee_class", ""),
            sector=company.get("sector", ""),
            has_annual_reports=company.get("has_annual_reports", False),
        )

    # Group directors by normalized name for person node creation
    person_companies = defaultdict(list)

    for d in directors:
        full_name = d.get("full_name") or f"{d.get('first_name', '')} {d.get('last_name', '')}".strip()
        if not full_name or full_name == " ":
            continue

        name_key = full_name.lower().strip()
        person_companies[name_key].append({
            "orgnr": d["orgnr"],
            "role": d.get("role_normalized", "UNKNOWN"),
            "role_original": d.get("role", ""),
            "confidence": d.get("confidence", 0.5),
            "full_name": full_name,
        })

    # Create person nodes and edges
    person_count = 0

    for name_key, roles in person_companies.items():
        full_name = roles[0]["full_name"]
        person_id = f"person-{person_count}"
        person_count += 1

        # Deduplicate companies
        unique_companies = {}
        for r in roles:
            if r["orgnr"] not in unique_companies:
                unique_companies[r["orgnr"]] = r

        company_count = len(unique_companies)

        G.add_node(
            person_id,
            _type="Person",
            names=[{"name": full_name}],
            full_name=full_name,
            company_count=company_count,
            roles=list(set(r["role"] for r in roles)),
        )

        # Add edges to companies (deduplicated)
        for orgnr, role_info in unique_companies.items():
            company_id = f"company-{orgnr}"
            if company_id in G.nodes:
                G.add_edge(
                    person_id,
                    company_id,
                    _type="DIRECTS",
                    role=role_info["role"],
                    role_original=role_info["role_original"],
                    confidence=role_info["confidence"],
                )

    # Add address nodes and edges
    address_companies = defaultdict(list)
    for orgnr, company in companies.items():
        postal_code = (company.get("address_postal_code") or "").strip()
        city = (company.get("address_city") or "").strip()
        if postal_code or city:
            addr_key = f"{postal_code}:{city}".lower()
            address_companies[addr_key].append(orgnr)

    address_count = 0
    for addr_key, orgnrs in address_companies.items():
        if len(orgnrs) >= 2:  # Only create nodes for shared addresses
            addr_id = f"address-{address_count}"
            address_count += 1

            sample_company = companies.get(orgnrs[0], {})

            G.add_node(
                addr_id,
                _type="Address",
                normalized={
                    "street": sample_company.get("address_street", ""),
                    "postal_code": sample_company.get("address_postal_code", ""),
                    "city": sample_company.get("address_city", ""),
                },
                company_count=len(orgnrs),
            )

            for orgnr in orgnrs:
                company_id = f"company-{orgnr}"
                if company_id in G.nodes:
                    G.add_edge(
                        company_id,
                        addr_id,
                        _type="REGISTERED_AT",
                    )

    print(f"\nBuilt graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")
    print(f"  - Companies: {len(companies):,}")
    print(f"  - Persons: {person_count:,}")
    print(f"  - Addresses: {address_count:,}")

    return G


def detect_patterns(G: nx.MultiDiGraph, companies: dict) -> dict:
    """Run detection algorithms on the graph."""
    results = {
        "high_risk_companies": [],
        "suspicious_addresses": [],
        "serial_directors": [],
        "shell_networks": [],
        "shared_directors": [],
        "summary": {},
    }

    # === Serial Directors ===
    print("\nDetecting serial directors...")
    serial_directors = []
    for node_id, data in G.nodes(data=True):
        if data.get("_type") == "Person":
            company_count = data.get("company_count", 0)
            if company_count >= 3:
                # Get the companies (deduplicated)
                directed_companies = {}
                for _, target, edge_data in G.out_edges(node_id, data=True):
                    if edge_data.get("_type") == "DIRECTS":
                        company_data = G.nodes.get(target, {})
                        orgnr = company_data.get("orgnr")
                        if orgnr and orgnr not in directed_companies:
                            directed_companies[orgnr] = {
                                "orgnr": orgnr,
                                "name": (company_data.get("names") or [{}])[0].get("name", ""),
                                "role": edge_data.get("role", "UNKNOWN"),
                            }

                serial_directors.append({
                    "person_id": node_id,
                    "name": data.get("full_name"),
                    "company_count": len(directed_companies),
                    "companies": list(directed_companies.values()),
                    "risk_score": min(1.0, len(directed_companies) / 10),
                })

    serial_directors.sort(key=lambda x: x["company_count"], reverse=True)
    results["serial_directors"] = serial_directors
    print(f"  Found {len(serial_directors):,} serial directors (3+ companies)")

    # === Suspicious Addresses ===
    print("Detecting suspicious addresses...")
    suspicious_addresses = []
    for node_id, data in G.nodes(data=True):
        if data.get("_type") == "Address":
            company_count = data.get("company_count", 0)
            if company_count >= 5:
                normalized = data.get("normalized", {})
                suspicious_addresses.append({
                    "address_id": node_id,
                    "street": normalized.get("street", ""),
                    "postal_code": normalized.get("postal_code", ""),
                    "city": normalized.get("city", ""),
                    "company_count": company_count,
                })

    suspicious_addresses.sort(key=lambda x: x["company_count"], reverse=True)
    results["suspicious_addresses"] = suspicious_addresses
    print(f"  Found {len(suspicious_addresses):,} suspicious addresses (5+ companies)")

    # === Shell Score Calculation ===
    print("Calculating shell scores...")
    high_risk = []
    all_results = []

    for node_id, data in G.nodes(data=True):
        if data.get("_type") != "Company":
            continue

        orgnr = data.get("orgnr")
        name = (data.get("names") or [{}])[0].get("name", "Unknown")

        shell_score = 0.0
        flags = []
        indicators = {}

        # 1. No directors found
        director_edges = [e for _, _, e in G.in_edges(node_id, data=True) if e.get("_type") == "DIRECTS"]
        director_count = len(director_edges)
        indicators["director_count"] = director_count

        # Companies with no directors in our data get a small penalty
        # (they might just not have filed digitally yet)

        # 2. Serial director involvement
        serial_director_involved = False
        for person_id, _, _ in G.in_edges(node_id, data=True):
            person_data = G.nodes.get(person_id, {})
            if person_data.get("company_count", 0) >= 5:
                serial_director_involved = True
                break

        if serial_director_involved:
            shell_score += 0.25
            flags.append("serial_director")
            indicators["serial_director"] = True

        # 3. Shared address with many companies
        shared_address = False
        for _, addr_id, edge_data in G.out_edges(node_id, data=True):
            if edge_data.get("_type") == "REGISTERED_AT":
                addr_data = G.nodes.get(addr_id, {})
                if addr_data.get("company_count", 0) >= 10:
                    shared_address = True
                    break

        if shared_address:
            shell_score += 0.25
            flags.append("shared_address")
            indicators["shared_address"] = True

        # 4. No F-skatt registration
        if not data.get("f_skatt"):
            shell_score += 0.1
            flags.append("no_fskatt")
        indicators["f_skatt"] = data.get("f_skatt", False)

        # 5. No employees
        employee_class = data.get("employee_class", "")
        if "0 anställda" in employee_class or employee_class == "":
            shell_score += 0.1
            flags.append("no_employees")
        indicators["employee_class"] = employee_class

        # 6. Shell-typical SNI codes
        sni_codes = data.get("sni_codes", [])
        shell_snis = {"70220", "64200", "68100", "68200", "70100"}  # Holding, real estate, management consulting
        if any(sni in shell_snis for sni in sni_codes):
            shell_score += 0.15
            flags.append("shell_sni")
        indicators["sni_codes"] = sni_codes

        # 7. Very new company with serial director
        start_date = data.get("registration_date", "")
        if start_date and start_date >= "2023-01-01" and serial_director_involved:
            shell_score += 0.15
            flags.append("new_with_serial_director")

        # Determine risk level
        if shell_score >= 0.5:
            risk_level = "high"
        elif shell_score >= 0.25:
            risk_level = "medium"
        else:
            risk_level = "low"

        G.nodes[node_id]["shell_score"] = shell_score
        G.nodes[node_id]["risk_level"] = risk_level

        company_result = {
            "company_id": node_id,
            "orgnr": orgnr,
            "name": name,
            "shell_score": shell_score,
            "risk_level": risk_level,
            "flags": flags,
            "indicators": indicators,
        }

        all_results.append(company_result)

        if risk_level == "high":
            high_risk.append(company_result)

    high_risk.sort(key=lambda x: x["shell_score"], reverse=True)
    all_results.sort(key=lambda x: x["shell_score"], reverse=True)

    results["high_risk_companies"] = high_risk
    results["all_results"] = all_results[:10000]  # Limit for JSON size

    # === Summary ===
    risk_distribution = defaultdict(int)
    for r in all_results:
        risk_distribution[r["risk_level"]] += 1

    results["summary"] = {
        "total_companies": len(companies),
        "total_addresses": sum(1 for _, d in G.nodes(data=True) if d.get("_type") == "Address"),
        "total_persons": sum(1 for _, d in G.nodes(data=True) if d.get("_type") == "Person"),
        "high_risk_count": len(high_risk),
        "medium_risk_count": risk_distribution.get("medium", 0),
        "low_risk_count": risk_distribution.get("low", 0),
        "suspicious_address_count": len(suspicious_addresses),
        "serial_director_count": len(serial_directors),
        "risk_distribution": dict(risk_distribution),
    }

    print(f"\nRisk distribution:")
    print(f"  - High: {len(high_risk):,}")
    print(f"  - Medium: {risk_distribution.get('medium', 0):,}")
    print(f"  - Low: {risk_distribution.get('low', 0):,}")

    return results


def generate_alerts(results: dict) -> list:
    """Generate alerts from detection results."""
    alerts = []
    now = datetime.now(timezone.utc).isoformat()

    # Shell company alerts
    for company in results["high_risk_companies"][:500]:
        alerts.append({
            "id": f"shell-{company['orgnr']}",
            "alert_type": "shell_company",
            "severity": company["risk_level"],
            "entity_id": company["company_id"],
            "entity_type": "Company",
            "description": f"Potential shell company: {company['name']} (score: {company['shell_score']:.0%})",
            "evidence": {
                "shell_score": company["shell_score"],
                "flags": company["flags"],
                "indicators": company["indicators"],
            },
            "created_at": now,
        })

    # Registration mill alerts
    for i, addr in enumerate(results["suspicious_addresses"][:100]):
        severity = "high" if addr["company_count"] >= 20 else "medium"
        alerts.append({
            "id": f"regmill-{i}",
            "alert_type": "registration_mill",
            "severity": severity,
            "entity_id": addr["address_id"],
            "entity_type": "Address",
            "description": f"Possible registration mill: {addr['company_count']} companies at {addr['street']}, {addr['city']}",
            "evidence": {
                "company_count": addr["company_count"],
                "address": {
                    "street": addr["street"],
                    "postal_code": addr["postal_code"],
                    "city": addr["city"],
                },
            },
            "created_at": now,
        })

    # Serial director alerts
    for i, director in enumerate(results["serial_directors"][:100]):
        if director["company_count"] >= 5:
            alerts.append({
                "id": f"serial-{i}",
                "alert_type": "serial_director",
                "severity": "high" if director["company_count"] >= 10 else "medium",
                "entity_id": director["person_id"],
                "entity_type": "Person",
                "description": f"Serial director: {director['name']} on {director['company_count']} boards",
                "evidence": {
                    "company_count": director["company_count"],
                    "companies": director["companies"][:10],
                },
                "created_at": now,
            })

    print(f"\nGenerated {len(alerts):,} alerts")
    return alerts


def main():
    print("=" * 70)
    print("Preparing Demo Data - Combining SCB + Bolagsverket")
    print("=" * 70)

    # Load SCB companies (all 644K)
    scb_companies = load_scb_companies()

    # Load Bolagsverket directors
    directors, bv_companies = load_bolagsverket_directors()

    # Merge data
    print("\nMerging data sources...")
    companies = merge_company_data(scb_companies, bv_companies)

    # Build graph
    print("\nBuilding graph...")
    G = build_graph(companies, directors)

    # Run detection
    print("\nRunning detection algorithms...")
    results = detect_patterns(G, companies)

    # Generate alerts
    print("\nGenerating alerts...")
    alerts = generate_alerts(results)

    # Save outputs
    print("\n" + "=" * 70)
    print("Saving outputs...")

    graph_path = DATA_DIR / "company_graph.pickle"
    with open(graph_path, "wb") as f:
        pickle.dump(G, f)
    print(f"  Saved graph to {graph_path}")

    results_path = DATA_DIR / "intelligence_results.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"  Saved results to {results_path}")

    alerts_path = DATA_DIR / "alerts.json"
    with open(alerts_path, "w") as f:
        json.dump(alerts, f, indent=2, ensure_ascii=False)
    print(f"  Saved alerts to {alerts_path}")

    print("\n" + "=" * 70)
    print("DEMO DATA READY!")
    print("=" * 70)
    print(f"\nGraph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")
    print(f"Companies: {len(companies):,}")
    print(f"Directors: {len(directors):,}")
    print(f"High-risk companies: {len(results['high_risk_companies']):,}")
    print(f"Suspicious addresses: {len(results['suspicious_addresses']):,}")
    print(f"Serial directors: {len(results['serial_directors']):,}")
    print(f"Alerts: {len(alerts):,}")
    print(f"\nTo start the demo server:")
    print(f"  python scripts/demo_server.py")


if __name__ == "__main__":
    main()
