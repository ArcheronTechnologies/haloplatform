#!/usr/bin/env python3
"""
Run shell company scoring on all companies in the graph.

This calculates shell_score for each company based on:
- No employees
- Generic SNI code
- Recently formed (< 2 years)
- F-skatt but no VAT
- Single director

Updates the graph pickle with shell_score values.
"""

import json
import pickle
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

GRAPH_PATH = Path("data/company_graph.pickle")
OUTPUT_PATH = Path("data/shell_scoring_results.json")

# Generic SNI codes (management consulting, financial services, real estate, etc.)
GENERIC_SNI_CODES = {"64", "66", "68", "70", "82"}


@dataclass
class ShellScoreResult:
    """Shell scoring result for a company."""
    company_id: str
    company_name: str
    shell_score: float
    indicators: dict
    severity: str  # low, medium, high


def load_graph():
    """Load the company graph."""
    with open(GRAPH_PATH, "rb") as f:
        return pickle.load(f)


def save_graph(g):
    """Save the updated graph."""
    with open(GRAPH_PATH, "wb") as f:
        pickle.dump(g, f)


def get_director_count(g, company_id: str) -> int:
    """Count directors for a company."""
    count = 0
    for u, v, data in g.edges(data=True):
        if v == company_id and data.get("_type") == "DirectsEdge":
            count += 1
    return count


def calculate_shell_score(g, company_id: str) -> ShellScoreResult:
    """Calculate shell score for a company."""
    if company_id not in g.nodes:
        return ShellScoreResult(
            company_id=company_id,
            company_name="Unknown",
            shell_score=0.0,
            indicators={},
            severity="low"
        )

    data = dict(g.nodes[company_id])
    names = data.get("names", [{}])
    company_name = names[0].get("name", company_id) if names else company_id

    indicators = {}

    # 1. No employees
    employees = data.get("employees") or {}
    emp_count = employees.get("count", 0) if isinstance(employees, dict) else 0
    indicators["no_employees"] = emp_count == 0

    # 2. Generic SNI code
    sni_codes = data.get("sni_codes", [])
    sni_2digit = ""
    if sni_codes:
        first_sni = sni_codes[0]
        sni_2digit = str(first_sni.get("kod", first_sni.get("code", "")))[:2]
    indicators["generic_sni"] = sni_2digit in GENERIC_SNI_CODES

    # 3. Recently formed (< 2 years)
    formation_date = data.get("formation", {}).get("date") or data.get("registration_date")
    age_days = None
    if formation_date:
        try:
            if isinstance(formation_date, str):
                formation_date = date.fromisoformat(formation_date)
            age_days = (date.today() - formation_date).days
            indicators["recently_formed"] = age_days < 730  # 2 years
        except (ValueError, TypeError):
            indicators["recently_formed"] = False
    else:
        indicators["recently_formed"] = False

    # 4. F-skatt but no VAT (potential invoice fraud setup)
    f_skatt = data.get("f_skatt") or {}
    moms = data.get("moms") or {}
    has_f_skatt = f_skatt.get("registered", False)
    has_vat = moms.get("registered", False)
    indicators["f_skatt_no_vat"] = has_f_skatt and not has_vat

    # 5. Single director
    director_count = get_director_count(g, company_id)
    indicators["single_director"] = director_count == 1

    # 6. No revenue (if data available)
    revenue = data.get("revenue")
    if revenue is not None:
        indicators["no_revenue"] = revenue == 0
    else:
        # Don't count as indicator if data not available
        indicators["no_revenue"] = False

    # Calculate weighted shell score
    # Weights based on signal strength
    weights = {
        "no_employees": 0.15,
        "generic_sni": 0.20,
        "recently_formed": 0.15,
        "f_skatt_no_vat": 0.25,  # Strong indicator
        "single_director": 0.10,  # Common, low weight
        "no_revenue": 0.15,
    }

    shell_score = sum(
        weights[k] for k, v in indicators.items() if v
    )

    # Determine severity
    if shell_score >= 0.6:
        severity = "high"
    elif shell_score >= 0.4:
        severity = "medium"
    else:
        severity = "low"

    return ShellScoreResult(
        company_id=company_id,
        company_name=company_name,
        shell_score=shell_score,
        indicators=indicators,
        severity=severity
    )


