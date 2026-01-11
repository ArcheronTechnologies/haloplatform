"""
Cross-domain correlation engine.

Correlates entities and relationships across different data domains:
- Corporate (companies, directors, ownership)
- Property (real estate, vehicles)
- Welfare (benefit claims, employment)
- Financial (transactions, accounts)
- Physical (addresses, locations)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class Domain(str, Enum):
    """Data domains for correlation."""

    CORPORATE = "corporate"
    PROPERTY = "property"
    WELFARE = "welfare"
    FINANCIAL = "financial"
    PHYSICAL = "physical"


class CorrelationType(str, Enum):
    """Types of correlations between domains."""

    DIRECT = "direct"  # Same entity appears in multiple domains
    INDIRECT = "indirect"  # Entities linked through relationships
    TEMPORAL = "temporal"  # Events coincide in time
    GEOGRAPHIC = "geographic"  # Entities share location
    NETWORK = "network"  # Entities connected through network


@dataclass
class DomainCorrelation:
    """A correlation between entities across domains."""

    source_domain: Domain
    target_domain: Domain
    source_entity_id: UUID
    target_entity_id: UUID
    correlation_type: CorrelationType
    strength: float  # 0.0 to 1.0
    description: str
    evidence: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source_domain": self.source_domain.value,
            "target_domain": self.target_domain.value,
            "source_entity_id": str(self.source_entity_id),
            "target_entity_id": str(self.target_entity_id),
            "correlation_type": self.correlation_type.value,
            "strength": self.strength,
            "description": self.description,
            "evidence": self.evidence,
            "metadata": self.metadata,
        }


@dataclass
class CorrelationResult:
    """Result of a cross-domain correlation analysis."""

    entity_id: UUID
    analyzed_at: datetime
    domains_found: list[Domain]
    correlations: list[DomainCorrelation]
    risk_indicators: list[str] = field(default_factory=list)
    total_strength: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "entity_id": str(self.entity_id),
            "analyzed_at": self.analyzed_at.isoformat(),
            "domains_found": [d.value for d in self.domains_found],
            "correlations": [c.to_dict() for c in self.correlations],
            "risk_indicators": self.risk_indicators,
            "total_strength": self.total_strength,
        }


class FusionEngine:
    """
    Cross-domain intelligence fusion engine.

    Correlates entities and patterns across different data domains
    to identify complex organized crime networks.
    """

    def __init__(self):
        self._domain_adapters: dict[Domain, Any] = {}
        self._correlation_rules: list[callable] = []

    def register_domain_adapter(self, domain: Domain, adapter: Any) -> None:
        """
        Register a data adapter for a domain.

        Args:
            domain: The data domain
            adapter: Adapter for accessing domain data
        """
        self._domain_adapters[domain] = adapter
        logger.info(f"Registered adapter for domain: {domain.value}")

    def add_correlation_rule(self, rule: callable) -> None:
        """
        Add a custom correlation rule.

        Args:
            rule: Callable that takes two entities and returns correlation strength
        """
        self._correlation_rules.append(rule)

    def correlate_entity(
        self,
        entity_id: UUID,
        domains: Optional[list[Domain]] = None,
    ) -> CorrelationResult:
        """
        Find correlations for an entity across domains.

        Args:
            entity_id: Entity to analyze
            domains: Domains to search (defaults to all)

        Returns:
            Correlation analysis result
        """
        domains = domains or list(Domain)
        correlations: list[DomainCorrelation] = []
        domains_found: list[Domain] = []
        risk_indicators: list[str] = []

        # Check each domain for entity presence
        for domain in domains:
            adapter = self._domain_adapters.get(domain)
            if not adapter:
                continue

            # Look for entity in domain
            # This is a placeholder - real implementation would query adapters
            entity_data = self._find_entity_in_domain(entity_id, domain, adapter)
            if entity_data:
                domains_found.append(domain)

        # Find cross-domain correlations
        for i, domain1 in enumerate(domains_found):
            for domain2 in domains_found[i + 1:]:
                correlation = self._correlate_domains(
                    entity_id, domain1, domain2
                )
                if correlation:
                    correlations.append(correlation)

        # Apply custom correlation rules
        for rule in self._correlation_rules:
            try:
                additional = rule(entity_id, domains_found)
                if additional:
                    correlations.extend(additional)
            except Exception as e:
                logger.warning(f"Correlation rule failed: {e}")

        # Calculate risk indicators
        risk_indicators = self._calculate_risk_indicators(
            entity_id, domains_found, correlations
        )

        # Calculate total strength
        total_strength = (
            sum(c.strength for c in correlations) / len(correlations)
            if correlations
            else 0.0
        )

        return CorrelationResult(
            entity_id=entity_id,
            analyzed_at=datetime.utcnow(),
            domains_found=domains_found,
            correlations=correlations,
            risk_indicators=risk_indicators,
            total_strength=total_strength,
        )

    def find_network_correlations(
        self,
        entity_ids: list[UUID],
        max_depth: int = 2,
    ) -> list[CorrelationResult]:
        """
        Find correlations across a network of entities.

        Args:
            entity_ids: Entities to analyze
            max_depth: Maximum relationship depth

        Returns:
            List of correlation results
        """
        results = []
        analyzed = set()

        def analyze_entity(eid: UUID, depth: int):
            if eid in analyzed or depth > max_depth:
                return
            analyzed.add(eid)

            result = self.correlate_entity(eid)
            results.append(result)

            # Find related entities and analyze them
            for correlation in result.correlations:
                if correlation.target_entity_id not in analyzed:
                    analyze_entity(correlation.target_entity_id, depth + 1)

        for entity_id in entity_ids:
            analyze_entity(entity_id, 0)

        return results

    def _find_entity_in_domain(
        self,
        entity_id: UUID,
        domain: Domain,
        adapter: Any,
    ) -> Optional[dict]:
        """Find an entity in a specific domain."""
        # Placeholder - real implementation would query the adapter
        return None

    def _correlate_domains(
        self,
        entity_id: UUID,
        domain1: Domain,
        domain2: Domain,
    ) -> Optional[DomainCorrelation]:
        """Find correlation between an entity's presence in two domains."""
        # Placeholder - real implementation would analyze domain data
        return None

    def _calculate_risk_indicators(
        self,
        entity_id: UUID,
        domains: list[Domain],
        correlations: list[DomainCorrelation],
    ) -> list[str]:
        """Calculate risk indicators based on correlations."""
        indicators = []

        # Multiple domain presence is a risk indicator
        if len(domains) >= 3:
            indicators.append(f"Entity present in {len(domains)} domains")

        # Strong correlations indicate organized activity
        strong_correlations = [c for c in correlations if c.strength > 0.8]
        if strong_correlations:
            indicators.append(
                f"{len(strong_correlations)} strong cross-domain correlations"
            )

        # Specific domain combinations are higher risk
        domain_set = set(domains)
        if Domain.CORPORATE in domain_set and Domain.WELFARE in domain_set:
            indicators.append("Corporate-Welfare correlation (potential fraud)")

        if Domain.FINANCIAL in domain_set and Domain.PHYSICAL in domain_set:
            indicators.append("Financial-Physical correlation (money movement)")

        return indicators
