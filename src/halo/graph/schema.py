"""
Intelligence Graph Node Types.

Defines the core entity types for the Halo intelligence graph.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional
from uuid import uuid4


@dataclass
class Person:
    """
    Person node in the intelligence graph.

    Represents individuals - can be Swedish citizens (with personnummer),
    foreigners, or people with protected identity.
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    personnummer: Optional[str] = None  # nullable for foreigners, protected identity
    names: list[dict] = field(default_factory=list)  # [{name, source, observed_at}]
    addresses: list[dict] = field(default_factory=list)  # [{address_id, type, from_date, to_date}]
    dob: Optional[date] = None
    nationality: Optional[str] = None
    pep_status: Optional[dict] = None  # {is_pep, position, from, to, source}
    sanctions_matches: list[dict] = field(default_factory=list)  # [{list, match_score, checked_at}]

    # Computed fields
    risk_score: float = 0.0
    flags: list[dict] = field(default_factory=list)  # [{flag_type, severity, evidence[]}]
    network_metrics: dict = field(default_factory=dict)  # {degree, betweenness, eigenvector, cluster_id}

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    sources: list[str] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        """Get the most recent/primary name."""
        if self.names:
            # Sort by observed_at if available, take most recent
            sorted_names = sorted(
                self.names,
                key=lambda n: n.get("observed_at", ""),
                reverse=True
            )
            return sorted_names[0].get("name", "Unknown")
        return "Unknown"

    @property
    def is_pep(self) -> bool:
        """Check if person is a PEP."""
        return bool(self.pep_status and self.pep_status.get("is_pep"))

    @property
    def has_sanctions_hit(self) -> bool:
        """Check if person has any sanctions matches."""
        return any(m.get("match_score", 0) > 0.8 for m in self.sanctions_matches)


@dataclass
class Company:
    """
    Company node in the intelligence graph.

    Represents Swedish companies registered with Bolagsverket.
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    orgnr: str = ""
    names: list[dict] = field(default_factory=list)  # [{name, type, from, to}] includes särskilda firmor
    legal_form: str = ""  # AB, HB, EF, etc
    status: dict = field(default_factory=dict)  # {code, text, from}
    status_history: list[dict] = field(default_factory=list)  # [{status, from, to}]

    formation: dict = field(default_factory=dict)  # {date, agent, method}
    addresses: list[dict] = field(default_factory=list)  # [{address_id, type, from, to}]
    sni_codes: list[dict] = field(default_factory=list)  # [{code, from, to}]

    # Tax registration
    f_skatt: Optional[dict] = None  # {registered, from, to}
    vat: Optional[dict] = None  # {registered, from, to}
    employer: Optional[dict] = None  # {registered, from, to}

    # Financials (when available)
    employees: Optional[dict] = None  # {count, interval, as_of}
    revenue: Optional[dict] = None  # {amount, year}

    # Computed fields
    risk_score: float = 0.0
    flags: list[dict] = field(default_factory=list)
    shell_score: float = 0.0  # 0-1 probability of being a shell company
    network_metrics: dict = field(default_factory=dict)

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    sources: list[str] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        """Get the current company name."""
        if self.names:
            # Get name without to_date (current)
            current = [n for n in self.names if not n.get("to")]
            if current:
                return current[0].get("name", "Unknown")
            # Fallback to most recent
            sorted_names = sorted(
                self.names,
                key=lambda n: n.get("from", ""),
                reverse=True
            )
            return sorted_names[0].get("name", "Unknown")
        return "Unknown"

    @property
    def is_active(self) -> bool:
        """Check if company is active."""
        status_code = self.status.get("code", "").lower()
        return status_code in ("active", "aktiv", "registered")

    @property
    def has_f_skatt(self) -> bool:
        """Check if company has F-skatt registration."""
        return bool(self.f_skatt and self.f_skatt.get("registered"))

    @property
    def has_vat(self) -> bool:
        """Check if company has VAT registration."""
        return bool(self.vat and self.vat.get("registered"))

    @property
    def employee_count(self) -> int:
        """Get employee count or 0 if unknown."""
        if self.employees:
            return self.employees.get("count", 0)
        return 0


@dataclass
class Address:
    """
    Address node in the intelligence graph.

    Represents physical or virtual addresses where entities are registered.
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    raw_strings: list[str] = field(default_factory=list)  # all observed variations
    normalized: dict = field(default_factory=dict)  # {street, number, postal_code, city, country}
    geo: Optional[dict] = None  # {lat, lng}
    property_id: Optional[str] = None  # link to fastighet
    type: str = "unknown"  # residential, commercial, mixed, virtual, unknown

    # Computed fields
    registration_count: int = 0
    registration_velocity: float = 0.0  # new registrations per month
    flags: list[dict] = field(default_factory=list)

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    sources: list[str] = field(default_factory=list)

    @property
    def display_address(self) -> str:
        """Get formatted address string."""
        n = self.normalized
        parts = []
        if n.get("street"):
            street = n["street"]
            if n.get("number"):
                street += f" {n['number']}"
            parts.append(street)
        if n.get("postal_code"):
            parts.append(n["postal_code"])
        if n.get("city"):
            parts.append(n["city"])
        return ", ".join(parts) if parts else (self.raw_strings[0] if self.raw_strings else "Unknown")

    @property
    def is_virtual(self) -> bool:
        """Check if address is a virtual office."""
        return self.type == "virtual"

    @property
    def is_high_density(self) -> bool:
        """Check if address has suspiciously high registration count."""
        return self.registration_count > 5


@dataclass
class Property:
    """
    Property node in the intelligence graph.

    Represents real estate (fastighet) from Lantmäteriet.
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    fastighet_id: str = ""  # from Lantmäteriet
    addresses: list[str] = field(default_factory=list)  # [address_id]
    type: str = ""
    size: Optional[float] = None
    owners: list[dict] = field(default_factory=list)  # [{entity_id, share, from, to}]
    taxeringsvarde: Optional[dict] = None  # {amount, year}

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    sources: list[str] = field(default_factory=list)


@dataclass
class BankAccount:
    """
    Bank account node in the intelligence graph.

    For future use when transaction data is available.
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    iban: Optional[str] = None
    bank: str = ""
    holder_id: str = ""
    holder_type: str = ""  # person or company
    type: str = ""  # current, savings, etc
    opened: Optional[date] = None
    closed: Optional[date] = None

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    sources: list[str] = field(default_factory=list)


@dataclass
class Document:
    """
    Document node for evidence chain.

    Represents source documents like annual reports, registrations, court filings.
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    type: str = ""  # annual_report, registration, court_filing, news
    entity_refs: list[dict] = field(default_factory=list)  # [{entity_id, entity_type}]
    source: str = ""
    date: Optional[date] = None
    url: Optional[str] = None
    extracted_data: dict = field(default_factory=dict)

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    sources: list[str] = field(default_factory=list)
