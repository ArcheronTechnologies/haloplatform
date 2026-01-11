"""
Relationship extraction from structured data and text.

Extracts relationships from:
- Company boards (from Bolagsverket data)
- Ownership structures
- Address co-location
- Transaction patterns
- NLP-based extraction from text

Produces edges for the entity graph.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from halo.db.orm import RelationshipType

logger = logging.getLogger(__name__)


class RelationshipSource(Enum):
    """Source of the relationship extraction."""

    BOLAGSVERKET = "bolagsverket"
    SCB = "scb"
    LANTMATERIET = "lantmateriet"
    TRANSACTION = "transaction"
    NLP = "nlp"
    MANUAL = "manual"


@dataclass
class ExtractedRelationship:
    """A relationship extracted from data or text."""

    from_entity_id: Optional[UUID]
    to_entity_id: Optional[UUID]
    relationship_type: RelationshipType
    confidence: float
    source: RelationshipSource

    # For unresolved entities (will be resolved later)
    from_entity_ref: Optional[str] = None
    to_entity_ref: Optional[str] = None

    # Metadata
    attributes: dict = field(default_factory=dict)
    evidence: str = ""
    extracted_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_resolved(self) -> bool:
        """Check if both entities are resolved to IDs."""
        return self.from_entity_id is not None and self.to_entity_id is not None


@dataclass
class BoardMember:
    """A board member extracted from company data."""

    name: str
    personnummer: Optional[str] = None
    role: str = "styrelseledamot"
    from_date: Optional[datetime] = None
    to_date: Optional[datetime] = None


@dataclass
class OwnershipStake:
    """An ownership stake in a company."""

    owner_ref: str  # Personnummer, orgnummer, or name
    owner_type: str  # "person" or "company"
    percentage: Optional[float] = None
    share_count: Optional[int] = None
    share_class: str = "A"


class StructuredRelationshipExtractor:
    """
    Extracts relationships from structured data sources.

    Handles:
    - Company board compositions
    - Ownership structures
    - Address co-location
    - Vehicle ownership
    """

    def extract_from_bolagsverket(
        self,
        company_data: dict[str, Any],
        company_entity_id: Optional[UUID] = None,
    ) -> list[ExtractedRelationship]:
        """
        Extract relationships from Bolagsverket company data.

        Args:
            company_data: Raw company data from Bolagsverket
            company_entity_id: Resolved entity ID for the company

        Returns:
            List of extracted relationships
        """
        relationships = []
        orgnr = company_data.get("organisationsnummer", "")

        # Extract board members
        board = company_data.get("styrelse", [])
        for member in board:
            rel = self._extract_board_relationship(
                member, orgnr, company_entity_id
            )
            if rel:
                relationships.append(rel)

        # Extract ownership
        owners = company_data.get("agare", [])
        for owner in owners:
            rel = self._extract_ownership_relationship(
                owner, orgnr, company_entity_id
            )
            if rel:
                relationships.append(rel)

        # Extract signatory rights
        signatories = company_data.get("firmatecknare", [])
        for sig in signatories:
            rel = self._extract_signatory_relationship(
                sig, orgnr, company_entity_id
            )
            if rel:
                relationships.append(rel)

        # Extract auditor
        auditor = company_data.get("revisor", {})
        if auditor:
            rel = self._extract_auditor_relationship(
                auditor, orgnr, company_entity_id
            )
            if rel:
                relationships.append(rel)

        logger.debug(
            f"Extracted {len(relationships)} relationships from company {orgnr}"
        )
        return relationships

    def _extract_board_relationship(
        self,
        member_data: dict[str, Any],
        company_orgnr: str,
        company_entity_id: Optional[UUID],
    ) -> Optional[ExtractedRelationship]:
        """Extract board member relationship."""
        name = member_data.get("namn", "")
        if not name:
            return None

        role = member_data.get("befattning", "styrelseledamot").lower()
        personnummer = member_data.get("personnummer")

        # Map role to relationship type
        if "ordförande" in role:
            rel_type = RelationshipType.BOARD_CHAIR
        elif "vd" in role or "verkställande" in role:
            rel_type = RelationshipType.CEO
        elif "suppleant" in role:
            rel_type = RelationshipType.BOARD_DEPUTY
        else:
            rel_type = RelationshipType.BOARD_MEMBER

        return ExtractedRelationship(
            from_entity_id=None,  # Person - to be resolved
            to_entity_id=company_entity_id,
            relationship_type=rel_type,
            confidence=0.95 if personnummer else 0.7,
            source=RelationshipSource.BOLAGSVERKET,
            from_entity_ref=personnummer or name,
            to_entity_ref=company_orgnr,
            attributes={
                "role": role,
                "name": name,
                "from_date": member_data.get("tillträdesdatum"),
            },
            evidence=f"Bolagsverket: {name} som {role}",
        )

    def _extract_ownership_relationship(
        self,
        owner_data: dict[str, Any],
        company_orgnr: str,
        company_entity_id: Optional[UUID],
    ) -> Optional[ExtractedRelationship]:
        """Extract ownership relationship."""
        owner_ref = owner_data.get("personnummer") or owner_data.get(
            "organisationsnummer"
        )
        if not owner_ref:
            owner_ref = owner_data.get("namn", "")
        if not owner_ref:
            return None

        percentage = owner_data.get("andel")
        share_count = owner_data.get("antal_aktier")

        # Determine if owner is a person or company
        owner_type = "person"
        if owner_data.get("organisationsnummer"):
            owner_type = "company"

        return ExtractedRelationship(
            from_entity_id=None,
            to_entity_id=company_entity_id,
            relationship_type=RelationshipType.OWNS,
            confidence=0.95,
            source=RelationshipSource.BOLAGSVERKET,
            from_entity_ref=owner_ref,
            to_entity_ref=company_orgnr,
            attributes={
                "owner_type": owner_type,
                "percentage": percentage,
                "share_count": share_count,
                "share_class": owner_data.get("aktieslag", "A"),
            },
            evidence=f"Bolagsverket: äger {percentage or '?'}%",
        )

    def _extract_signatory_relationship(
        self,
        sig_data: dict[str, Any],
        company_orgnr: str,
        company_entity_id: Optional[UUID],
    ) -> Optional[ExtractedRelationship]:
        """Extract signatory rights relationship."""
        name = sig_data.get("namn", "")
        if not name:
            return None

        personnummer = sig_data.get("personnummer")

        return ExtractedRelationship(
            from_entity_id=None,
            to_entity_id=company_entity_id,
            relationship_type=RelationshipType.SIGNATORY,
            confidence=0.95 if personnummer else 0.7,
            source=RelationshipSource.BOLAGSVERKET,
            from_entity_ref=personnummer or name,
            to_entity_ref=company_orgnr,
            attributes={
                "name": name,
                "signatory_type": sig_data.get("typ", "ensam"),
            },
            evidence=f"Bolagsverket: firmatecknare {name}",
        )

    def _extract_auditor_relationship(
        self,
        auditor_data: dict[str, Any],
        company_orgnr: str,
        company_entity_id: Optional[UUID],
    ) -> Optional[ExtractedRelationship]:
        """Extract auditor relationship."""
        # Auditor can be a person or an auditing firm
        auditor_ref = auditor_data.get("organisationsnummer") or auditor_data.get(
            "personnummer"
        )
        if not auditor_ref:
            auditor_ref = auditor_data.get("namn", "")
        if not auditor_ref:
            return None

        return ExtractedRelationship(
            from_entity_id=None,
            to_entity_id=company_entity_id,
            relationship_type=RelationshipType.AUDITOR,
            confidence=0.95,
            source=RelationshipSource.BOLAGSVERKET,
            from_entity_ref=auditor_ref,
            to_entity_ref=company_orgnr,
            attributes={
                "name": auditor_data.get("namn"),
                "firm": auditor_data.get("revisionsbyrå"),
            },
            evidence=f"Bolagsverket: revisor",
        )

    def extract_address_colocation(
        self,
        entities_at_address: list[tuple[UUID, str, str]],
    ) -> list[ExtractedRelationship]:
        """
        Extract co-location relationships from address data.

        Args:
            entities_at_address: List of (entity_id, entity_type, entity_name)
                                 at the same address

        Returns:
            List of co-location relationships
        """
        relationships = []

        if len(entities_at_address) < 2:
            return relationships

        # Create co-location relationships between all pairs
        for i, (id1, type1, name1) in enumerate(entities_at_address):
            for id2, type2, name2 in entities_at_address[i + 1 :]:
                # Skip if same entity type (less interesting)
                confidence = 0.6 if type1 == type2 else 0.75

                relationships.append(
                    ExtractedRelationship(
                        from_entity_id=id1,
                        to_entity_id=id2,
                        relationship_type=RelationshipType.COLOCATED,
                        confidence=confidence,
                        source=RelationshipSource.LANTMATERIET,
                        attributes={
                            "from_type": type1,
                            "to_type": type2,
                        },
                        evidence=f"Same address: {name1} och {name2}",
                    )
                )

        return relationships


class NLPRelationshipExtractor:
    """
    Extracts relationships from unstructured text using NLP.

    Detects patterns like:
    - "X är VD för Y"
    - "X äger Y"
    - "X arbetar på Y"
    - "X och Y samarbetar"
    """

    # Swedish relationship patterns
    PATTERNS = {
        RelationshipType.CEO: [
            r"(\w+(?:\s+\w+)?)\s+är\s+(?:VD|verkställande\s+direktör)\s+(?:för|på|i)\s+(\w+(?:\s+\w+)*)",
            r"VD:?n?\s+(\w+(?:\s+\w+)?)\s+(?:på|för|i)\s+(\w+(?:\s+\w+)*)",
        ],
        RelationshipType.BOARD_CHAIR: [
            r"(\w+(?:\s+\w+)?)\s+är\s+(?:styrelse)?ordförande\s+(?:för|i)\s+(\w+(?:\s+\w+)*)",
            r"ordförande\s+(\w+(?:\s+\w+)?)\s+(?:i|för)\s+(\w+(?:\s+\w+)*)",
        ],
        RelationshipType.OWNS: [
            r"(\w+(?:\s+\w+)?)\s+äger\s+(\w+(?:\s+\w+)*)",
            r"(\w+(?:\s+\w+)?)\s+har\s+(?:köpt|förvärvat)\s+(\w+(?:\s+\w+)*)",
            r"ägare\s+(\w+(?:\s+\w+)?)\s+(?:till|av)\s+(\w+(?:\s+\w+)*)",
        ],
        RelationshipType.EMPLOYED_BY: [
            r"(\w+(?:\s+\w+)?)\s+arbetar\s+(?:på|för|hos)\s+(\w+(?:\s+\w+)*)",
            r"(\w+(?:\s+\w+)?)\s+är\s+anställd\s+(?:på|hos|vid)\s+(\w+(?:\s+\w+)*)",
        ],
        RelationshipType.ASSOCIATED: [
            r"(\w+(?:\s+\w+)?)\s+(?:och|samt)\s+(\w+(?:\s+\w+)?)\s+samarbetar",
            r"koppling\s+mellan\s+(\w+(?:\s+\w+)?)\s+och\s+(\w+(?:\s+\w+)?)",
            r"(\w+(?:\s+\w+)?)\s+har\s+(?:kontakt|koppling)\s+(?:med|till)\s+(\w+(?:\s+\w+)?)",
        ],
        RelationshipType.TRANSACTED_WITH: [
            r"(\w+(?:\s+\w+)?)\s+(?:betalade|överförde)\s+(?:till|mot)\s+(\w+(?:\s+\w+)?)",
            r"transaktion\s+(?:från|mellan)\s+(\w+(?:\s+\w+)?)\s+(?:till|och)\s+(\w+(?:\s+\w+)?)",
        ],
        RelationshipType.FAMILY: [
            r"(\w+(?:\s+\w+)?)\s+är\s+(?:gift|sambo)\s+med\s+(\w+(?:\s+\w+)?)",
            r"(\w+(?:\s+\w+)?)\s+(?:och|samt)\s+(\w+(?:\s+\w+)?)\s+är\s+syskon",
            r"(\w+(?:\s+\w+)?)s?\s+(?:son|dotter|barn|förälder|mor|far)\s+(\w+(?:\s+\w+)?)",
        ],
    }

    # Compile patterns
    _compiled_patterns: dict[RelationshipType, list[re.Pattern]] = {}

    def __init__(self):
        """Initialize with compiled regex patterns."""
        for rel_type, patterns in self.PATTERNS.items():
            self._compiled_patterns[rel_type] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]

    def extract_from_text(
        self,
        text: str,
        source_document_id: Optional[UUID] = None,
    ) -> list[ExtractedRelationship]:
        """
        Extract relationships from text using pattern matching.

        Args:
            text: Input text
            source_document_id: ID of source document for provenance

        Returns:
            List of extracted relationships
        """
        relationships = []

        for rel_type, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                matches = pattern.finditer(text)
                for match in matches:
                    entity1 = match.group(1).strip()
                    entity2 = match.group(2).strip()

                    # Skip very short matches (likely false positives)
                    if len(entity1) < 2 or len(entity2) < 2:
                        continue

                    # Get context around match
                    start = max(0, match.start() - 50)
                    end = min(len(text), match.end() + 50)
                    context = text[start:end]

                    relationships.append(
                        ExtractedRelationship(
                            from_entity_id=None,
                            to_entity_id=None,
                            relationship_type=rel_type,
                            confidence=self._calculate_confidence(match, text),
                            source=RelationshipSource.NLP,
                            from_entity_ref=entity1,
                            to_entity_ref=entity2,
                            attributes={
                                "pattern": pattern.pattern,
                                "document_id": str(source_document_id)
                                if source_document_id
                                else None,
                            },
                            evidence=f"...{context}...",
                        )
                    )

        # Deduplicate similar relationships
        relationships = self._deduplicate(relationships)

        logger.debug(f"Extracted {len(relationships)} relationships from text")
        return relationships

    def _calculate_confidence(self, match: re.Match, text: str) -> float:
        """
        Calculate confidence score for a match.

        Higher confidence for:
        - Longer entity names
        - Matches in formal text
        - Matches with surrounding context
        """
        base_confidence = 0.5

        entity1 = match.group(1)
        entity2 = match.group(2)

        # Longer names = higher confidence
        if len(entity1) > 10:
            base_confidence += 0.1
        if len(entity2) > 10:
            base_confidence += 0.1

        # Multiple words = likely a real name
        if " " in entity1:
            base_confidence += 0.1
        if " " in entity2:
            base_confidence += 0.1

        # Cap at 0.85 (NLP extractions should not be fully trusted)
        return min(0.85, base_confidence)

    def _deduplicate(
        self, relationships: list[ExtractedRelationship]
    ) -> list[ExtractedRelationship]:
        """Remove duplicate relationships, keeping highest confidence."""
        seen: dict[tuple, ExtractedRelationship] = {}

        for rel in relationships:
            key = (
                rel.from_entity_ref,
                rel.to_entity_ref,
                rel.relationship_type,
            )

            if key not in seen or rel.confidence > seen[key].confidence:
                seen[key] = rel

        return list(seen.values())


class TransactionRelationshipExtractor:
    """
    Extracts relationships from transaction data.

    Creates TRANSACTED_WITH relationships based on:
    - Direct transactions between entities
    - Transaction patterns indicating business relationships
    """

    def __init__(
        self,
        min_transactions: int = 3,
        min_total_amount: float = 10000,
    ):
        """
        Initialize extractor.

        Args:
            min_transactions: Minimum transactions to create relationship
            min_total_amount: Minimum total amount for relationship
        """
        self.min_transactions = min_transactions
        self.min_total_amount = min_total_amount

    def extract_from_transactions(
        self,
        transactions: list[dict[str, Any]],
    ) -> list[ExtractedRelationship]:
        """
        Extract relationships from transaction data.

        Args:
            transactions: List of transaction dicts with from_entity_id,
                         to_entity_id, amount, timestamp

        Returns:
            List of transaction-based relationships
        """
        # Aggregate transactions between entity pairs
        pairs: dict[tuple[UUID, UUID], dict] = {}

        for txn in transactions:
            from_id = txn.get("from_entity_id")
            to_id = txn.get("to_entity_id")
            amount = txn.get("amount", 0)

            if not from_id or not to_id:
                continue

            key = (from_id, to_id)
            if key not in pairs:
                pairs[key] = {
                    "count": 0,
                    "total_amount": 0,
                    "first_date": txn.get("timestamp"),
                    "last_date": txn.get("timestamp"),
                }

            pairs[key]["count"] += 1
            pairs[key]["total_amount"] += amount

            txn_date = txn.get("timestamp")
            if txn_date:
                if pairs[key]["first_date"] is None or txn_date < pairs[key]["first_date"]:
                    pairs[key]["first_date"] = txn_date
                if pairs[key]["last_date"] is None or txn_date > pairs[key]["last_date"]:
                    pairs[key]["last_date"] = txn_date

        # Create relationships for significant transaction patterns
        relationships = []

        for (from_id, to_id), stats in pairs.items():
            if (
                stats["count"] >= self.min_transactions
                and stats["total_amount"] >= self.min_total_amount
            ):
                # Calculate confidence based on volume
                confidence = min(
                    0.9,
                    0.5 + (stats["count"] / 20) * 0.2 + (stats["total_amount"] / 1000000) * 0.2,
                )

                relationships.append(
                    ExtractedRelationship(
                        from_entity_id=from_id,
                        to_entity_id=to_id,
                        relationship_type=RelationshipType.TRANSACTED_WITH,
                        confidence=confidence,
                        source=RelationshipSource.TRANSACTION,
                        attributes={
                            "transaction_count": stats["count"],
                            "total_amount": stats["total_amount"],
                            "first_transaction": stats["first_date"].isoformat()
                            if stats["first_date"]
                            else None,
                            "last_transaction": stats["last_date"].isoformat()
                            if stats["last_date"]
                            else None,
                        },
                        evidence=f"{stats['count']} transactions totaling {stats['total_amount']:,.0f} SEK",
                    )
                )

        return relationships


class RelationshipExtractor:
    """
    Main relationship extraction orchestrator.

    Combines all extraction methods and provides a unified interface.
    """

    def __init__(self):
        """Initialize all extractors."""
        self.structured_extractor = StructuredRelationshipExtractor()
        self.nlp_extractor = NLPRelationshipExtractor()
        self.transaction_extractor = TransactionRelationshipExtractor()

    def extract_all(
        self,
        company_data: Optional[list[dict]] = None,
        texts: Optional[list[tuple[str, Optional[UUID]]]] = None,
        transactions: Optional[list[dict]] = None,
        address_groups: Optional[list[list[tuple[UUID, str, str]]]] = None,
    ) -> list[ExtractedRelationship]:
        """
        Extract relationships from all available sources.

        Args:
            company_data: List of company data dicts from Bolagsverket
            texts: List of (text, document_id) tuples
            transactions: List of transaction dicts
            address_groups: List of entity groups at same address

        Returns:
            All extracted relationships
        """
        all_relationships = []

        # Structured data
        if company_data:
            for data in company_data:
                rels = self.structured_extractor.extract_from_bolagsverket(data)
                all_relationships.extend(rels)

        # Text/NLP
        if texts:
            for text, doc_id in texts:
                rels = self.nlp_extractor.extract_from_text(text, doc_id)
                all_relationships.extend(rels)

        # Transactions
        if transactions:
            rels = self.transaction_extractor.extract_from_transactions(transactions)
            all_relationships.extend(rels)

        # Address co-location
        if address_groups:
            for group in address_groups:
                rels = self.structured_extractor.extract_address_colocation(group)
                all_relationships.extend(rels)

        logger.info(f"Extracted {len(all_relationships)} total relationships")
        return all_relationships