def main():
    print("=" * 60)
    print("SHELL COMPANY SCORING")
    print("=" * 60)

    if not GRAPH_PATH.exists():
        print(f"Error: Graph not found at {GRAPH_PATH}")
        return 1

    g = load_graph()
    companies = [n for n, d in g.nodes(data=True) if d.get("_type") == "Company"]
    print(f"Loaded graph: {len(companies)} companies")

    # Score all companies
    print("\nScoring companies...")
    results = []
    severity_counts = Counter()
    indicator_counts = Counter()

    for i, company_id in enumerate(companies):
        result = calculate_shell_score(g, company_id)
        results.append(result)

        # Update graph node with shell_score
        g.nodes[company_id]["shell_score"] = result.shell_score

        severity_counts[result.severity] += 1
        for indicator, value in result.indicators.items():
            if value:
                indicator_counts[indicator] += 1

        if (i + 1) % 1000 == 0:
            print(f"  Processed {i + 1}/{len(companies)}")

    # Save updated graph
    print("\nSaving updated graph...")
    save_graph(g)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    print("\nSeverity distribution:")
    for severity in ["high", "medium", "low"]:
        count = severity_counts[severity]
        pct = 100 * count / len(companies)
        print(f"  {severity}: {count:,} ({pct:.1f}%)")

    print("\nIndicator prevalence:")
    for indicator, count in indicator_counts.most_common():
        pct = 100 * count / len(companies)
        print(f"  {indicator}: {count:,} ({pct:.1f}%)")

    # Top high-risk companies
    high_risk = [r for r in results if r.severity == "high"]
    high_risk.sort(key=lambda x: -x.shell_score)

    print(f"\nTop 20 highest shell scores:")
    for r in high_risk[:20]:
        indicators_str = ", ".join(k for k, v in r.indicators.items() if v)
        print(f"  {r.shell_score:.2f}: {r.company_name[:40]} [{indicators_str}]")

    # Expected flag rates (addressing the 14% concern)
    print("\n" + "=" * 60)
    print("FLAG RATE ANALYSIS")
    print("=" * 60)

    # Single indicator combinations
    single_director_count = indicator_counts.get("single_director", 0)
    generic_sni_count = indicator_counts.get("generic_sni", 0)

    print(f"\nSingle indicators:")
    print(f"  single_director: {single_director_count:,} ({100*single_director_count/len(companies):.1f}%)")
    print(f"  generic_sni: {generic_sni_count:,} ({100*generic_sni_count/len(companies):.1f}%)")

    # Count companies with both
    both_count = sum(
        1 for r in results
        if r.indicators.get("single_director") and r.indicators.get("generic_sni")
    )
    print(f"\n  BOTH single_director AND generic_sni: {both_count:,} ({100*both_count/len(companies):.1f}%)")
    print(f"  (This would be flagged if using only these two indicators)")

    # Actual high severity (shell_score >= 0.6)
    print(f"\n  Actual high severity (score >= 0.6): {severity_counts['high']:,} ({100*severity_counts['high']/len(companies):.1f}%)")
    print(f"  (Using weighted multi-factor scoring)")

    # Save detailed results
    output = {
        "analysis_date": datetime.now(timezone.utc).isoformat(),
        "total_companies": len(companies),
        "severity_distribution": dict(severity_counts),
        "indicator_prevalence": dict(indicator_counts),
        "high_risk_companies": [
            {
                "company_id": r.company_id,
                "company_name": r.company_name,
                "shell_score": r.shell_score,
                "indicators": r.indicators,
            }
            for r in high_risk[:100]
        ],
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nSaved detailed results to {OUTPUT_PATH}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
