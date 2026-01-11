"""
Counter-Intelligence Detection.

Detect deliberate structuring to avoid detection.
The ABSENCE of expected patterns is itself a signal.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from halo.graph.client import GraphClient


@dataclass
class EvasionScore:
    """Result of evasion detection analysis."""
    entity_id: str
    entity_type: str

    # Isolation score (0-1, higher = more isolated than normal)
    isolation_score: float = 0.0

    # Synthetic compliance indicators
    synthetic_compliance: bool = False
    compliance_details: dict = field(default_factory=dict)

    # Structuring indicators
    structuring_detected: bool = False
    structuring_patterns: list[str] = field(default_factory=list)

    # Overall evasion assessment
    evasion_probability: float = 0.0
    evasion_level: str = "low"  # low, medium, high
    rationale: str = ""

    computed_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "isolation_score": self.isolation_score,
            "synthetic_compliance": self.synthetic_compliance,
            "compliance_details": self.compliance_details,
            "structuring_detected": self.structuring_detected,
            "structuring_patterns": self.structuring_patterns,
            "evasion_probability": self.evasion_probability,
            "evasion_level": self.evasion_level,
            "rationale": self.rationale,
            "computed_at": self.computed_at.isoformat(),
        }


class EvasionDetector:
    """
    Detect deliberate structuring to avoid detection.

    Key insight: The ABSENCE of expected patterns is itself a signal.
    Fraud networks try to appear isolated and compliant, which is
    different from how real businesses behave.
    """

    def __init__(self, graph_client: Optional[GraphClient] = None):
        self.graph = graph_client

    async def analyze(self, entity_id: str) -> EvasionScore:
        """
        Analyze entity for evasion tactics.
        """
        entity_data = await self._get_entity_data(entity_id)
        entity_type = entity_data.get("_type", "Company")

        # Calculate isolation score
        isolation = await self._score_isolation(entity_id, entity_data)

        # Check for synthetic compliance
        synthetic, compliance_details = await self._detect_synthetic_compliance(
            entity_id, entity_data
        )

        # Check for structuring patterns
        structuring, patterns = await self._detect_structuring(entity_id, entity_data)

        # Calculate overall evasion probability
        evasion_prob = self._calculate_evasion_probability(
            isolation, synthetic, structuring
        )

        # Determine level and rationale
        if evasion_prob > 0.7:
            level = "high"
            rationale = "Strong indicators of deliberate detection evasion"
        elif evasion_prob > 0.4:
            level = "medium"
            rationale = "Some evasion indicators present"
        else:
            level = "low"
            rationale = "No significant evasion indicators"

        return EvasionScore(
            entity_id=entity_id,
            entity_type=entity_type,
            isolation_score=isolation,
            synthetic_compliance=synthetic,
            compliance_details=compliance_details,
            structuring_detected=structuring,
            structuring_patterns=patterns,
            evasion_probability=evasion_prob,
            evasion_level=level,
            rationale=rationale
        )

    async def _score_isolation(
        self,
        entity_id: str,
        entity_data: dict
    ) -> float:
        """
        Fraud networks try to appear isolated. Real businesses connect.

        Measures how "isolated" an entity is compared to expectations.
        """
        isolation_factors = []

        # 1. Check director connections
        # Real directors usually have other roles, history
        if entity_data.get("_type") == "Company":
            directors = await self._get_directors(entity_id)
            isolated_directors = 0

            for director in directors:
                director_id = director.get("id")
                if director_id:
                    # Check if director has other roles
                    role_count = await self._get_directorship_count(director_id)
                    history = await self._get_historical_roles(director_id)

                    if role_count == 1 and len(history) == 0:
                        isolated_directors += 1

            if directors:
                isolation_factors.append(isolated_directors / len(directors))
            else:
                isolation_factors.append(1.0)  # No directors is suspicious

        # 2. Check address connections
        # Real companies share addresses with related businesses sometimes
        address_connections = await self._get_address_colocated_companies(entity_id)
        if not address_connections:
            isolation_factors.append(0.5)  # Slight signal
        else:
            # Having some colocated companies is normal
            isolation_factors.append(0.0)

        # 3. Check inferred business relationships
        # Real companies have suppliers/customers visible in data
        relationships = await self._get_inferred_business_relationships(entity_id)
        if not relationships:
            isolation_factors.append(0.3)  # Some companies are legitimately standalone
        else:
            isolation_factors.append(0.0)

        # 4. Check for unusually clean network
        # Real networks have some noise/complexity
        if self.graph:
            neighbors = await self.graph.backend.get_neighbors(entity_id)
            if len(neighbors) == 0:
                isolation_factors.append(1.0)
            elif len(neighbors) < 3:
                isolation_factors.append(0.5)
            else:
                isolation_factors.append(0.0)

        if isolation_factors:
            return sum(isolation_factors) / len(isolation_factors)
        return 0.0

    async def _detect_synthetic_compliance(
        self,
        entity_id: str,
        entity_data: dict
    ) -> tuple[bool, dict]:
        """
        Real companies are occasionally late on filings.
        Perfect compliance can indicate a front company.
        """
        details = {
            "on_time_rate": 0.0,
            "has_minimal_activity": False,
            "filing_count": 0,
            "suspicious": False,
            "rationale": ""
        }

        # Get filing history
        filings = await self._get_filing_history(entity_id)

        if not filings or len(filings) < 3:
            # Not enough history to analyze
            return False, details

        details["filing_count"] = len(filings)

        # Calculate on-time rate
        on_time = sum(1 for f in filings if f.get("on_time", False))
        on_time_rate = on_time / len(filings)
        details["on_time_rate"] = on_time_rate

        # Check for minimal activity
        has_minimal_activity = await self._has_minimal_activity(entity_id, entity_data)
        details["has_minimal_activity"] = has_minimal_activity

        # Perfect on-time rate + no activity + long history = suspicious
        suspicious = (
            on_time_rate == 1.0 and
            has_minimal_activity and
            len(filings) > 5
        )

        details["suspicious"] = suspicious
        if suspicious:
            details["rationale"] = (
                "Perfect filing compliance with minimal business activity "
                "suggests maintained shell company"
            )

        return suspicious, details

    async def _detect_structuring(
        self,
        entity_id: str,
        entity_data: dict
    ) -> tuple[bool, list[str]]:
        """
        Detect deliberate structuring to avoid thresholds/detection.
        """
        patterns = []

        # 1. Just-below-threshold transactions
        # Common in money laundering to avoid reporting
        transactions = await self._get_transactions(entity_id)
        if transactions:
            # Swedish reporting threshold is 150,000 SEK
            threshold = 150000
            just_below = sum(
                1 for t in transactions
                if threshold * 0.85 < t.get("amount", 0) < threshold
            )
            if len(transactions) > 5 and just_below > len(transactions) * 0.3:
                patterns.append("Multiple transactions just below reporting threshold")

        # 2. Round-trip transactions
        # Money going out and coming back from related parties
        round_trips = await self._detect_round_trip_transactions(entity_id)
        if round_trips:
            patterns.append("Potential round-trip transactions detected")

        # 3. Ownership just below beneficial owner threshold
        # Sweden: 25% triggers beneficial owner disclosure
        ownership = entity_data.get("owners", [])
        for owner in ownership:
            share = owner.get("share", 0)
            if 20 <= share < 25:  # Suspiciously close to threshold
                patterns.append(f"Ownership structured at {share}% (just below 25% disclosure)")

        # 4. Multiple small entities instead of one large one
        # Common structuring to avoid scrutiny
        related_entities = await self._get_related_entities(entity_id)
        if len(related_entities) > 3:
            similar_count = sum(
                1 for e in related_entities
                if self._are_similar_businesses(entity_data, e)
            )
            if similar_count > 2:
                patterns.append("Multiple similar entities (potential structuring)")

        # 5. Timing patterns
        # Activity concentrated in specific patterns to avoid detection
        activity_timing = await self._analyze_activity_timing(entity_id)
        if activity_timing.get("suspicious_pattern"):
            patterns.append(activity_timing.get("pattern_description", "Suspicious timing pattern"))

        return len(patterns) > 0, patterns

    def _calculate_evasion_probability(
        self,
        isolation: float,
        synthetic: bool,
        structuring: bool
    ) -> float:
        """
        Calculate overall evasion probability.
        """
        score = 0.0

        # Isolation contributes up to 40%
        score += isolation * 0.4

        # Synthetic compliance contributes 30%
        if synthetic:
            score += 0.3

        # Structuring contributes 30%
        if structuring:
            score += 0.3

        return min(score, 1.0)

    # Helper methods

    async def _get_entity_data(self, entity_id: str) -> dict:
        """Get entity data."""
        if self.graph:
            company = await self.graph.get_company(entity_id)
            if company:
                return company
            person = await self.graph.get_person(entity_id)
            if person:
                return person
        return {"id": entity_id}

    async def _get_directors(self, company_id: str) -> list[dict]:
        """Get directors of a company."""
        if self.graph:
            neighbors = await self.graph.backend.get_neighbors(
                company_id,
                edge_types=["DirectsEdge"],
                direction="in"
            )
            return [n["m"] for n in neighbors if n["m"].get("_type") == "Person"]
        return []

    async def _get_directorship_count(self, person_id: str) -> int:
        """Get number of directorships."""
        if self.graph:
            directorships = await self.graph.get_directorships(person_id)
            return len(directorships)
        return 0

    async def _get_historical_roles(self, person_id: str) -> list[dict]:
        """Get historical roles for a person."""
        # Would query for ended directorships
        return []

    async def _get_address_colocated_companies(self, entity_id: str) -> list[dict]:
        """Get companies at same address."""
        if self.graph:
            entity = await self._get_entity_data(entity_id)
            addresses = entity.get("addresses", [])
            colocated = []
            for addr in addresses:
                addr_id = addr.get("address_id")
                if addr_id:
                    companies = await self.graph.get_companies_at_address(addr_id)
                    colocated.extend([c for c in companies if c.get("id") != entity_id])
            return colocated
        return []

    async def _get_inferred_business_relationships(self, entity_id: str) -> list[dict]:
        """Get inferred business relationships."""
        # Would analyze transactions, shared directors, etc.
        return []

    async def _get_filing_history(self, entity_id: str) -> list[dict]:
        """Get filing history for entity."""
        # Would query for annual reports, tax filings, etc.
        return []

    async def _has_minimal_activity(self, entity_id: str, entity_data: dict) -> bool:
        """Check if company has minimal activity."""
        # Check for employees
        employees = entity_data.get("employees", {})
        if employees.get("count", 0) > 0:
            return False

        # Check for revenue
        revenue = entity_data.get("revenue", {})
        if revenue.get("amount", 0) > 100000:  # More than 100k SEK
            return False

        # Check for transactions
        transactions = await self._get_transactions(entity_id)
        if len(transactions) > 10:  # Significant transaction volume
            return False

        return True

    async def _get_transactions(self, entity_id: str) -> list[dict]:
        """Get transactions for entity."""
        # Would query transaction data
        return []

    async def _detect_round_trip_transactions(self, entity_id: str) -> list[dict]:
        """Detect round-trip transactions."""
        # Would analyze transaction patterns
        return []

    async def _get_related_entities(self, entity_id: str) -> list[dict]:
        """Get entities related through ownership/directors."""
        if self.graph:
            network = await self.graph.expand_network([entity_id], hops=2)
            return list(network.get("nodes", {}).values())
        return []

    def _are_similar_businesses(self, entity1: dict, entity2: dict) -> bool:
        """Check if two businesses are suspiciously similar."""
        # Same SNI code
        sni1 = entity1.get("sni_codes", [{}])[0].get("code", "")[:2] if entity1.get("sni_codes") else ""
        sni2 = entity2.get("sni_codes", [{}])[0].get("code", "")[:2] if entity2.get("sni_codes") else ""
        if sni1 and sni1 == sni2:
            return True

        # Similar names
        name1 = entity1.get("display_name", "").lower()
        name2 = entity2.get("display_name", "").lower()
        if name1 and name2:
            # Simple similarity check
            words1 = set(name1.split())
            words2 = set(name2.split())
            overlap = len(words1 & words2)
            if overlap >= 2:
                return True

        return False

    async def _analyze_activity_timing(self, entity_id: str) -> dict:
        """Analyze timing patterns of activity."""
        # Would analyze when transactions/events occur
        return {"suspicious_pattern": False}
