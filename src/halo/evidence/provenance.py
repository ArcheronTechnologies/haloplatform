"""
Provenance chain tracking for evidence integrity.

Implements hash-based chain of custody for evidence items.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


@dataclass
class ProvenanceEntry:
    """Single entry in a provenance chain."""

    id: UUID
    timestamp: datetime
    action: str  # created, modified, accessed, exported, etc.
    actor: str  # User or system that performed the action
    previous_hash: Optional[str]
    entry_hash: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "timestamp": self.timestamp.isoformat(),
            "action": self.action,
            "actor": self.actor,
            "previous_hash": self.previous_hash,
            "entry_hash": self.entry_hash,
            "details": self.details,
        }


@dataclass
class ProvenanceChain:
    """
    Chain of custody for an evidence item.

    Implements a hash-linked chain where each entry's hash
    depends on the previous entry, ensuring tamper-evidence.
    """

    item_id: UUID
    entries: list[ProvenanceEntry] = field(default_factory=list)

    def add_entry(
        self,
        action: str,
        actor: str,
        details: Optional[dict] = None,
    ) -> ProvenanceEntry:
        """
        Add a new entry to the provenance chain.

        Args:
            action: The action performed
            actor: Who performed the action
            details: Additional details about the action

        Returns:
            The new ProvenanceEntry
        """
        previous_hash = self.entries[-1].entry_hash if self.entries else None

        entry_id = uuid4()
        timestamp = datetime.utcnow()

        # Calculate entry hash
        entry_hash = self._calculate_entry_hash(
            entry_id=entry_id,
            timestamp=timestamp,
            action=action,
            actor=actor,
            previous_hash=previous_hash,
            details=details or {},
        )

        entry = ProvenanceEntry(
            id=entry_id,
            timestamp=timestamp,
            action=action,
            actor=actor,
            previous_hash=previous_hash,
            entry_hash=entry_hash,
            details=details or {},
        )

        self.entries.append(entry)
        logger.info(f"Added provenance entry {entry_id} for item {self.item_id}")

        return entry

    def verify(self) -> bool:
        """
        Verify the integrity of the entire chain.

        Returns:
            True if the chain is valid, False if tampered
        """
        if not self.entries:
            return True

        for i, entry in enumerate(self.entries):
            # Check previous hash link
            if i == 0:
                if entry.previous_hash is not None:
                    logger.error(f"First entry should have no previous hash")
                    return False
            else:
                if entry.previous_hash != self.entries[i - 1].entry_hash:
                    logger.error(f"Chain broken at entry {entry.id}")
                    return False

            # Verify entry hash
            expected_hash = self._calculate_entry_hash(
                entry_id=entry.id,
                timestamp=entry.timestamp,
                action=entry.action,
                actor=entry.actor,
                previous_hash=entry.previous_hash,
                details=entry.details,
            )

            if entry.entry_hash != expected_hash:
                logger.error(f"Hash mismatch at entry {entry.id}")
                return False

        return True

    def get_chain_hash(self) -> Optional[str]:
        """Get the hash of the latest entry (chain head)."""
        if not self.entries:
            return None
        return self.entries[-1].entry_hash

    def _calculate_entry_hash(
        self,
        entry_id: UUID,
        timestamp: datetime,
        action: str,
        actor: str,
        previous_hash: Optional[str],
        details: dict,
    ) -> str:
        """Calculate the hash for an entry."""
        hasher = hashlib.sha256()

        hasher.update(str(entry_id).encode())
        hasher.update(timestamp.isoformat().encode())
        hasher.update(action.encode())
        hasher.update(actor.encode())
        hasher.update((previous_hash or "").encode())
        hasher.update(str(sorted(details.items())).encode())

        return hasher.hexdigest()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "item_id": str(self.item_id),
            "entries": [e.to_dict() for e in self.entries],
            "chain_hash": self.get_chain_hash(),
            "is_valid": self.verify(),
        }


def verify_provenance(chain: ProvenanceChain) -> tuple[bool, list[str]]:
    """
    Verify a provenance chain and return detailed results.

    Args:
        chain: The provenance chain to verify

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors = []

    if not chain.entries:
        return True, []

    for i, entry in enumerate(chain.entries):
        # Check previous hash link
        if i == 0:
            if entry.previous_hash is not None:
                errors.append(f"Entry {i}: First entry should have no previous hash")
        else:
            expected_prev = chain.entries[i - 1].entry_hash
            if entry.previous_hash != expected_prev:
                errors.append(
                    f"Entry {i}: Previous hash mismatch. "
                    f"Expected {expected_prev[:8]}..., got {entry.previous_hash[:8] if entry.previous_hash else 'None'}..."
                )

    is_valid = len(errors) == 0
    return is_valid, errors


def create_provenance_chain(item_id: UUID, actor: str) -> ProvenanceChain:
    """
    Create a new provenance chain with an initial 'created' entry.

    Args:
        item_id: ID of the item this chain tracks
        actor: Who created the item

    Returns:
        New ProvenanceChain with initial entry
    """
    chain = ProvenanceChain(item_id=item_id)
    chain.add_entry(
        action="created",
        actor=actor,
        details={"event": "item_created"},
    )
    return chain
