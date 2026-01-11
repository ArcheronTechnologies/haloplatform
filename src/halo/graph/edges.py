"""
Intelligence Graph Edge Types.

Defines relationships between entities in the Halo intelligence graph.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional
from uuid import uuid4


@dataclass
class DirectsEdge:
    """
    Person directs a Company.

    Represents board membership, CEO roles, etc.
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    from_id: str = ""  # Person ID
    to_id: str = ""  # Company ID
    role: str = ""  # styrelseledamot, suppleant, vd, ordförande
    signing_rights: Optional[str] = None  # ensam, tillsammans, prokura
    from_date: Optional[date] = None
    to_date: Optional[date] = None
    source: str = ""

    @property
    def is_active(self) -> bool:
        """Check if directorship is current."""
        return self.to_date is None


@dataclass
class OwnsEdge:
    """
    Person or Company owns a Company.

    Represents ownership relationships.
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    from_id: str = ""  # Person or Company ID
    from_type: str = ""  # person or company
    to_id: str = ""  # Company ID
    share: float = 0.0  # 0-100 percentage
    direct: bool = True
    from_date: Optional[date] = None
    to_date: Optional[date] = None
    source: str = ""

    @property
    def is_majority(self) -> bool:
        """Check if this is majority ownership."""
        return self.share > 50

    @property
    def is_active(self) -> bool:
        """Check if ownership is current."""
        return self.to_date is None


@dataclass
class BeneficialOwnerEdge:
    """
    Person is beneficial owner of Company.

    Computed through ownership chains - represents ultimate control.
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    from_id: str = ""  # Person ID
    to_id: str = ""  # Company ID
    share: float = 0.0  # effective ownership percentage
    control_type: str = ""  # ownership, voting, other_control
    layers: int = 0  # how many companies deep
    path: list[str] = field(default_factory=list)  # [entity_ids] the ownership chain
    source: str = ""
    computed_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_layered(self) -> bool:
        """Check if ownership is through multiple layers."""
        return self.layers > 1


@dataclass
class RegisteredAtEdge:
    """
    Company registered at Address.
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    from_id: str = ""  # Company ID
    to_id: str = ""  # Address ID
    type: str = ""  # post, visit, registered
    from_date: Optional[date] = None
    to_date: Optional[date] = None
    source: str = ""

    @property
    def is_current(self) -> bool:
        """Check if registration is current."""
        return self.to_date is None


@dataclass
class LivesAtEdge:
    """
    Person lives at Address.
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    from_id: str = ""  # Person ID
    to_id: str = ""  # Address ID
    from_date: Optional[date] = None
    to_date: Optional[date] = None
    source: str = ""

    @property
    def is_current(self) -> bool:
        """Check if residence is current."""
        return self.to_date is None


@dataclass
class CoDirectorEdge:
    """
    Inferred: two Persons share directorships.

    Automatically computed when persons serve on boards together.
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    from_id: str = ""  # Person ID
    to_id: str = ""  # Person ID
    shared_companies: list[dict] = field(default_factory=list)  # [{company_id, overlap_period}]
    co_occurrence: int = 0  # number of shared companies
    strength: float = 0.0  # computed relationship strength
    computed_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_strong_connection(self) -> bool:
        """Check if connection is significant."""
        return self.co_occurrence >= 2 or self.strength > 0.5


@dataclass
class CoRegisteredEdge:
    """
    Inferred: two Companies share addresses or directors.

    Automatically computed to identify related companies.
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    from_id: str = ""  # Company ID
    to_id: str = ""  # Company ID
    shared_addresses: list[dict] = field(default_factory=list)  # [{address_id, overlap_period}]
    shared_directors: list[str] = field(default_factory=list)  # [person_ids]
    formation_gap_days: Optional[int] = None  # days between formations
    strength: float = 0.0
    computed_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_suspicious_gap(self) -> bool:
        """Check if companies were formed suspiciously close together."""
        return self.formation_gap_days is not None and self.formation_gap_days < 30


@dataclass
class TransactsEdge:
    """
    Money flow between accounts.

    For future use when transaction data is available.
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    from_id: str = ""  # BankAccount ID
    to_id: str = ""  # BankAccount ID
    amount: float = 0.0
    currency: str = "SEK"
    date: Optional[datetime] = None
    reference: Optional[str] = None
    pattern_flags: list[str] = field(default_factory=list)
    source: str = ""

    @property
    def is_large(self) -> bool:
        """Check if transaction is above reporting threshold."""
        # 150,000 SEK is the Swedish threshold
        return self.amount >= 150000

    @property
    def is_flagged(self) -> bool:
        """Check if transaction has any pattern flags."""
        return len(self.pattern_flags) > 0


@dataclass
class SameAsEdge:
    """
    Entity resolution: two records represent same entity.

    Created when deduplication identifies matches.
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    from_id: str = ""
    from_type: str = ""
    to_id: str = ""
    to_type: str = ""
    confidence: float = 0.0
    method: str = ""  # exact_match, fuzzy, ml_model
    evidence: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_high_confidence(self) -> bool:
        """Check if match is high confidence."""
        return self.confidence > 0.9


@dataclass
class OwnsPropertyEdge:
    """
    Person or Company owns a Property.
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    from_id: str = ""  # Person or Company ID
    from_type: str = ""  # person or company
    to_id: str = ""  # Property ID
    share: float = 100.0  # ownership percentage
    from_date: Optional[date] = None
    to_date: Optional[date] = None
    purchase_price: Optional[float] = None
    source: str = ""

    @property
    def is_current(self) -> bool:
        """Check if ownership is current."""
        return self.to_date is None
