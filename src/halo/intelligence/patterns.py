"""
Layer 2: Pattern-Based Fraud Detection.

Encoded knowledge of how fraud works - graph pattern matching
for known fraud typologies.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

from halo.graph.client import GraphClient


@dataclass
class FraudPattern:
    """
    Definition of a fraud pattern with its detection query.
    """
    id: str
    name: str
    description: str
    severity: str  # low, medium, high, critical
    typology: str  # shell_company, money_laundering, tax_fraud, phoenix, etc.
    query: str  # Cypher query
    extractor: Callable[[dict], dict]  # function to extract match data
    enabled: bool = True


@dataclass
class PatternMatch:
    """Result of a pattern match."""
    pattern_id: str
    pattern_name: str
    severity: str
    typology: str
    match_data: dict
    detected_at: datetime = field(default_factory=datetime.utcnow)
    entity_ids: list[str] = field(default_factory=list)

    def to_alert(self) -> dict:
        """Convert to alert format."""
        return {
            "alert_type": "pattern_match",
            "pattern_type": self.pattern_id,
            "severity": self.severity,
            "title": self.pattern_name,
            "description": f"Pattern detected: {self.pattern_name}",
            "entity_ids": self.entity_ids,
            "metadata": self.match_data,
            "created_at": self.detected_at.isoformat(),
        }


# Pattern library with Cypher queries
FRAUD_PATTERNS: dict[str, FraudPattern] = {
    "registration_mill": FraudPattern(
        id="registration_mill",
        name="Registration Mill",
        description="Address used to register multiple shell companies with shared directors",
        severity="high",
        typology="shell_company_network",
        query="""
            MATCH (a:Address)<-[:REGISTERED_AT]-(c:Company)
            WITH a, collect(c) as companies, count(c) as cnt
            WHERE cnt > 5
            MATCH (p:Person)-[:DIRECTS]->(c1:Company)-[:REGISTERED_AT]->(a)
            MATCH (p)-[:DIRECTS]->(c2:Company)-[:REGISTERED_AT]->(a)
            WHERE c1 <> c2
            RETURN a as address, companies, collect(DISTINCT p) as shared_directors, cnt as company_count
        """,
        extractor=lambda row: {
            "address": row.get("address", {}),
            "company_count": row.get("company_count", 0),
            "companies": row.get("companies", []),
            "shared_directors": row.get("shared_directors", [])
        }
    ),

    "phoenix": FraudPattern(
        id="phoenix",
        name="Phoenix Company",
        description="Directors of failed company immediately start new one in same industry",
        severity="medium",
        typology="corporate_fraud",
        query="""
            MATCH (old:Company)<-[:DIRECTS]-(p:Person)
            WHERE old.status.code IN ['dissolved', 'bankrupt', 'konkurs', 'avregistrerad']
            MATCH (p)-[:DIRECTS]->(new:Company)
            WHERE new.formation.date > old.status.from
            AND new.formation.date < old.status.from + duration('P90D')
            RETURN old as old_company, new as new_company, p as director
        """,
        extractor=lambda row: {
            "old_company": row.get("old_company", {}),
            "new_company": row.get("new_company", {}),
            "director": row.get("director", {})
        }
    ),

    "circular_ownership": FraudPattern(
        id="circular_ownership",
        name="Circular Ownership",
        description="Ownership loops that hide beneficial ownership",
        severity="high",
        typology="money_laundering",
        query="""
            MATCH path = (c:Company)-[:OWNS*2..6]->(c)
            RETURN c as company, path, length(path) as loop_length
        """,
        extractor=lambda row: {
            "company": row.get("company", {}),
            "loop_path": row.get("path"),
            "loop_length": row.get("loop_length", 0)
        }
    ),

    "invoice_factory": FraudPattern(
        id="invoice_factory",
        name="Invoice Factory Setup",
        description="Company structured for fake invoice generation",
        severity="high",
        typology="tax_fraud",
        query="""
            MATCH (c:Company)-[:REGISTERED_AT]->(a:Address)
            WHERE c.f_skatt.registered = true
            AND (c.vat.registered = false OR c.vat IS NULL)
            AND (c.employees.count = 0 OR c.employees IS NULL)
            AND c.formation.date > date() - duration('P12M')
            AND a.type = 'virtual'
            RETURN c as company, a as address
        """,
        extractor=lambda row: {
            "company": row.get("company", {}),
            "address": row.get("address", {})
        }
    ),

    "layered_ownership": FraudPattern(
        id="layered_ownership",
        name="Layered Ownership Structure",
        description="Deep ownership chains hiding beneficial owner",
        severity="medium",
        typology="money_laundering",
        query="""
            MATCH path = (p:Person)-[:OWNS*4..]->(target:Company)
            WHERE ALL(r IN relationships(path) WHERE r.share > 50)
            RETURN p as beneficial_owner, target as target_company,
                   length(path) as layers, nodes(path) as chain
        """,
        extractor=lambda row: {
            "beneficial_owner": row.get("beneficial_owner", {}),
            "target_company": row.get("target_company", {}),
            "layers": row.get("layers", 0),
            "ownership_chain": row.get("chain", [])
        }
    ),

    "dormant_reactivation": FraudPattern(
        id="dormant_reactivation",
        name="Dormant Company Reactivation",
        description="Long-dormant company suddenly becomes active (shelf company)",
        severity="medium",
        typology="shell_company_network",
        query="""
            MATCH (c:Company)
            WHERE c.status.code = 'active'
            AND c.previous_status.code = 'dormant'
            AND c.previous_status.duration > duration('P2Y')
            AND c.status.from > date() - duration('P6M')
            RETURN c as company
        """,
        extractor=lambda row: {"company": row.get("company", {})}
    ),

    "rapid_director_rotation": FraudPattern(
        id="rapid_director_rotation",
        name="Rapid Director Rotation",
        description="Company with unusually high director turnover",
        severity="medium",
        typology="shell_company_network",
        query="""
            MATCH (c:Company)<-[d:DIRECTS]-(p:Person)
            WITH c, count(d) as total_directorships,
                 sum(CASE WHEN d.to_date IS NOT NULL THEN 1 ELSE 0 END) as ended
            WHERE total_directorships > 3 AND ended > 2
            AND (ended * 1.0 / total_directorships) > 0.5
            RETURN c as company, total_directorships, ended
        """,
        extractor=lambda row: {
            "company": row.get("company", {}),
            "total_directorships": row.get("total_directorships", 0),
            "ended_directorships": row.get("ended", 0)
        }
    ),

    "nominee_director_network": FraudPattern(
        id="nominee_director_network",
        name="Nominee Director Network",
        description="Person directing many unrelated companies (professional nominee)",
        severity="medium",
        typology="shell_company_network",
        query="""
            MATCH (p:Person)-[:DIRECTS]->(c:Company)
            WITH p, collect(c) as companies, count(c) as company_count
            WHERE company_count > 5
            AND ALL(c1 IN companies, c2 IN companies
                    WHERE c1 = c2 OR NOT EXISTS((c1)-[:CO_REGISTERED]-(c2)))
            RETURN p as person, companies, company_count
        """,
        extractor=lambda row: {
            "person": row.get("person", {}),
            "companies": row.get("companies", []),
            "company_count": row.get("company_count", 0)
        }
    ),

    "address_hopping": FraudPattern(
        id="address_hopping",
        name="Address Hopping",
        description="Company frequently changing registered address",
        severity="low",
        typology="evasion",
        query="""
            MATCH (c:Company)-[r:REGISTERED_AT]->(a:Address)
            WITH c, count(r) as address_count
            WHERE address_count > 3
            MATCH (c)-[r:REGISTERED_AT]->(a:Address)
            WITH c, address_count, collect({address: a, from: r.from_date, to: r.to_date}) as addresses
            RETURN c as company, address_count, addresses
        """,
        extractor=lambda row: {
            "company": row.get("company", {}),
            "address_count": row.get("address_count", 0),
            "addresses": row.get("addresses", [])
        }
    ),

    "cross_border_layering": FraudPattern(
        id="cross_border_layering",
        name="Cross-Border Layering",
        description="Swedish company owned through foreign entities",
        severity="medium",
        typology="money_laundering",
        query="""
            MATCH path = (foreign:Company)-[:OWNS*1..3]->(swedish:Company)
            WHERE foreign.jurisdiction <> 'SE'
            AND swedish.jurisdiction = 'SE'
            RETURN swedish as company, foreign as foreign_owner,
                   length(path) as layers, path
        """,
        extractor=lambda row: {
            "company": row.get("company", {}),
            "foreign_owner": row.get("foreign_owner", {}),
            "layers": row.get("layers", 0)
        }
    ),
}


class PatternMatcher:
    """
    Pattern matching engine for fraud detection.

    Runs Cypher queries against the graph database to find fraud patterns.
    """

    def __init__(self, graph_client: GraphClient):
        self.graph = graph_client
        self.patterns = FRAUD_PATTERNS

    async def run_all_patterns(self) -> list[PatternMatch]:
        """
        Run all enabled fraud patterns and return matches.
        """
        all_matches = []

        for pattern_id, pattern in self.patterns.items():
            if not pattern.enabled:
                continue

            try:
                matches = await self.run_pattern(pattern)
                all_matches.extend(matches)
            except Exception as e:
                # Log but continue with other patterns
                import logging
                logging.error(f"Error running pattern {pattern_id}: {e}")

        return all_matches

    async def run_pattern(self, pattern: FraudPattern) -> list[PatternMatch]:
        """
        Run a single pattern and return matches.
        """
        results = await self.graph.execute_cypher(pattern.query)
        matches = []

        for row in results:
            match_data = pattern.extractor(row)

            # Extract entity IDs from match data
            entity_ids = self._extract_entity_ids(match_data)

            match = PatternMatch(
                pattern_id=pattern.id,
                pattern_name=pattern.name,
                severity=pattern.severity,
                typology=pattern.typology,
                match_data=match_data,
                entity_ids=entity_ids
            )
            matches.append(match)

        return matches

    async def check_entity(
        self,
        entity_id: str,
        entity_type: str
    ) -> list[PatternMatch]:
        """
        Check if a specific entity matches any fraud patterns.

        Modifies queries to filter by the given entity.
        """
        matches = []

        for pattern_id, pattern in self.patterns.items():
            if not pattern.enabled:
                continue

            # Add entity filter to query
            filtered_query = self._add_entity_filter(
                pattern.query, entity_id, entity_type
            )

            try:
                results = await self.graph.execute_cypher(filtered_query)

                for row in results:
                    match_data = pattern.extractor(row)
                    entity_ids = self._extract_entity_ids(match_data)

                    match = PatternMatch(
                        pattern_id=pattern_id,
                        pattern_name=pattern.name,
                        severity=pattern.severity,
                        typology=pattern.typology,
                        match_data=match_data,
                        entity_ids=entity_ids
                    )
                    matches.append(match)
            except Exception:
                continue

        return matches

    async def check_entities_batch(
        self,
        entity_ids: list[str]
    ) -> dict[str, list[PatternMatch]]:
        """
        Check multiple entities for pattern matches.

        Returns a dict mapping entity_id to list of matches.
        """
        results = {}

        for entity_id in entity_ids:
            # Try both company and person types
            matches = await self.check_entity(entity_id, "Company")
            if not matches:
                matches = await self.check_entity(entity_id, "Person")
            results[entity_id] = matches

        return results

    def _add_entity_filter(
        self,
        query: str,
        entity_id: str,
        entity_type: str
    ) -> str:
        """
        Add a WHERE clause to filter by entity ID.

        This is a simple implementation - production would need
        proper query parsing.
        """
        # Find variable names that match the entity type
        type_mapping = {
            "Company": ["c", "c1", "c2", "old", "new", "target", "swedish", "company"],
            "Person": ["p", "person", "director"],
            "Address": ["a", "address"],
        }

        var_names = type_mapping.get(entity_type, [])

        # Add filter after the MATCH clause
        for var in var_names:
            if f"({var}:{entity_type})" in query or f"({var})" in query:
                # Add WHERE clause for this variable
                filter_clause = f" AND {var}.id = '{entity_id}'"
                if "WHERE" in query:
                    # Insert before first WHERE
                    query = query.replace("WHERE", f"WHERE {var}.id = '{entity_id}' AND ", 1)
                else:
                    # Add WHERE after MATCH
                    query = query.replace("RETURN", f"WHERE {var}.id = '{entity_id}'\nRETURN")
                break

        return query

    def _extract_entity_ids(self, match_data: dict) -> list[str]:
        """
        Extract entity IDs from match data.
        """
        entity_ids = []

        def extract_from_value(value: Any) -> None:
            if isinstance(value, dict):
                if "id" in value:
                    entity_ids.append(value["id"])
                for v in value.values():
                    extract_from_value(v)
            elif isinstance(value, list):
                for item in value:
                    extract_from_value(item)

        extract_from_value(match_data)
        return list(set(entity_ids))

    def add_pattern(self, pattern: FraudPattern) -> None:
        """Add a custom pattern."""
        self.patterns[pattern.id] = pattern

    def disable_pattern(self, pattern_id: str) -> None:
        """Disable a pattern."""
        if pattern_id in self.patterns:
            self.patterns[pattern_id].enabled = False

    def enable_pattern(self, pattern_id: str) -> None:
        """Enable a pattern."""
        if pattern_id in self.patterns:
            self.patterns[pattern_id].enabled = True

    def get_patterns_by_typology(self, typology: str) -> list[FraudPattern]:
        """Get all patterns of a specific typology."""
        return [p for p in self.patterns.values() if p.typology == typology]
