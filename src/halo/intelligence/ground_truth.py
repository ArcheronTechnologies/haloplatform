"""
Ground Truth Data Sources for Fraud Detection Validation.

This module documents known Swedish fraud case sources and provides
placeholder data for validation testing.

IMPORTANT: Ground truth data is essential for validating fraud detection.
Without known fraud cases, we cannot measure precision/recall.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class FraudCase:
    """A known fraud case for validation."""
    orgnr: str
    company_name: str
    fraud_type: str  # tax_fraud, invoice_fraud, money_laundering, etc.
    conviction_date: Optional[date]
    source: str  # Where we found this information
    details: Optional[str] = None


# ============================================================================
# GROUND TRUTH SOURCES IN SWEDEN
# ============================================================================
#
# 1. ICIJ OFFSHORE LEAKS DATABASE (INTEGRATED)
#    - https://offshoreleaks.icij.org
#    - Downloaded: 2025-12-26 (data as of 2025-03-31)
#    - Contains: 122 Swedish entities, 2,925 Swedish officers
#    - Cross-referenced: 16 person name matches (likely false positives
#      due to common Swedish names like Anders Wall, Daniel Andersson)
#    - Offshore entities (Panama Papers, Paradise Papers, etc.) have
#      Swedish addresses but are not Swedish companies themselves
#    - Data stored in: data/icij/ and data/icij_ground_truth.json
#
# 2. EKOBROTTSMYNDIGHETEN (Swedish Economic Crime Authority)
#    - https://www.ekobrottsmyndigheten.se
#    - Publishes press releases about convictions
#    - Annual reports with aggregated statistics
#    - Does NOT publish list of convicted companies/org numbers
#
# 3. DOMSTOL.SE (Swedish Courts)
#    - https://www.domstol.se
#    - Court decisions are public record
#    - Can search by case number but not by company
#    - Need specific case references to find fraud convictions
#
# 4. BOLAGSVERKET (Swedish Companies Registration Office)
#    - https://bolagsverket.se
#    - Maintains bankruptcy/liquidation register
#    - Does NOT flag fraud-related bankruptcies specifically
#
# 5. SKATTEVERKET (Swedish Tax Agency)
#    - https://www.skatteverket.se
#    - VAT fraud cases handled here
#    - Does NOT publish list of convicted companies
#
# 6. MEDIA SOURCES
#    - Sveriges Radio (sverigesradio.se) - Ekot news
#    - Dagens Nyheter, Svenska Dagbladet, Expressen
#    - Often report major fraud cases with company names
#
# 7. ACADEMIC RESEARCH
#    - Brottsförebyggande rådet (BRÅ) - Crime prevention council
#    - University studies on Swedish fraud
#    - May have datasets for research purposes
#
# ============================================================================


# Known fraud cases from public sources
# NOTE: EBM rarely publishes company names due to Swedish privacy laws.
# See data/ebm_fraud_cases.json for case numbers and patterns.
#
# KEY EBM CASES (2024-2025):
# - B 3150-21: Falcon Funds money laundering (5yr + 1yr sentences)
# - B 1856-23: Construction labor fraud, 40M SEK (13 defendants)
# - B 10353-25: Prepaid SIM fraud enabling serious crimes
# - Unnamed: 6B SEK company broker fraud (1,100 companies sold to criminals)
# - Unnamed: 386.5M SEK laundered through 22 shell companies
# - Unnamed: 19 convicted in major Gothenburg money laundering case
#
# KEY STATISTIC FROM EBM:
# "80% of historikbolag (shell companies with history) are sold to criminals"

KNOWN_FRAUD_CASES = [
    # Falcon Funds case - only case with enough public detail
    FraudCase(
        orgnr="",  # Not disclosed
        company_name="Falcon Funds (related entities)",
        fraud_type="money_laundering",
        conviction_date=date(2024, 4, 1),
        source="EBM press release, case B 3150-21",
        details="Pension fraud scheme, 37M SEK forfeited, 5yr prison"
    ),
]


# ============================================================================
# PROXY INDICATORS FOR GROUND TRUTH
# ============================================================================
# When actual fraud convictions are unavailable, we can use proxy indicators:
#
# 1. BANKRUPTCY WITHIN 2 YEARS OF FORMATION
#    - Shell companies often formed, used, then bankrupted quickly
#    - High false positive rate but useful signal
#
# 2. TAX DEBT AT BANKRUPTCY
#    - Companies with large tax debt at konkurs likely evaded taxes
#    - Available from Kronofogden (Swedish Enforcement Authority)
#
# 3. DIRECTOR BANS (NÄRINGSFÖRBUD)
#    - Directors banned from running companies after fraud
#    - Tracked by Bolagsverket
#
# 4. AUDIT DISCLAIMER/QUALIFIED OPINION
#    - Auditor unable to verify financials
#    - Strong indicator of accounting irregularities
# ============================================================================


def get_proxy_fraud_indicators(g) -> dict:
    """
    Calculate proxy fraud indicators from graph data.

    Returns companies that match fraud-like patterns even though
    we don't have conviction data.
    """
    from datetime import date, timedelta

    companies = [n for n, d in g.nodes(data=True) if d.get("_type") == "Company"]

    # 1. Quick bankruptcies (formed and konkurs within 2 years)
    quick_bankruptcies = []
    for company_id in companies:
        data = dict(g.nodes[company_id])
        status = data.get("status", {})

        # Check if konkurs
        if status.get("code") in ("konkurs", "bankrupt"):
            formation = data.get("formation", {}).get("date")
            status_date = status.get("from")

            if formation and status_date:
                try:
                    if isinstance(formation, str):
                        formation = date.fromisoformat(formation)
                    if isinstance(status_date, str):
                        status_date = date.fromisoformat(status_date)

                    days_to_konkurs = (status_date - formation).days
                    if days_to_konkurs < 730:  # 2 years
                        quick_bankruptcies.append({
                            "company_id": company_id,
                            "company_name": data.get("names", [{}])[0].get("name", company_id),
                            "formation_date": str(formation),
                            "konkurs_date": str(status_date),
                            "days_to_konkurs": days_to_konkurs,
                        })
                except (ValueError, TypeError):
                    pass

    # 2. High shell score companies (from our detection)
    high_shell = []
    for company_id in companies:
        data = dict(g.nodes[company_id])
        shell_score = data.get("shell_score", 0)
        if shell_score >= 0.6:
            high_shell.append({
                "company_id": company_id,
                "company_name": data.get("names", [{}])[0].get("name", company_id),
                "shell_score": shell_score,
            })

    return {
        "quick_bankruptcies": quick_bankruptcies,
        "quick_bankruptcy_count": len(quick_bankruptcies),
        "high_shell_score": high_shell,
        "high_shell_count": len(high_shell),
        "note": "These are proxy indicators, not confirmed fraud cases",
    }


def validate_detection_accuracy(g, known_cases: list[FraudCase]) -> dict:
    """
    Validate our fraud detection against known cases.

    Returns precision/recall metrics if we have ground truth.
    """
    if not known_cases:
        return {
            "status": "no_ground_truth",
            "message": "Cannot calculate precision/recall without known fraud cases",
            "recommendation": "Collect confirmed fraud cases from Ekobrottsmyndigheten, "
                              "court records, or media reports",
        }

    # Get our high-risk detections
    detected_high_risk = set()
    for n, d in g.nodes(data=True):
        if d.get("_type") == "Company" and d.get("shell_score", 0) >= 0.6:
            # Try to extract org number from ID
            orgnr = n.replace("company-", "")
            detected_high_risk.add(orgnr)

    known_frauds = set(case.orgnr for case in known_cases)

    # Calculate metrics
    true_positives = detected_high_risk & known_frauds
    false_positives = detected_high_risk - known_frauds
    false_negatives = known_frauds - detected_high_risk

    precision = len(true_positives) / len(detected_high_risk) if detected_high_risk else 0
    recall = len(true_positives) / len(known_frauds) if known_frauds else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

    return {
        "status": "calculated",
        "true_positives": len(true_positives),
        "false_positives": len(false_positives),
        "false_negatives": len(false_negatives),
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
        "detected_count": len(detected_high_risk),
        "known_fraud_count": len(known_frauds),
    }
